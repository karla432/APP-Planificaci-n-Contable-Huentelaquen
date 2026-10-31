"""Menú Informes: panel del cierre y cumplimiento por colaborador. Visibles para todo el equipo, solo lectura."""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from nucleo import permisos
from nucleo.models import Feriado, Ocurrencia, Periodo, Proceso
from nucleo.servicios import agenda, carga, kpi, parametros, presentacion, reloj
from nucleo.servicios.feriados import calendario_confirmado


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
        hitos = dict(kpi.hitos_del_mes(periodo.anio, periodo.mes))
        ordinal = sum(1 for d in cal.dias_habiles_del_mes(periodo.anio, periodo.mes) if d <= hoy)
        c.update({
            "ruta": kpi.ruta_del_cierre(periodo, hoy), "resumen": kpi.resumen(periodo, hoy), "procesos": kpi.avance_por_proceso(periodo, hoy),
            "cumplimiento": _filas_cumplimiento(periodo, hoy), "dia_habil": ordinal,
            "atencion_titulo": agenda.atencion(request.user, periodo, hoy)[0], "atencion": agenda.atencion(request.user, periodo, hoy)[1],
            "feriados_mes": list(Feriado.objects.filter(confirmado=True, fecha__year=periodo.anio, fecha__month=periodo.mes)),
            "faltan_cierre": None if hoy > hitos["Día 8"] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, hitos["Día 8"])),
            "faltan_directorio": None if hoy > hitos["Día 10"] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, hitos["Día 10"])),
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
    cierre = carga.por_dia_de_cierre()
    hoy = reloj.hoy()
    periodo = Periodo.objects.filter(anio=hoy.year, mes=hoy.month).first() or Periodo.objects.first()
    reales = sorted(carga.real_vs_estimado(periodo), key=lambda f: (agenda.orden_de(f.colaborador, hoy), f.colaborador.nombre)) if periodo else []
    return render(request, "nucleo/informe_carga.html", {
        "periodo": periodo, "reales": reales,
        "filas": filas, "mas_cargado": mas_cargado, "cierre": cierre, "dias": carga.DIAS_DEL_CIERRE, "sin_horas": carga.tareas_sin_horas(),
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


@login_required
def cronograma(request):
    if permisos.rol_de(request.user) is None:
        return _sin_perfil(request)
    hoy = reloj.hoy()
    primero, periodo = _mes_elegido(request, hoy)
    c = {"hoy": hoy, "periodo": periodo, **_navegacion(primero)}
    if periodo is not None:
        hitos = kpi.hitos_del_mes(periodo.anio, periodo.mes)
        dia_de = {f: int(etiqueta.split()[1]) for etiqueta, f in hitos}
        celdas, orden = {}, {}
        for o in _cierre_del_mes(periodo):
            n = dia_de.get(o.fecha_limite)
            if n is None:
                continue
            proceso = o.tarea.proceso
            orden[proceso.pk] = min(orden.get(proceso.pk, (10**9, "")), (o.tarea.secuencia, o.tarea.codigo))
            celdas.setdefault((proceso.pk, n), []).append(o)
        filas = []
        for pk in sorted(orden, key=orden.get):
            proceso = Proceso.objects.get(pk=pk)
            cel = {}
            for n in range(1, 11):
                ocs = celdas.get((pk, n), [])
                if not ocs:
                    continue
                if any(o.estado in kpi.SIN_HACER + (Ocurrencia.DEVUELTA,) and o.fecha_limite < hoy for o in ocs):
                    clase = "rd"
                elif all(o.estado in kpi.HECHAS or o.estado == "recibida" for o in ocs):
                    clase = "ok"
                elif ocs[0].fecha_limite <= hoy:
                    clase = "wr"
                else:
                    clase = "gr"
                cel[n] = {"n": len(ocs), "clase": clase}
            filas.append({"proceso": proceso, "celdas": cel})
        seleccion = None
        if request.GET.get("proceso") and request.GET.get("dia"):
            try:
                pk, n = int(request.GET["proceso"]), int(request.GET["dia"])
                seleccion = {"proceso": Proceso.objects.get(pk=pk), "dia": n, "tareas": celdas.get((pk, n), [])}
            except (ValueError, Proceso.DoesNotExist):
                seleccion = None
        c.update({"hitos": [(etiqueta, f, kpi.descripcion_del_hito(int(etiqueta.split()[1]))) for etiqueta, f in hitos], "filas": filas, "dias": range(1, 11), "seleccion": seleccion,
                  "feriados_mes": list(Feriado.objects.filter(confirmado=True, fecha__year=periodo.anio, fecha__month=periodo.mes))})
    return render(request, "nucleo/informe_cronograma.html", c)
