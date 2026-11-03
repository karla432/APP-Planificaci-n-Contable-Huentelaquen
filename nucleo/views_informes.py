"""Menú Informes: panel del cierre y cumplimiento por colaborador. Visibles para todo el equipo, solo lectura."""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from nucleo import permisos
from nucleo.models import Feriado, Ocurrencia, Periodo, Proceso
from nucleo.servicios import agenda, carga, kpi, parametros, presentacion, reloj
from nucleo.servicios.feriados import calendario_confirmado
from nucleo.views_mantenedor import con_roles


def _sin_perfil(request):
    return render(request, "nucleo/sin_perfil.html", status=403)


def _mes_elegido(request, hoy: date):
    try:
        anio, m = (int(x) for x in request.GET.get("mes", "").split("-"))
        primero = date(anio, m, 1)
    except ValueError:
        primero = hoy.replace(day=1)
    return primero, Periodo.objects.filter(anio=primero.year, mes=primero.month).first()


def _navegacion(primero: date) -> dict:
    return {
        "primero": primero, "mes_anterior": (primero - timedelta(days=1)).replace(day=1).strftime("%Y-%m"),
        "mes_siguiente": (primero + timedelta(days=32)).replace(day=1).strftime("%Y-%m"),
    }


def _fecha_iso(texto: str | None):
    try:
        return date.fromisoformat(texto or "")
    except ValueError:
        return None


def _filas_cumplimiento(periodo, hoy: date) -> list[dict]:
    filas = []
    for k in kpi.por_colaborador(periodo, hoy):
        texto, clase = presentacion.etiqueta_semaforo(k.semaforo)
        filas.append({"k": k, "cargos": agenda.cargos_de(k.colaborador, hoy), "etiqueta": texto, "clase": clase, "orden": agenda.orden_de(k.colaborador, hoy)})
    return sorted(filas, key=lambda f: (f["orden"], f["k"].colaborador.nombre))


@login_required
def panel(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    c = {"hoy": hoy, "meta": parametros.entero("meta_cumplimiento"), **_navegacion(primero), "periodo": periodo}
    if periodo is not None:
        cal = calendario_confirmado()
        entregas = kpi.entregas(periodo.anio, periodo.mes)
        atencion_titulo, atencion_grupos = agenda.atencion_por_responsable(request.user, periodo, hoy)
        ver = request.GET.get("ver", "")
        fecha_pinchada = _fecha_iso(request.GET.get("fecha"))
        if ver in kpi.VISTAS_DE_LISTADO or fecha_pinchada:
            titulo = kpi.VISTAS_DE_LISTADO.get(ver) or f"Tareas del cierre del {fecha_pinchada:%d-%m-%Y}"
            c["listado"] = {"titulo": titulo, "tareas": kpi.tareas_del_cierre(periodo, hoy, ver=ver, fecha=fecha_pinchada), "ver": ver, "fecha": fecha_pinchada}
        ordinal = sum(1 for d in cal.dias_habiles_del_mes(periodo.anio, periodo.mes) if d <= hoy)
        c.update({
            "ruta": kpi.ruta_del_cierre(periodo, hoy), "resumen": kpi.resumen(periodo, hoy), "procesos": kpi.avance_por_proceso(periodo, hoy),
            "dia_habil": ordinal, "atencion_titulo": atencion_titulo, "atencion_grupos": atencion_grupos,
            "feriados_mes": list(Feriado.objects.filter(confirmado=True, fecha__year=periodo.anio, fecha__month=periodo.mes)),
            "faltan_cierre": None if hoy > entregas[8] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, entregas[8])),
            "faltan_directorio": None if hoy > entregas[10] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, entregas[10])),
            "entregas": entregas,
            "atrasadas": list(Ocurrencia.objects.filter(periodo=periodo, estado=Ocurrencia.PENDIENTE, fecha_limite__lt=hoy, tarea__regla_tipo__in=kpi.TIPOS_DE_CIERRE)
                              .select_related("tarea__proceso", "colaborador", "cargo_ejecuta").order_by("fecha_limite", "tarea__codigo")[:8]),
        })
    return render(request, "nucleo/informe_panel.html", c)


@login_required
def cumplimiento(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    c = {"hoy": hoy, "meta": parametros.entero("meta_cumplimiento"), "periodo": periodo, **_navegacion(primero)}
    if periodo is not None:
        c.update({"cumplimiento": _filas_cumplimiento(periodo, hoy), "insumos": kpi.insumos_por_cargo_externo(periodo, hoy), "revision": kpi.cumplimiento_de_revision(periodo, hoy)})
    return render(request, "nucleo/informe_cumplimiento.html", c)


@login_required
def carga_del_equipo(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    filas = carga.por_cargo()
    etiquetas = {"verde": ("Dentro de su capacidad", "ok"), "ambar": ("Al límite", "warn"), "rojo": ("Sobrecargado", "red")}
    for f in filas:
        f.etiqueta, f.clase = etiquetas[f.semaforo]
    mas_cargado = max(filas, key=lambda f: f.total, default=None)
    hoy = reloj.hoy()
    cierre = carga.por_dia_de_cierre(hoy.year, hoy.month)
    periodo = Periodo.objects.filter(anio=hoy.year, mes=hoy.month).first() or Periodo.objects.first()
    reales = sorted(carga.real_vs_estimado(periodo), key=lambda f: (agenda.orden_de(f.colaborador, hoy), f.colaborador.nombre)) if periodo else []
    return render(request, "nucleo/informe_carga.html", {
        "periodo": periodo, "reales": reales,
        "filas": filas, "mas_cargado": mas_cargado, "cierre": cierre, "dias": carga.dias_del_cierre(hoy.year, hoy.month), "sin_horas": carga.tareas_sin_horas(),
        "capacidad": parametros.entero("horas_disponibles_mes"),
    })


TITULOS_DEL_TABLERO = [("pendiente", "Pendiente"), ("bloqueada", "Bloqueada"), ("por_revisar", "Por revisar"), ("hecha", "Hecha o revisada"), ("devuelta", "Devuelta")]


def columna_del_tablero(o) -> str:
    if o.estado == Ocurrencia.BLOQUEADA:
        return "bloqueada"
    if o.estado == Ocurrencia.DEVUELTA:
        return "devuelta"
    if o.estado == Ocurrencia.PENDIENTE:
        return "pendiente"
    if o.estado == Ocurrencia.HECHA and o.tipo_marca == "HECHA" and o.cargo_revisa_id is not None:
        return "por_revisar"  # una hecha sin revisor no espera revisión: queda hecha
    return "hecha"


def _cierre_del_mes(periodo):
    return (Ocurrencia.objects.filter(periodo=periodo, tarea__regla_tipo__in=kpi.TIPOS_DE_CIERRE).exclude(estado=Ocurrencia.NO_APLICA)
            .select_related("tarea__proceso", "cargo_ejecuta", "colaborador", "cargo_revisa"))


@login_required
def tablero(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    c = {"hoy": hoy, "periodo": periodo, **_navegacion(primero), "procesos": Proceso.objects.filter(activo=True), "f_proceso": request.GET.get("proceso", ""),
         "solo_mias": request.GET.get("solo_mias") == "1"}
    if periodo is not None:
        qs = _cierre_del_mes(periodo)
        if c["f_proceso"]:
            qs = qs.filter(tarea__proceso_id=c["f_proceso"])
        propia = permisos.colaborador_de(request.user)
        if c["solo_mias"] and propia is not None:
            qs = qs.filter(colaborador=propia)
        columnas = {k: [] for k, _ in TITULOS_DEL_TABLERO}
        for o in qs.order_by("fecha_limite", "tarea__secuencia", "tarea__codigo"):
            o.atrasada = o.estado in kpi.SIN_HACER + (Ocurrencia.DEVUELTA,) and o.fecha_limite < hoy
            o.dia_cierre = o.regla_copia.get("n")
            columnas[columna_del_tablero(o)].append(o)
        abiertas = sum(len(columnas[k]) for k in ("pendiente", "bloqueada", "devuelta"))
        c.update({"columnas": [(titulo, columnas[k]) for k, titulo in TITULOS_DEL_TABLERO], "abiertas": abiertas,
                  "atrasadas": sum(o.atrasada for k in ("pendiente", "bloqueada", "devuelta") for o in columnas[k])})
    return render(request, "nucleo/informe_tablero.html", c)


VISTAS_DEL_CRONOGRAMA = [("cierre", "Cierre (hasta el día 10)"), ("semana", "Semana"), ("mes", "Mes completo")]
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _clase_de_celda(ocs, hoy: date) -> str:
    if any(o.estado in kpi.SIN_HACER + (Ocurrencia.DEVUELTA,) and o.fecha_limite < hoy for o in ocs):
        return "rd"
    if all(o.estado in kpi.HECHAS or o.estado == "recibida" for o in ocs):
        return "ok"
    return "wr" if ocs[0].fecha_limite <= hoy else "gr"


@login_required
def cronograma(request):
    """Procesos (por código, de menor a mayor) por días: el cierre, una semana o el mes completo. Cada número es la cantidad de tareas del día."""
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    vista = request.GET.get("vista") if request.GET.get("vista") in dict(VISTAS_DEL_CRONOGRAMA) else "cierre"
    c = {"hoy": hoy, "periodo": periodo, **_navegacion(primero), "vista": vista, "vistas": VISTAS_DEL_CRONOGRAMA}
    if periodo is None:
        return render(request, "nucleo/informe_cronograma.html", c)
    cal = calendario_confirmado()
    descripciones = kpi.descripciones_del_mes(periodo.anio, periodo.mes)
    habiles_cierre = {f: n for n, (_, f) in enumerate(kpi.hitos_del_mes(periodo.anio, periodo.mes), start=1)}
    todas = Ocurrencia.objects.filter(periodo=periodo).exclude(estado=Ocurrencia.NO_APLICA).select_related("tarea__proceso", "cargo_ejecuta", "colaborador", "cargo_revisa")
    if vista == "cierre":
        fechas, ocurrencias = list(habiles_cierre), _cierre_del_mes(periodo)
        c["titulo"] = "Del día hábil 1 hasta la entrega al Directorio (día 10); los reportes quedan listos en la tarde del día 8 y el día 9 va al Gerente General."
    elif vista == "mes":
        fechas, ocurrencias = cal.dias_habiles_del_mes(periodo.anio, periodo.mes), todas
        c["titulo"] = "Todos los días hábiles del mes, con todas las tareas (cierre y operación)."
    else:
        try:
            referencia = date.fromisoformat(request.GET.get("fecha", ""))
        except ValueError:
            referencia = hoy if (hoy.year, hoy.month) == (primero.year, primero.month) else primero
        lunes = referencia - timedelta(days=referencia.weekday())
        fechas, ocurrencias = [lunes + timedelta(days=i) for i in range(5)], todas
        c.update({"lunes": lunes, "viernes": lunes + timedelta(days=4), "fecha_anterior": (lunes - timedelta(days=7)).isoformat(), "fecha_siguiente": (lunes + timedelta(days=7)).isoformat()})
        c["titulo"] = "Una semana, de lunes a viernes, con todas las tareas (cierre y operación)."
    columnas = [{"fecha": f, "n": habiles_cierre.get(f), "etiqueta": f"Día {habiles_cierre[f]}" if vista == "cierre" else f"{DIAS_CORTOS[f.weekday()]} {f:%d}", "descripcion": descripciones.get(f, ""),
                 "feriado": cal.es_feriado(f)} for f in fechas]
    celdas, procesos = {}, {}
    visibles = set(fechas)
    for o in ocurrencias:
        if o.fecha_limite not in visibles:
            continue
        procesos[o.tarea.proceso.pk] = o.tarea.proceso
        celdas.setdefault((o.tarea.proceso.pk, o.fecha_limite), []).append(o)
    filas = []
    for proceso in sorted(procesos.values(), key=lambda p: (p.orden, p.nombre)):  # por código del proceso, de menor a mayor
        celdas_fila = []
        for col in columnas:
            ocs = celdas.get((proceso.pk, col["fecha"]), [])
            celdas_fila.append({"n": len(ocs), "clase": _clase_de_celda(ocs, hoy), "col": col} if ocs else None)
        filas.append({"proceso": proceso, "celdas": celdas_fila})
    seleccion = None
    if request.GET.get("proceso") and request.GET.get("dia"):
        try:
            pk = int(request.GET["proceso"])
            dia = request.GET["dia"]
            fecha = date.fromisoformat(dia) if "-" in dia else next(f for f, n in habiles_cierre.items() if n == int(dia))
            seleccion = {"proceso": Proceso.objects.get(pk=pk), "dia": dia, "fecha": fecha, "etiqueta": f"Día {habiles_cierre[fecha]}" if fecha in habiles_cierre else f"{fecha:%d-%m-%Y}",
                         "tareas": celdas.get((pk, fecha), [])}
        except (ValueError, StopIteration, Proceso.DoesNotExist):
            seleccion = None
    c.update({"columnas": columnas, "filas": filas, "seleccion": seleccion, "feriados_mes": list(Feriado.objects.filter(confirmado=True, fecha__year=periodo.anio, fecha__month=periodo.mes))})
    return render(request, "nucleo/informe_cronograma.html", c)


# ---- Matriz del cierre ----------------------------------------------------------------------------------------------


def _mes_de_la_matriz(request, hoy: date) -> tuple[int, int]:
    try:
        anio, mes = (int(x) for x in request.GET.get("mes", "").split("-"))
        date(anio, mes, 1)
        return anio, mes
    except ValueError:
        return hoy.year, hoy.month


def _clase_de_horas(horas: float, capacidad: float, techo: float = 0.9) -> str:
    if horas > capacidad + 1e-9:
        return "rd"
    if capacidad and horas > capacidad * techo + 1e-9:  # pasa el techo de planificación: se usa la reserva
        return "wr"
    return "ok" if horas else "gr"


def _tabla_de_matriz(m) -> list[dict]:
    return [{"fila": f, "celdas": [{"fecha": d, "horas": f.horas[d], "capacidad": f.capacidad[d], "clase": _clase_de_horas(f.horas[d], f.capacidad[d], m.techo(d))} for d in m.dias]} for f in m.filas]


@con_roles(permisos.GERENTE, permisos.JEFATURA)
def matriz_del_cierre(request):
    """Quién hace qué cada día de la semana del cierre, contra su jornada, y una propuesta para equilibrar al equipo. Para revisar antes de entregar."""
    from nucleo.servicios import matriz
    hoy = reloj.hoy()
    anio, mes = _mes_de_la_matriz(request, hoy)
    primero = date(anio, mes, 1)
    if request.GET.get("ver") != "propuesta":  # lo normal: el plan vigente (la Planificación 2.0); la propuesta de equilibrio es opcional
        m = matriz.construir(anio, mes)
        return render(request, "nucleo/informe_matriz_plan.html", {
            "primero": primero, "anio": anio, "mes": mes, "mes_param": f"{anio}-{mes:02d}", **_navegacion(primero), "m": m, "tabla": _tabla_de_matriz(m), "dias": m.dias,
            "etiquetas": {d: m.etiqueta(d) for d in m.dias}, "diagnostico": matriz.diagnostico_del_plan(m), "hitos": matriz.hitos_del_plan(m),
            "dependencias": matriz.dependencias_incumplidas(m), "alertas": m.alertas(), "hasta": m.ctx.hasta,
        })
    prop = matriz.proponer(anio, mes)
    return render(request, "nucleo/informe_matriz.html", {
        "primero": primero, "anio": anio, "mes": mes, "mes_param": f"{anio}-{mes:02d}", **_navegacion(primero), "prop": prop,
        "tablas": [("Como está hoy", _tabla_de_matriz(prop.antes)), ("Propuesta", _tabla_de_matriz(prop.despues))], "resumen": list(zip(prop.antes.filas, prop.despues.filas)), "dias": prop.antes.dias,
        "etiquetas": {d: prop.antes.etiqueta(d) for d in prop.antes.dias}, "alertas": prop.despues.alertas(), "faltan": round(max(0.0, prop.despues.horas_semana_cierre - prop.despues.capacidad_semana_cierre), 1),
        "diagnostico": matriz.diagnostico(prop), "cambios": prop.cambios[:12], "mas_cambios": max(len(prop.cambios) - 12, 0), "hasta": prop.antes.ctx.hasta,
    })


@con_roles(permisos.GERENTE, permisos.JEFATURA)
def matriz_exportar(request):
    anio, mes = _mes_de_la_matriz(request, reloj.hoy())
    from nucleo.servicios import auditoria, excel_masivo
    contenido = excel_masivo.exportar_matriz(anio, mes)
    auditoria.registrar("matriz.descargada", usuario=request.user, entidad="Periodo", entidad_id=f"{mes:02d}-{anio}")
    r = HttpResponse(contenido, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="matriz_del_cierre_{anio}-{mes:02d}.xlsx"'
    r["Cache-Control"] = "no-store"
    return r
