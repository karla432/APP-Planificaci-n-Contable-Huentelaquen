"""Pantallas del Mantenedor: Tareas, Procesos y Usuarios. El permiso se valida aquí y otra vez en los servicios."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from nucleo import permisos
from nucleo.models import Cargo, Colaborador, Proceso, Tarea
from nucleo.servicios import agenda, mantenedor, reglas_texto, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado

TIPOS = [
    ("DIARIA_HABIL", "Todos los días hábiles"), ("SEMANAL", "Una vez a la semana"), ("CIERRE_DIA_HABIL", "Día hábil del cierre (1 a 10)"),
    ("CIERRE_HITO", "D7 (preliminar) o D10 (definitivo)"), ("DIA_FIJO", "Día fijo del mes"), ("FIN_DE_MES", "Último día del mes"), ("MESES", "Meses específicos"), ("EVENTO", "Por evento (se crea a mano)"),
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
    lista = list(qs.order_by("proceso__nombre", "codigo"))
    for t in lista:
        t.periodicidad = reglas_texto.describir(t.regla(), t.regla_franja)
    return render(request, "nucleo/mant_tareas.html", {"tareas": lista, "f": f, "procesos": Proceso.objects.all(), "cargos": Cargo.objects.filter(activo=True)})


def _valores_de(t: Tarea | None) -> dict:
    if t is None:
        return {"proceso": "", "tarea_principal": "", "subtarea": "", "cargo_ejecuta": "", "tipo": "CIERRE_DIA_HABIL", "dia_semana": "", "franja": "", "n": "", "dia": "",
                "meses": [], "ajuste": "siguiente", "referencia": "", "activa": True, "cargo_revisa": "", "horas": ""}
    return {"proceso": str(t.proceso_id), "tarea_principal": t.tarea_principal, "subtarea": t.subtarea, "cargo_ejecuta": str(t.cargo_ejecuta_id), "tipo": t.regla_tipo,
            "dia_semana": "" if t.regla_dia_semana is None else str(t.regla_dia_semana), "franja": t.regla_franja, "n": "" if t.regla_n is None else str(t.regla_n),
            "dia": "" if t.regla_dia is None else str(t.regla_dia), "meses": [m for m in t.regla_meses.split(",") if m], "ajuste": t.regla_ajuste,
            "referencia": t.referencia_normativa, "activa": t.activa, "cargo_revisa": str(t.cargo_revisa_id or ""),
            "horas": "" if t.minutos_estimados is None else str(round(t.minutos_estimados / 60, 2)).replace(".", ",")}


def _valores_de_post(post) -> dict:
    return {"proceso": post.get("proceso", ""), "tarea_principal": post.get("tarea_principal", ""), "subtarea": post.get("subtarea", ""), "cargo_ejecuta": post.get("cargo_ejecuta", ""),
            "tipo": post.get("tipo", ""), "dia_semana": post.get("dia_semana", ""), "franja": post.get("franja", ""), "n": post.get("n", ""), "dia": post.get("dia", ""),
            "meses": post.getlist("meses"), "ajuste": post.get("ajuste", "siguiente"), "referencia": post.get("referencia", ""), "activa": post.get("activa") == "on", "cargo_revisa": post.get("cargo_revisa", ""),
            "horas": post.get("horas", "")}


def _datos_de(v: dict) -> mantenedor.DatosTarea:
    return mantenedor.DatosTarea(
        proceso_id=_entero(v["proceso"]) or 0, tarea_principal=v["tarea_principal"], subtarea=v["subtarea"], cargo_ejecuta_id=_entero(v["cargo_ejecuta"]) or 0, tipo=v["tipo"],
        dia_semana=_entero(v["dia_semana"]), franja=v["franja"], n=_entero(v["n"]), dia=_entero(v["dia"]), meses=tuple(m for m in (_entero(x) for x in v["meses"]) if m),
        ajuste=v["ajuste"], referencia=v["referencia"], activa=v["activa"], cargo_revisa_id=_entero(v["cargo_revisa"]), minutos=_minutos(v["horas"]),
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
        "tipos": TIPOS, "dias": DIAS, "meses": MESES,
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
        try:
            if request.POST.get("accion") == "crear":
                mantenedor.crear_proceso(request.user, request.POST.get("nombre", ""))
            else:
                p = get_object_or_404(Proceso, pk=request.POST.get("proceso"))
                mantenedor.renombrar_proceso(request.user, p, request.POST.get("nombre", ""), activo=request.POST.get("activo") == "on")
            messages.success(request, "Proceso guardado.")
        except PermisoDenegado as e:
            return _prohibido(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        return redirect("mant_procesos")
    return render(request, "nucleo/mant_procesos.html", {"procesos": Proceso.objects.annotate(n_tareas=Count("tareas")).order_by("nombre")})


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
