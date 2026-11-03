"""Pantallas del Mantenedor: Tareas, Procesos y Usuarios. El permiso se valida aquí y otra vez en los servicios."""
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from nucleo import permisos
from nucleo.models import ESTADOS_PLAN, Cargo, Colaborador, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import agenda, auditoria, estructura, excel_masivo, mantenedor, reglas_texto, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado

TIPOS = [
    ("DIARIA_HABIL", "Todos los días hábiles"), ("SEMANAL", "Una vez a la semana"), ("CIERRE_DIA_HABIL", "Día hábil del cierre (1 a 7)"),
    ("CIERRE_HITO", "Día 8, 9 o 10 del mes (reportes, Gerente, Directorio)"), ("DIA_FIJO", "Día fijo del mes"), ("FIN_DE_MES", "Último día del mes"), ("MESES", "Meses específicos"), ("EVENTO", "Por evento (se crea a mano)"),
]
DIAS = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes")]
MESES = [(i + 1, n.capitalize()) for i, n in enumerate(reglas_texto.MESES)]
ETIQUETAS_ROL = {"GERENTE": "Gerente", "JEFATURA": "Jefatura", "COLABORADOR": "Colaborador", "LECTURA": "Solo lectura", "ADMIN_SISTEMA": "Administrador del sistema"}


def _prohibido(request, mensaje="No tienes permiso para esta pantalla."):
    return render(request, "nucleo/prohibido.html", {"mensaje": mensaje}, status=403)


def con_roles(*roles):
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if permisos.rol_de(request.user) not in roles:
                return _prohibido(request)
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador


EDITA_TAREAS = (permisos.GERENTE, permisos.JEFATURA)
GESTIONA_USUARIOS = (permisos.GERENTE, permisos.ADMIN_SISTEMA)


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _fecha(texto: str):
    if not (texto or "").strip():
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise ErrorDeNegocio("Una de las fechas no es válida (usa día, mes y año).") from None


def _minutos(horas: str):
    try:
        return round(float(horas.replace(",", ".")) * 60)
    except (ValueError, AttributeError):
        return None


# ---- Tareas ----------------------------------------------------------------------------------------------


@con_roles(*EDITA_TAREAS)
def tareas(request):
    qs = Tarea.objects.select_related("proceso", "cargo_ejecuta", "cargo_revisa")
    f = {k: request.GET.get(k, "") for k in ("proceso", "cargo", "estado", "q")}
    if f["proceso"]:
        qs = qs.filter(proceso_id=_entero(f["proceso"]))
    if f["cargo"]:
        qs = qs.filter(cargo_ejecuta_id=_entero(f["cargo"]))
    if f["estado"] == "activas":
        qs = qs.filter(activa=True)
    elif f["estado"] == "inactivas":
        qs = qs.filter(activa=False)
    elif f["estado"] == "revision":
        qs = qs.filter(requiere_revision=True)
    if f["q"]:
        qs = qs.filter(Q(tarea_principal__icontains=f["q"]) | Q(subtarea__icontains=f["q"]) | Q(codigo__icontains=f["q"]))
    lista = list(qs.order_by("proceso__orden", "secuencia", "codigo"))
    for t in lista:
        t.periodicidad = reglas_texto.describir(t.regla(), t.regla_franja)
    return render(request, "nucleo/mant_tareas.html", {"tareas": lista, "f": f, "procesos": Proceso.objects.all(), "cargos": Cargo.objects.filter(activo=True)})


def _valores_de(t: Tarea | None) -> dict:
    if t is None:
        return {"proceso": "", "tarea_principal": "", "subtarea": "", "cargo_ejecuta": "", "tipo": "CIERRE_DIA_HABIL", "dia_semana": "", "franja": "", "n": "", "dia": "",
                "meses": [], "ajuste": "siguiente", "referencia": "", "activa": True, "cargo_revisa": "", "horas": "", "minutos_revision": "", "estado_plan": "pendiente", "fecha_inicio": "",
                "fecha_termino": "", "observaciones": "", "modo_cierre": "igual", "cargo_cierre": "", "revisa_cierre": "", "dh_inicio": ""}
    return {"proceso": str(t.proceso_id), "tarea_principal": t.tarea_principal, "subtarea": t.subtarea, "cargo_ejecuta": str(t.cargo_ejecuta_id), "tipo": t.regla_tipo,
            "dia_semana": "" if t.regla_dia_semana is None else str(t.regla_dia_semana), "franja": t.regla_franja, "n": "" if t.regla_n is None else str(t.regla_n),
            "dia": "" if t.regla_dia is None else str(t.regla_dia), "meses": [m for m in t.regla_meses.split(",") if m], "ajuste": t.regla_ajuste,
            "referencia": t.referencia_normativa, "activa": t.activa, "cargo_revisa": str(t.cargo_revisa_id or ""),
            "horas": "" if t.minutos_estimados is None else str(round(t.minutos_estimados / 60, 2)).replace(".", ","),
            "minutos_revision": "" if t.minutos_revision is None else str(t.minutos_revision), "estado_plan": t.estado_plan,
            "fecha_inicio": str(t.fecha_inicio or ""), "fecha_termino": str(t.fecha_termino or ""), "observaciones": t.observaciones,
            "modo_cierre": t.modo_cierre, "cargo_cierre": str(t.cargo_cierre_id or ""), "revisa_cierre": str(t.cargo_revisa_cierre_id or ""), "dh_inicio": "" if t.dh_inicio is None else str(t.dh_inicio)}


def _valores_de_post(post) -> dict:
    return {"proceso": post.get("proceso", ""), "tarea_principal": post.get("tarea_principal", ""), "subtarea": post.get("subtarea", ""), "cargo_ejecuta": post.get("cargo_ejecuta", ""),
            "tipo": post.get("tipo", ""), "dia_semana": post.get("dia_semana", ""), "franja": post.get("franja", ""), "n": post.get("n", ""), "dia": post.get("dia", ""),
            "meses": post.getlist("meses"), "ajuste": post.get("ajuste", "siguiente"), "referencia": post.get("referencia", ""), "activa": post.get("activa") == "on", "cargo_revisa": post.get("cargo_revisa", ""),
            "horas": post.get("horas", ""), "minutos_revision": post.get("minutos_revision", ""), "estado_plan": post.get("estado_plan", "pendiente"), "fecha_inicio": post.get("fecha_inicio", ""),
            "fecha_termino": post.get("fecha_termino", ""), "observaciones": post.get("observaciones", ""), "modo_cierre": post.get("modo_cierre", "igual"),
            "cargo_cierre": post.get("cargo_cierre", ""), "revisa_cierre": post.get("revisa_cierre", ""), "dh_inicio": post.get("dh_inicio", "")}


def _datos_de(v: dict) -> mantenedor.DatosTarea:
    return mantenedor.DatosTarea(
        proceso_id=_entero(v["proceso"]) or 0, tarea_principal=v["tarea_principal"], subtarea=v["subtarea"], cargo_ejecuta_id=_entero(v["cargo_ejecuta"]) or 0, tipo=v["tipo"],
        dia_semana=_entero(v["dia_semana"]), franja=v["franja"], n=_entero(v["n"]), dia=_entero(v["dia"]), meses=tuple(m for m in (_entero(x) for x in v["meses"]) if m),
        ajuste=v["ajuste"], referencia=v["referencia"], activa=v["activa"], cargo_revisa_id=_entero(v["cargo_revisa"]), minutos=_minutos(v["horas"]), minutos_revision=_entero(v["minutos_revision"]),
        estado_plan=v["estado_plan"], fecha_inicio=_fecha(v["fecha_inicio"]), fecha_termino=_fecha(v["fecha_termino"]), observaciones=v["observaciones"],
        modo_cierre=v["modo_cierre"], cargo_cierre_id=_entero(v["cargo_cierre"]), cargo_revisa_cierre_id=_entero(v["revisa_cierre"]), dh_inicio=_entero(v["dh_inicio"]),
    )


def _formulario_tarea(request, tarea: Tarea | None):
    valores = _valores_de(tarea)
    error = ""
    if request.method == "POST":
        valores = _valores_de_post(request.POST)
        try:
            if tarea is None:
                t = mantenedor.crear_tarea(request.user, _datos_de(valores))
            else:
                t = mantenedor.editar_tarea(request.user, tarea, _datos_de(valores))
            messages.success(request, f"Tarea {t.codigo} guardada. El cambio rige desde el próximo mes que se abra.")
            return redirect("mant_tareas")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            error = str(e)
    return render(request, "nucleo/mant_tarea_form.html", {
        "tarea": tarea, "v": valores, "error": error, "procesos": Proceso.objects.filter(activo=True), "cargos": Cargo.objects.filter(activo=True),
        "tipos": TIPOS, "dias": DIAS, "meses": MESES, "estados": ESTADOS_PLAN, "modos_cierre": Tarea.MODOS_CIERRE, "tareas_existentes": TareaPrincipal.objects.select_related("proceso").order_by("proceso__orden", "numero"),
    })


@con_roles(*EDITA_TAREAS)
def tarea_nueva(request):
    return _formulario_tarea(request, None)


@con_roles(*EDITA_TAREAS)
def tarea_editar(request, pk):
    return _formulario_tarea(request, get_object_or_404(Tarea, pk=pk))


# ---- Procesos --------------------------------------------------------------------------------------------


@con_roles(*EDITA_TAREAS)
def procesos(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "crear":
                p = estructura.crear_proceso(request.user, request.POST.get("nombre", ""), request.POST.get("sigla", ""))
                messages.success(request, f"Proceso {p.codigo} creado al final del orden.")
            elif accion in ("subir", "bajar"):
                p = get_object_or_404(Proceso, pk=request.POST.get("proceso"))
                estructura.mover_proceso(request.user, p, accion)
                p.refresh_from_db()
                messages.success(request, f"«{p.nombre}» ahora es {p.codigo}. Los códigos de sus tareas y subtareas se actualizaron.")
            elif accion == "catalogo":
                r = estructura.cargar_catalogo_base(request.user)
                messages.success(request, f"Catálogo base: {len(r['creados'])} procesos agregados al final, {len(r['ya_existian'])} ya existían."
                                 + (f" Dependencias omitidas por el orden actual: {', '.join(r['dependencias_omitidas'])}." if r["dependencias_omitidas"] else ""))
            else:
                p = get_object_or_404(Proceso, pk=request.POST.get("proceso"))
                mantenedor.renombrar_proceso(request.user, p, request.POST.get("nombre", ""), activo=request.POST.get("activo") == "on")
                messages.success(request, "Proceso guardado.")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        return redirect("mant_procesos")
    lista = list(Proceso.objects.annotate(n_tareas=Count("tareas_principales", distinct=True), n_subtareas=Count("tareas", distinct=True)).order_by("orden"))
    deps = estructura.dependencias_de()
    for p in lista:
        p.depende_de = deps.get(p.pk, [])
    return render(request, "nucleo/mant_procesos.html", {"procesos": lista, "etapas": estructura.etapas(), "hay_dependencias": bool(deps)})


def _fecha_o_none(post, clave):
    return _fecha(post.get(clave, ""))


def _plan(post, prefijo: str = "") -> estructura.DatosPlan:
    return estructura.DatosPlan(responsable_id=_entero(post.get(prefijo + "responsable")), estado_plan=post.get(prefijo + "estado_plan", "pendiente"),
                                fecha_inicio=_fecha_o_none(post, prefijo + "fecha_inicio"), fecha_termino=_fecha_o_none(post, prefijo + "fecha_termino"),
                                observaciones=post.get(prefijo + "observaciones", ""))


@con_roles(*EDITA_TAREAS)
def proceso_detalle(request, pk):
    """Un proceso: sus datos de planificación, de qué depende y sus tareas (nivel 2). Las subtareas se editan en Mantenedor → Tareas."""
    p = get_object_or_404(Proceso, pk=pk)
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "guardar":
                estructura.editar_proceso(request.user, p, request.POST.get("nombre", ""), request.POST.get("sigla", ""), _plan(request.POST))
                p.refresh_from_db()
                messages.success(request, f"Proceso {p.codigo} guardado.")
            elif accion == "dependencias":
                estructura.fijar_dependencias(request.user, p, request.POST.getlist("depende_de"))
                messages.success(request, "Dependencias guardadas.")
            elif accion == "activo":
                estructura.fijar_activo_proceso(request.user, p, request.POST.get("valor") == "1", con_hijos=request.POST.get("con_hijos") == "on")
                messages.success(request, "Estado del proceso actualizado.")
            elif accion == "tarea_crear":
                tp = estructura.crear_tarea_principal(request.user, p, request.POST.get("nombre", ""))
                messages.success(request, f"Tarea {tp.codigo} creada.")
            elif accion == "tarea_guardar":
                tp = get_object_or_404(TareaPrincipal, pk=request.POST.get("tarea"), proceso=p)
                estructura.editar_tarea_principal(request.user, tp, request.POST.get("nombre", ""), _plan(request.POST))
                messages.success(request, f"Tarea {tp.codigo} guardada.")
            elif accion == "tarea_activa":
                tp = get_object_or_404(TareaPrincipal, pk=request.POST.get("tarea"), proceso=p)
                estructura.fijar_activa_tarea_principal(request.user, tp, request.POST.get("valor") == "1", con_hijos=request.POST.get("con_hijos") == "on")
                messages.success(request, f"Tarea {tp.codigo} actualizada.")
            else:
                raise ErrorDeNegocio("Acción desconocida.")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        return redirect("mant_proceso_detalle", pk=p.pk)
    tareas = list(TareaPrincipal.objects.filter(proceso=p).select_related("responsable").annotate(n=Count("subtareas")).order_by("numero"))
    deps = estructura.dependencias_de().get(p.pk, [])
    return render(request, "nucleo/mant_proceso_detalle.html", {
        "p": p, "tareas": tareas, "cargos": Cargo.objects.filter(activo=True), "estados": ESTADOS_PLAN, "depende_de": {d.pk for d in deps}, "depende_de_lista": deps,
        "posibles": Proceso.objects.filter(orden__lt=p.orden), "dependientes": Proceso.objects.filter(dependencias__depende_de=p),
    })


# ---- Descarga y carga masiva en Excel ----------------------------------------------------------------------


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ETIQUETAS_DE_CAMPO = {
    "cargo_ejecuta": "Responsable", "cargo_revisa": "Revisa", "periodicidad_excel": "Periodicidad", "cuando_excel": "Cuándo", "regla_tipo": "Tipo de regla",
    "regla_dia_semana": "Día de la semana", "regla_n": "Día hábil del cierre", "regla_dia": "Día del mes", "regla_meses": "Meses", "regla_ajuste": "Ajuste si es inhábil",
    "regla_franja": "Franja", "referencia_normativa": "Observación", "minutos_estimados": "Minutos estimados", "minutos_revision": "Minutos de revisión", "ejecuciones_mes": "Ejecuciones al mes",
    "fuente_horas": "Quién definió las horas", "dia_cierre": "Día de cierre (Excel)", "revisa_excel": "Revisa (Excel)", "regla_estado": "Estado de la regla",
    "requiere_revision": "Requiere revisión", "motivo_revision": "Motivo de revisión", "proceso_nombre": "Proceso", "tarea_principal": "Tarea principal", "subtarea": "Subtarea",
    "dh_inicio": "Empieza el día hábil", "horas_dh": "Horas por día hábil", "horas_semana": "Horas por día de la semana", "al_terminar_cierre": "Al terminar el cierre",
    "tipo_control": "Tipo de control", "cambio_plan": "Cambio respecto del plan anterior", "justificacion": "Justificación", "modo_cierre": "En las semanas del cierre",
    "cargo_cierre": "Responsable en el cierre", "cargo_revisa_cierre": "Revisa en el cierre", "minutos_revision": "Minutos de revisión",
}


def _descarga(contenido: bytes, prefijo: str):
    r = HttpResponse(contenido, content_type=XLSX)
    r["Content-Disposition"] = f'attachment; filename="{excel_masivo.nombre_de_descarga(prefijo, reloj.hoy())}"'
    r["Cache-Control"] = "no-store"
    return r


def _archivo_subido(request) -> tuple[bytes, str]:
    f = request.FILES.get("archivo")
    if f is None:
        raise ErrorDeNegocio("Elige primero el archivo Excel.")
    return f.read(excel_masivo.MAX_BYTES + 1), f.name[:120]


@con_roles(*EDITA_TAREAS)
def tareas_exportar(request):
    contenido = excel_masivo.exportar_tareas()
    auditoria.registrar("tareas.descargadas", usuario=request.user, entidad="Tarea", despues={"filas": Tarea.objects.filter(activa=True).count()})
    return _descarga(contenido, "tareas")


@con_roles(*EDITA_TAREAS)
def procesos_exportar(request):
    return _descarga(excel_masivo.exportar_procesos(), "procesos")


def _contexto_de_la_vista_previa(vp, nombre: str) -> dict:
    cambios = [(t, f, [(ETIQUETAS_DE_CAMPO.get(k, k), "" if a is None else a, "" if d is None else d) for k, (a, d) in diff.items()]) for t, f, diff in vp.cambios]
    return {"vp": vp, "nombre_archivo": nombre, "problemas": excel_masivo.problemas_para_aplicar(vp), "cambios": cambios[:40], "mas_cambios": max(len(cambios) - 40, 0),
            "altas": vp.altas[:40], "mas_altas": max(len(vp.altas) - 40, 0), "bajas": vp.bajas[:40], "mas_bajas": max(len(vp.bajas) - 40, 0)}


@con_roles(*EDITA_TAREAS)
def tareas_cargar(request):
    """Cargar tareas en dos pasos: 1) subir el Excel y ver la vista previa; 2) confirmar. Nada se guarda en el primer paso."""
    sesion = request.session.get("carga_masiva") or {}
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "revisar":
                contenido, nombre = _archivo_subido(request)
                vp = excel_masivo.previsualizar_tareas(request.user, contenido, nombre)
                excel_masivo.borrar_en_espera(sesion.get("token", ""))
                request.session["carga_masiva"] = {"token": excel_masivo.guardar_en_espera(contenido), "nombre": nombre}
                return render(request, "nucleo/mant_tareas_cargar.html", _contexto_de_la_vista_previa(vp, nombre))
            if accion == "cancelar":
                excel_masivo.borrar_en_espera(sesion.get("token", ""))
                request.session.pop("carga_masiva", None)
                messages.success(request, "Carga cancelada: no se cambió nada.")
                return redirect("mant_tareas")
            if accion == "aplicar":
                contenido = excel_masivo.leer_en_espera(sesion.get("token", ""))
                try:
                    r = excel_masivo.aplicar_tareas(request.user, contenido, sesion.get("nombre", ""), confirma_desactivar=request.POST.get("confirmo") == "on")
                except ErrorDeNegocio as e:
                    messages.error(request, str(e))
                    vp = excel_masivo.previsualizar_tareas(request.user, contenido, sesion.get("nombre", ""))
                    return render(request, "nucleo/mant_tareas_cargar.html", _contexto_de_la_vista_previa(vp, sesion.get("nombre", "")))
                excel_masivo.borrar_en_espera(sesion.get("token", ""))
                request.session.pop("carga_masiva", None)
                messages.success(request, f"Carga aplicada: {r['altas']} tareas nuevas, {r['cambios']} modificadas y {r['bajas']} desactivadas. Rige desde el próximo mes que se abra.")
                return redirect("mant_tareas")
            raise ErrorDeNegocio("Acción desconocida.")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        return redirect("mant_tareas_cargar")
    return render(request, "nucleo/mant_tareas_cargar.html", {"vp": None})


@con_roles(*EDITA_TAREAS)
@require_POST
def procesos_cargar(request):
    try:
        contenido, nombre = _archivo_subido(request)
        r = excel_masivo.cargar_procesos(request.user, contenido, nombre)
        messages.success(request, f"Procesos cargados: {r['creados']} nuevos, {r['reordenados']} cambiaron de lugar y {r['activo_cambiado']} cambiaron de estado.")
    except PermisoDenegado as e:
        return _prohibido(request, str(e))
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    return redirect("mant_procesos")


# ---- Usuarios --------------------------------------------------------------------------------------------


@con_roles(*GESTIONA_USUARIOS)
def usuarios(request):
    hoy = reloj.hoy()
    filas = []
    for u in get_user_model().objects.order_by("username"):
        c = Colaborador.objects.filter(usuario=u).first()
        filas.append({"u": u, "rol": permisos.rol_de(u), "nombre": c.nombre if c else u.first_name, "cargo": agenda.cargos_de(c, hoy) if c else ""})
    return render(request, "nucleo/mant_usuarios.html", {"filas": filas})


def _formulario_usuario(request, usuario):
    rol_actor = permisos.rol_de(request.user)
    roles = [(r, ETIQUETAS_ROL[r]) for r in permisos.ROLES if r != permisos.ADMIN_SISTEMA or rol_actor == permisos.ADMIN_SISTEMA]
    c = Colaborador.objects.filter(usuario=usuario).first() if usuario else None
    v = {"username": usuario.get_username() if usuario else "", "nombre": (c.nombre if c else usuario.first_name) if usuario else "", "correo": usuario.email if usuario else "",
         "rol": permisos.rol_de(usuario) if usuario else "COLABORADOR", "cargo": "", "activo": usuario.is_active if usuario else True}
    if c:
        a = mantenedor._asignacion_vigente(c, reloj.hoy())
        v["cargo"] = str(a.cargo_id) if a else ""
    error = ""
    if request.method == "POST":
        v.update({"username": request.POST.get("username", v["username"]), "nombre": request.POST.get("nombre", ""), "correo": request.POST.get("correo", ""),
                  "rol": request.POST.get("rol", ""), "cargo": request.POST.get("cargo", ""), "activo": request.POST.get("activo") == "on" if usuario else True})
        try:
            if usuario is None:
                mantenedor.crear_usuario(request.user, v["username"], v["nombre"], v["correo"], v["rol"], _entero(v["cargo"]))
            else:
                mantenedor.editar_usuario(request.user, usuario, v["nombre"], v["correo"], v["rol"], _entero(v["cargo"]), v["activo"])
            messages.success(request, "Usuario guardado.")
            return redirect("mant_usuarios")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            error = str(e)
    return render(request, "nucleo/mant_usuario_form.html", {"usuario": usuario, "v": v, "error": error, "roles": roles, "cargos": Cargo.objects.filter(activo=True, es_externo=False)})


@con_roles(*GESTIONA_USUARIOS)
def usuario_nuevo(request):
    return _formulario_usuario(request, None)


@con_roles(*GESTIONA_USUARIOS)
def usuario_editar(request, pk):
    return _formulario_usuario(request, get_object_or_404(get_user_model(), pk=pk))
