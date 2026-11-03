"""Carga del equipo: horas estimadas contra capacidad. TODO es estimación (la mayoría base de Claude, 24 definidas por la Gerente AyF)
hasta que los colaboradores registren horas reales.

- Horas de ejecución al mes = minutos por ejecución × ejecuciones al mes.
- Horas de revisión al mes = minutos de revisión de la tarea (o el valor general, hoy 0) × ejecuciones al mes, y se cargan a quien revisa.
- Capacidad = horas disponibles al mes por persona (160). Los cargos externos no tienen capacidad en la app.
"""
from dataclasses import dataclass, field

from nucleo.models import Cargo, Ocurrencia, Tarea
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


def horas_de_revision(t: Tarea, por_defecto_min: int | None = None) -> float:
    """Horas que tarda quien revisa UNA ejecución: las propias de la tarea o, si no tiene, el valor general (hoy 0: va dentro de las horas de quien ejecuta).
    Una tarea sin tiempo de ejecución estimado no carga revisión (no se sabe cuánto es)."""
    if not t.minutos_estimados:
        return 0.0
    minutos = t.minutos_revision if t.minutos_revision is not None else (por_defecto_min if por_defecto_min is not None else parametros.entero("minutos_revision"))
    return minutos / 60


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
    min_revision = parametros.entero("minutos_revision")
    filas = {c.pk: CargaCargo(c, capacidad) for c in Cargo.objects.filter(activo=True, es_externo=False)}
    for t in _tareas_activas():
        h = _h_al_mes(t)
        if t.cargo_ejecuta_id in filas:
            filas[t.cargo_ejecuta_id].tareas_ejecuta += 1
            filas[t.cargo_ejecuta_id].horas_ejecucion += h
        if t.cargo_revisa_id in filas:
            filas[t.cargo_revisa_id].tareas_revisa += 1
            filas[t.cargo_revisa_id].horas_revision += horas_de_revision(t, min_revision) * float(t.ejecuciones_mes or 0)  # también las de externos: el revisor las recibe y las revisa
    return list(filas.values())


def tareas_sin_horas() -> int:
    return _tareas_activas().filter(minutos_estimados__isnull=True).count()


@dataclass
class CargaDelCierre:
    cargo: Cargo
    horas: dict = field(default_factory=dict)
    disponible_por_dia: float = 0.0

    def sobrecargados(self) -> list[int]:
        return [d for d, h in self.horas.items() if h > self.disponible_por_dia + 1e-9]


def dias_del_cierre(anio: int | None = None, mes: int | None = None) -> range:
    """Cuántos días hábiles abarca el cierre del mes (del primero hasta la entrega al Directorio)."""
    from nucleo.servicios import kpi, reloj
    hoy = reloj.hoy()
    return range(1, len(kpi.hitos_del_mes(anio or hoy.year, mes or hoy.month)) + 1)


def por_dia_de_cierre(anio: int | None = None, mes: int | None = None) -> list[CargaDelCierre]:
    """Horas de las tareas del cierre que vencen cada día hábil (más la revisión del revisor), contra lo que deja libre la operación diaria.
    Se calcula con las fechas reales del mes: los días 8, 9 y 10 se corren al hábil siguiente si caen en día inhábil."""
    from nucleo.servicios import kpi, reloj
    from nucleo.servicios.feriados import calendario_confirmado
    from nucleo.servicios.recurrencia import fechas_limite
    hoy = reloj.hoy()
    anio, mes = anio or hoy.year, mes or hoy.month
    cal = calendario_confirmado()
    dia_de = {f: int(etiqueta.split()[1]) for etiqueta, f in kpi.hitos_del_mes(anio, mes)}
    dias = parametros.entero("dias_habiles_mes")
    capacidad_dia = parametros.entero("horas_disponibles_mes") / dias
    min_revision = parametros.entero("minutos_revision")
    filas = {c.pk: CargaDelCierre(c, horas={d: 0.0 for d in dia_de.values()}, disponible_por_dia=capacidad_dia) for c in Cargo.objects.filter(activo=True, es_externo=False)}
    for t in _tareas_activas():
        if t.regla_tipo in OPERACION and t.cargo_ejecuta_id in filas:
            filas[t.cargo_ejecuta_id].disponible_por_dia -= _h_al_mes(t) / dias
        if t.regla_tipo in kpi.TIPOS_DE_CIERRE:
            try:
                fechas = fechas_limite(t.regla(), anio, mes, cal)
            except ValueError:
                continue
            h = _h_por_ejecucion(t)
            for f in fechas:
                n = dia_de.get(f)
                if n is None:
                    continue
                if t.cargo_ejecuta_id in filas:
                    filas[t.cargo_ejecuta_id].horas[n] += h
                if t.cargo_revisa_id in filas:
                    filas[t.cargo_revisa_id].horas[n] += horas_de_revision(t, min_revision)
    return list(filas.values())


@dataclass
class RealVsEstimado:
    """Por persona y mes: lo que se estimó contra lo que anotó. Solo se comparan las tareas hechas que tienen horas reales."""
    colaborador: object
    hechas: int = 0
    con_horas: int = 0
    horas_estimadas: float = 0.0
    horas_reales: float = 0.0

    @property
    def sin_horas(self) -> int:
        return self.hechas - self.con_horas

    @property
    def diferencia_pct(self):
        if not self.con_horas or not self.horas_estimadas:
            return None
        return round((self.horas_reales - self.horas_estimadas) * 100 / self.horas_estimadas, 1)


def real_vs_estimado(periodo) -> list[RealVsEstimado]:
    filas: dict[int, RealVsEstimado] = {}
    qs = Ocurrencia.objects.filter(periodo=periodo, tipo_marca="HECHA", colaborador__isnull=False).exclude(estado=Ocurrencia.NO_APLICA).select_related("tarea", "colaborador")
    for o in qs:
        f = filas.setdefault(o.colaborador_id, RealVsEstimado(o.colaborador))
        if o.estado not in (Ocurrencia.HECHA, Ocurrencia.REVISADA):
            continue
        f.hechas += 1
        if o.minutos_reales is not None:
            f.con_horas += 1
            f.horas_reales += o.minutos_reales / 60
            estimado = o.minutos_estimados if o.minutos_estimados is not None else o.tarea.minutos_estimados
            f.horas_estimadas += (estimado or 0) / 60
    return list(filas.values())
