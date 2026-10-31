"""Indicadores de cumplimiento (docs/f1/03_kpi_roles_sod.md §1). Fuente única: las ocurrencias del período.

- «Vencida» = su fecha límite es anterior a hoy (vence al final del día hábil de la fecha límite).
- «A tiempo» = la PRIMERA marca `hecha` cae, en hora de Chile, en o antes de la fecha límite. Una tarea hecha tarde nunca suma;
  una devuelta conserva su resultado original.
- Las `no_aplica` aprobadas salen del denominador. Las tareas de cargos externos no entran al KPI de nadie: se miden aparte.
- Sin datos suficientes se dice «sin datos» o «muestra insuficiente»: no se calcula nada inventado.
"""
from dataclasses import dataclass
from datetime import date

from django.utils import timezone

from nucleo.models import Cargo, Ocurrencia
from nucleo.servicios import parametros
from nucleo.servicios.feriados import calendario_confirmado

TIPOS_DE_CIERRE = ("CIERRE_DIA_HABIL", "CIERRE_HITO")
HECHAS = (Ocurrencia.HECHA, Ocurrencia.REVISADA)
SIN_HACER = (Ocurrencia.PENDIENTE, Ocurrencia.BLOQUEADA)  # una bloqueada sigue sin hacer


def _dia_local(instante) -> date:
    return timezone.localtime(instante).date()


def _pct(parte: int, total: int):
    return None if total == 0 else round(parte * 100 / total, 1)


def semaforo(a_tiempo: int, vencidas: int) -> str:
    """verde / ambar / rojo, o «sin_datos» / «muestra_insuficiente». Comparación exacta con enteros (sin redondeos)."""
    if vencidas == 0:
        return "sin_datos"
    if vencidas < parametros.entero("minimo_muestra_semaforo"):
        return "muestra_insuficiente"
    if a_tiempo * 100 >= parametros.entero("meta_cumplimiento") * vencidas:
        return "verde"
    if a_tiempo * 100 >= parametros.entero("umbral_ambar") * vencidas:
        return "ambar"
    return "rojo"


@dataclass
class KpiPersona:
    colaborador: object
    vencidas: int = 0
    a_tiempo: int = 0
    completas: int = 0
    pendientes_vencidas: int = 0
    no_aplica: int = 0
    vencidas_con_no_aplica: int = 0
    con_primera_hecha: int = 0
    devueltas: int = 0

    @property
    def a_tiempo_pct(self):
        return _pct(self.a_tiempo, self.vencidas)

    @property
    def completitud_pct(self):
        return _pct(self.completas, self.vencidas)

    @property
    def tasa_devolucion_pct(self):
        return _pct(self.devueltas, self.con_primera_hecha)

    @property
    def tasa_no_aplica_pct(self):
        return _pct(self.no_aplica, self.vencidas_con_no_aplica)

    @property
    def semaforo(self):
        return semaforo(self.a_tiempo, self.vencidas)


def _a_tiempo(o: Ocurrencia) -> bool:
    return o.primera_hecha_en is not None and _dia_local(o.primera_hecha_en) <= o.fecha_limite


def por_colaborador(periodo, hoy: date) -> list[KpiPersona]:
    filas: dict[int, KpiPersona] = {}
    for o in Ocurrencia.objects.filter(periodo=periodo, colaborador__isnull=False).select_related("colaborador"):
        k = filas.setdefault(o.colaborador_id, KpiPersona(o.colaborador))
        if o.primera_hecha_en is not None:
            k.con_primera_hecha += 1
            if o.veces_devuelta > 0:
                k.devueltas += 1
        if o.fecha_limite >= hoy:
            continue
        k.vencidas_con_no_aplica += 1
        if o.estado == Ocurrencia.NO_APLICA:
            k.no_aplica += 1
            continue
        k.vencidas += 1
        k.a_tiempo += _a_tiempo(o)
        k.completas += o.primera_hecha_en is not None
        k.pendientes_vencidas += o.estado in SIN_HACER
    return sorted(filas.values(), key=lambda k: k.colaborador.nombre)


@dataclass
class InsumoCargo:
    cargo: Cargo
    vencidas: int = 0
    a_tiempo: int = 0

    @property
    def a_tiempo_pct(self):
        return _pct(self.a_tiempo, self.vencidas)


def insumos_por_cargo_externo(periodo, hoy: date) -> list[InsumoCargo]:
    """«Cumplimiento de insumos por área»: lo que recibe la Jefa de los responsables externos. No entra al KPI de nadie."""
    filas: dict[int, InsumoCargo] = {}
    for o in Ocurrencia.objects.filter(periodo=periodo, cargo_ejecuta__es_externo=True, fecha_limite__lt=hoy).exclude(estado=Ocurrencia.NO_APLICA).select_related("cargo_ejecuta"):
        i = filas.setdefault(o.cargo_ejecuta_id, InsumoCargo(o.cargo_ejecuta))
        i.vencidas += 1
        i.a_tiempo += _a_tiempo(o)
    return sorted(filas.values(), key=lambda i: i.cargo.nombre)


@dataclass
class RevisionCargo:
    cargo: Cargo
    debidas: int = 0
    a_tiempo: int = 0

    @property
    def a_tiempo_pct(self):
        return _pct(self.a_tiempo, self.debidas)


def cumplimiento_de_revision(periodo, hoy: date) -> list[RevisionCargo]:
    """Revisiones hechas dentro del plazo ÷ revisiones debidas, por cargo revisor. El plazo es un parámetro (propuesta de Legión)."""
    cal, dias = calendario_confirmado(), parametros.entero("plazo_revision_dias_habiles")
    filas: dict[int, RevisionCargo] = {}
    qs = Ocurrencia.objects.filter(periodo=periodo, tipo_marca="HECHA", cargo_revisa__isnull=False, primera_hecha_en__isnull=False).exclude(estado=Ocurrencia.NO_APLICA).select_related("cargo_revisa")
    for o in qs:
        plazo = cal.sumar_dias_habiles(_dia_local(o.primera_hecha_en), dias)
        if plazo >= hoy:
            continue
        r = filas.setdefault(o.cargo_revisa_id, RevisionCargo(o.cargo_revisa))
        r.debidas += 1
        r.a_tiempo += o.primera_revision_en is not None and _dia_local(o.primera_revision_en) <= plazo
    return sorted(filas.values(), key=lambda r: r.cargo.nombre)


@dataclass
class RutaDia:
    etiqueta: str
    fecha: date
    descripcion: str = ""
    hechas: int = 0
    total: int = 0
    atrasadas: int = 0

    @property
    def estado(self) -> str:
        if self.atrasadas:
            return "atrasada"
        return "al_dia" if self.total and self.hechas == self.total else "en_curso"


def _cierre(periodo):
    return Ocurrencia.objects.filter(periodo=periodo, tarea__regla_tipo__in=TIPOS_DE_CIERRE).exclude(estado=Ocurrencia.NO_APLICA)


DESCRIPCION_DE_HITOS = {8: "Cierre completo", 9: "Revisión con Gerencia General", 10: "Informes al Directorio"}


def descripcion_del_hito(n: int) -> str:
    return DESCRIPCION_DE_HITOS.get(n, "")


def hitos_del_mes(anio: int, mes: int) -> list[tuple[str, date]]:
    """Los días clave del cierre (Karla, 31-10-2026): días hábiles 1 a 10. Del 1 al 8 se cierra, el 9 se revisa con la Gerencia General
    y el 10 se liberan los informes al Directorio."""
    cal = calendario_confirmado()
    return [(f"Día {n}", cal.dia_habil_n(anio, mes, n)) for n in range(1, 11)]


def ruta_del_cierre(periodo, hoy: date) -> list[RutaDia]:
    dias = hitos_del_mes(periodo.anio, periodo.mes)
    ruta = {f: RutaDia(etiqueta, f, descripcion_del_hito(int(etiqueta.split()[1]))) for etiqueta, f in dias}
    for o in _cierre(periodo):
        r = ruta.get(o.fecha_limite)
        if r is None:
            continue
        r.total += 1
        r.hechas += o.estado in HECHAS
        r.atrasadas += o.estado in SIN_HACER and o.fecha_limite < hoy
    return [ruta[f] for _, f in dias]


@dataclass
class Resumen:
    hechas: int = 0
    total: int = 0
    atrasadas: int = 0
    vencen_hoy: int = 0
    equipo_a_tiempo: int = 0
    equipo_vencidas: int = 0
    revisadas: int = 0
    por_revisar: int = 0
    pendientes: int = 0
    bloqueadas: int = 0
    vencen_a_la_fecha: int = 0

    @property
    def avance_pct(self):
        return _pct(self.hechas, self.total)

    @property
    def plan_pct(self):
        """Lo que el plan esperaba a hoy: tareas del cierre cuya fecha límite ya llegó, sobre el total."""
        return _pct(self.vencen_a_la_fecha, self.total)

    @property
    def diferencia_con_el_plan(self):
        if self.total == 0:
            return None
        return round(self.avance_pct - self.plan_pct)

    @property
    def equipo_a_tiempo_pct(self):
        return _pct(self.equipo_a_tiempo, self.equipo_vencidas)


def resumen(periodo, hoy: date) -> Resumen:
    r = Resumen()
    for o in _cierre(periodo):
        r.total += 1
        r.hechas += o.estado in HECHAS
        r.atrasadas += o.estado in SIN_HACER and o.fecha_limite < hoy
        r.vencen_hoy += o.estado in SIN_HACER and o.fecha_limite == hoy
        r.vencen_a_la_fecha += o.fecha_limite <= hoy
        r.revisadas += o.estado == Ocurrencia.REVISADA
        r.por_revisar += o.estado == Ocurrencia.HECHA and o.tipo_marca == "HECHA" and o.cargo_revisa_id is not None
        r.pendientes += o.estado in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA)
        r.bloqueadas += o.estado == Ocurrencia.BLOQUEADA
    for k in por_colaborador(periodo, hoy):
        r.equipo_a_tiempo += k.a_tiempo
        r.equipo_vencidas += k.vencidas
    return r


@dataclass
class AvanceProceso:
    proceso: str
    hechas: int = 0
    total: int = 0
    estado: str = "al_dia"  # al_dia / por_vencer / atrasado


def avance_por_proceso(periodo, hoy: date) -> list[AvanceProceso]:
    filas: dict[str, AvanceProceso] = {}
    for o in _cierre(periodo).select_related("tarea__proceso"):
        a = filas.setdefault(o.tarea.proceso.nombre, AvanceProceso(o.tarea.proceso.nombre))
        a.total += 1
        a.hechas += o.estado in HECHAS
        if o.estado in SIN_HACER:
            if o.fecha_limite < hoy:
                a.estado = "atrasado"
            elif a.estado != "atrasado":
                a.estado = "por_vencer"
    return sorted(filas.values(), key=lambda a: a.proceso)


def de_persona(colaborador, hoy: date) -> KpiPersona:
    """El cumplimiento de una persona sumando todos los meses abiertos (puede haber dos al mismo tiempo, ej. noviembre y diciembre)."""
    from nucleo.models import Periodo
    total = KpiPersona(colaborador)
    for periodo in Periodo.objects.filter(estado="abierto"):
        for k in por_colaborador(periodo, hoy):
            if k.colaborador.pk == colaborador.pk:
                for campo in ("vencidas", "a_tiempo", "completas", "pendientes_vencidas", "no_aplica", "vencidas_con_no_aplica", "con_primera_hecha", "devueltas"):
                    setattr(total, campo, getattr(total, campo) + getattr(k, campo))
    return total
