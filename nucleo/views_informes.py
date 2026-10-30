"""Menú Informes: panel del cierre y cumplimiento por colaborador. Visibles para todo el equipo, solo lectura."""
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from nucleo import permisos
from nucleo.models import Feriado, Ocurrencia, Periodo
from nucleo.servicios import agenda, kpi, parametros, presentacion, reloj
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
        filas.append({"k": k, "cargos": agenda.cargos_de(k.colaborador, hoy), "etiqueta": texto, "clase": clase})
    return filas


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
            "feriados_mes": list(Feriado.objects.filter(confirmado=True, fecha__year=periodo.anio, fecha__month=periodo.mes)),
            "faltan_d7": None if hoy > hitos["D7"] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, hitos["D7"])),
            "faltan_d10": None if hoy > hitos["D10"] else presentacion.dias_habiles_texto(cal.dias_habiles_entre(hoy, hitos["D10"])),
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
