"""Qué tiene que hacer cada persona: lo suyo (atrasado, de hoy, próximo), lo que revisa y lo que recibe."""
from datetime import date, timedelta

from nucleo import permisos
from nucleo.models import Ocurrencia
from nucleo.servicios import reloj
from nucleo.servicios.feriados import calendario_confirmado

PENDIENTES = (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA)
DIAS_PROXIMOS = 7


def _abiertas():
    return Ocurrencia.objects.filter(periodo__estado="abierto").select_related("tarea__proceso", "cargo_ejecuta", "colaborador", "periodo")


def atraso_en_dias_habiles(o: Ocurrencia, hoy: date) -> int:
    return calendario_confirmado().dias_habiles_entre(o.fecha_limite, hoy) if o.fecha_limite < hoy else 0


def agenda_de(colaborador, hoy: date | None = None) -> dict:
    hoy = hoy or reloj.hoy()
    mias = _abiertas().filter(colaborador=colaborador, estado__in=PENDIENTES)
    atrasadas = list(mias.filter(fecha_limite__lt=hoy))
    for o in atrasadas:
        o.atraso = atraso_en_dias_habiles(o, hoy)
    return {
        "atrasadas": atrasadas,
        "hoy": list(mias.filter(fecha_limite=hoy)),
        "proximas": list(mias.filter(fecha_limite__gt=hoy, fecha_limite__lte=hoy + timedelta(days=DIAS_PROXIMOS))),
    }


def por_revisar(usuario, hoy: date | None = None) -> list[Ocurrencia]:
    cargos = permisos.cargos_vigentes_de(usuario)
    return list(_abiertas().filter(cargo_revisa_id__in=cargos, estado=Ocurrencia.HECHA, tipo_marca="HECHA").exclude(hecha_por=usuario))


def por_recibir(usuario, hoy: date | None = None) -> list[Ocurrencia]:
    hoy = hoy or reloj.hoy()
    cargos = permisos.cargos_vigentes_de(usuario)
    return list(_abiertas().filter(cargo_revisa_id__in=cargos, estado__in=PENDIENTES, tipo_marca="RECIBIDA", fecha_limite__lte=hoy + timedelta(days=DIAS_PROXIMOS)))
