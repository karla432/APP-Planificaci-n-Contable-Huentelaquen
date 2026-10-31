"""Qué tiene que hacer cada persona: lo suyo (atrasado, de hoy, próximo), lo que revisa y lo que recibe."""
from datetime import date, timedelta

from nucleo import permisos
from dataclasses import dataclass, field

from nucleo.models import Feriado, Ocurrencia
from nucleo.servicios import reloj
from nucleo.servicios import kpi
from nucleo.servicios.calendario import JORNADA_HORAS
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


def _de_la_persona(colaborador):
    return Ocurrencia.objects.filter(colaborador=colaborador).select_related("tarea__proceso", "cargo_ejecuta", "periodo")


def _marcar_atraso(o: Ocurrencia, hoy: date):
    o.pendiente = o.estado in PENDIENTES
    o.atrasada = o.pendiente and o.fecha_limite < hoy
    return o


@dataclass
class DiaSemana:
    fecha: date
    horas: int
    feriado: str = ""
    items: list = field(default_factory=list)


def semana_de(colaborador, referencia: date, hoy: date) -> list[DiaSemana]:
    """Lunes a viernes de la semana de `referencia`. Un feriado queda explícito y con 0 h de jornada."""
    lunes = referencia - timedelta(days=referencia.weekday())
    fechas = [lunes + timedelta(days=i) for i in range(5)]
    feriados = dict(Feriado.objects.filter(confirmado=True, fecha__in=fechas).values_list("fecha", "nombre"))
    por_dia: dict[date, list] = {f: [] for f in fechas}
    for o in _de_la_persona(colaborador).filter(fecha_limite__in=fechas).order_by("tarea__codigo"):
        por_dia[o.fecha_limite].append(_marcar_atraso(o, hoy))
    return [DiaSemana(f, 0 if f in feriados else JORNADA_HORAS[f.weekday()], feriados.get(f, ""), por_dia[f]) for f in fechas]


@dataclass
class HitoMes:
    etiqueta: str
    fecha: date
    hechas: int = 0
    total: int = 0


def mes_de(colaborador, anio: int, mes: int, hoy: date) -> dict:
    """Las tareas de la persona que vencen en el mes y su avance en los días clave del cierre."""
    ocurrencias = [_marcar_atraso(o, hoy) for o in _de_la_persona(colaborador).filter(fecha_limite__year=anio, fecha_limite__month=mes).order_by("fecha_limite", "tarea__codigo")]
    hitos = {f: HitoMes(etiqueta, f) for etiqueta, f in kpi.hitos_del_mes(anio, mes)}
    for o in ocurrencias:
        h = hitos.get(o.fecha_limite)
        if h is not None and o.tarea.regla_tipo in kpi.TIPOS_DE_CIERRE and o.estado != Ocurrencia.NO_APLICA:
            h.total += 1
            h.hechas += o.estado in kpi.HECHAS
    return {"ocurrencias": ocurrencias, "hitos": list(hitos.values())}


def cargos_de(colaborador, fecha: date) -> str:
    """Los cargos que ejerce la persona en esa fecha, como texto."""
    from nucleo.models import Asignacion
    nombres = Asignacion.objects.filter(colaborador=colaborador, desde__lte=fecha).exclude(hasta__lt=fecha).values_list("cargo__nombre", flat=True)
    return ", ".join(nombres)


def orden_de(colaborador, fecha: date) -> int:
    """Posición de la persona en las listas: la del menor `orden` entre los cargos que ejerce (100 si no tiene cargo)."""
    from nucleo.models import Asignacion
    ordenes = Asignacion.objects.filter(colaborador=colaborador, desde__lte=fecha).exclude(hasta__lt=fecha).values_list("cargo__orden", flat=True)
    return min(ordenes, default=100)
