"""Carga del equipo: horas estimadas contra capacidad. TODO es estimación (la mayoría base de Claude, 24 definidas por la Gerente AyF)
hasta que los colaboradores registren horas reales.

- Horas de ejecución al mes = minutos por ejecución × ejecuciones al mes.
- Horas de revisión al mes = 25 % de las horas de cada tarea que tiene revisor, y se cargan a quien revisa (como en la hoja de planificación).
- Capacidad = horas disponibles al mes por persona (160). Los cargos externos no tienen capacidad en la app.
"""
from dataclasses import dataclass, field

from nucleo.models import Cargo, Tarea
from nucleo.servicios import parametros

DIAS_DEL_CIERRE = range(1, 11)
OPERACION = ("DIARIA_HABIL", "SEMANAL")


def semaforo_de_carga(horas: float, capacidad: float) -> str:
    pct = horas * 100 / capacidad if capacidad else 0
    if pct > parametros.entero("carga_rojo"):
        return "rojo"
    return "ambar" if pct >= parametros.entero("carga_ambar") else "verde"


def _h_por_ejecucion(t: Tarea) -> float:
    return (t.minutos_estimados or 0) / 60


def _h_al_mes(t: Tarea) -> float:
    return _h_por_ejecucion(t) * float(t.ejecuciones_mes or 0)


@dataclass
class CargaCargo:
    cargo: Cargo
    capacidad: float
    tareas_ejecuta: int = 0
    tareas_revisa: int = 0
    horas_ejecucion: float = 0.0
    horas_revision: float = 0.0

    @property
    def total(self) -> float:
        return self.horas_ejecucion + self.horas_revision

    @property
    def ocupacion_pct(self) -> float:
        return round(self.total * 100 / self.capacidad, 1) if self.capacidad else 0.0

    @property
    def semaforo(self) -> str:
        return semaforo_de_carga(self.total, self.capacidad)


def _tareas_activas():
    return Tarea.objects.filter(activa=True).select_related("cargo_ejecuta", "cargo_revisa")


def por_cargo() -> list[CargaCargo]:
    capacidad = parametros.entero("horas_disponibles_mes")
    pct = parametros.entero("pct_horas_revision") / 100
    filas = {c.pk: CargaCargo(c, capacidad) for c in Cargo.objects.filter(activo=True, es_externo=False)}
    for t in _tareas_activas():
        h = _h_al_mes(t)
        if t.cargo_ejecuta_id in filas:
            filas[t.cargo_ejecuta_id].tareas_ejecuta += 1
            filas[t.cargo_ejecuta_id].horas_ejecucion += h
        if t.cargo_revisa_id in filas:
            filas[t.cargo_revisa_id].tareas_revisa += 1
            filas[t.cargo_revisa_id].horas_revision += h * pct  # también las de externos: el revisor las recibe y las revisa
    return list(filas.values())


def tareas_sin_horas() -> int:
    return _tareas_activas().filter(minutos_estimados__isnull=True).count()


@dataclass
class CargaDelCierre:
    cargo: Cargo
    horas: dict = field(default_factory=lambda: {d: 0.0 for d in DIAS_DEL_CIERRE})
    disponible_por_dia: float = 0.0

    def sobrecargados(self) -> list[int]:
        return [d for d, h in self.horas.items() if h > self.disponible_por_dia + 1e-9]


def por_dia_de_cierre() -> list[CargaDelCierre]:
    """Horas de las tareas del cierre que vencen cada día hábil (más la revisión del revisor), contra lo que deja libre la operación diaria."""
    dias = parametros.entero("dias_habiles_mes")
    capacidad_dia = parametros.entero("horas_disponibles_mes") / dias
    pct = parametros.entero("pct_horas_revision") / 100
    filas = {c.pk: CargaDelCierre(c, disponible_por_dia=capacidad_dia) for c in Cargo.objects.filter(activo=True, es_externo=False)}
    for t in _tareas_activas():
        if t.regla_tipo in OPERACION and t.cargo_ejecuta_id in filas:
            filas[t.cargo_ejecuta_id].disponible_por_dia -= _h_al_mes(t) / dias
        if t.regla_tipo == "CIERRE_DIA_HABIL" and t.regla_n in DIAS_DEL_CIERRE:
            h = _h_por_ejecucion(t)
            if t.cargo_ejecuta_id in filas:
                filas[t.cargo_ejecuta_id].horas[t.regla_n] += h
            if t.cargo_revisa_id in filas:
                filas[t.cargo_revisa_id].horas[t.regla_n] += h * pct
    return list(filas.values())
