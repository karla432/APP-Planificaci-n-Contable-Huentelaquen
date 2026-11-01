"""Matriz del cierre: quién hace qué cada día del cierre, con sus horas contra la jornada, y una propuesta para equilibrar al equipo (Karla, 01-11-2026).

Reglas que pidió Karla:
- Jornada: lunes a jueves 9 h y viernes 5 h. El Gerente AyF dedica como máximo 80 h al mes a Huentelauquén.
- Los 4 cargos del equipo deben quedar equilibrados en la semana del cierre (del primer día hábil al día 8).
- La Asistente Contable cubre en esa semana el ingreso de compras y los pagos (el Contador Senior solo revisa); la Jefa de Control, el Contador Senior y el
  Gerente AyF se enfocan al 100 % en el cierre, así que sus otras tareas semanales se pausan.

Todo es una PROPUESTA calculada con horas estimadas: no cambia nada hasta que Karla la revise y la cargue.
Lógica pura sobre la planificación; no escribe en la base de datos.
"""
from dataclasses import dataclass, field, replace
from datetime import date

from nucleo.models import Cargo, Tarea
from nucleo.servicios import kpi, parametros
from nucleo.servicios.calendario import JORNADA_HORAS, ventana_del_cierre
from nucleo.servicios.feriados import calendario_confirmado
from nucleo.servicios.recurrencia import ReglaIncompleta, ReglaInvalida, fechas_limite

CARGO_ANALISTA = "Asistente Contable"
CARGO_REVISOR_DE_OPERACION = "Contador Senior"
CARGOS_ENFOCADOS_AL_CIERRE = ("Gerente AyF", "Jefa de Control", "Contador Senior")
PROCESOS_QUE_CUBRE_LA_ANALISTA = ("Compras", "Pagos Banco Estado", "Pagos Banco de Chile")  # «ingresar las compras y sacar pagos»
OPERACION = ("DIARIA_HABIL", "SEMANAL")
CIERRE = ("CIERRE_DIA_HABIL", "CIERRE_HITO")
TOLERANCIA = 1e-9


@dataclass(frozen=True)
class Plan:
    """Cómo queda una tarea en un escenario: quién la hace, quién la revisa, cuándo vence y qué pasa en la semana del cierre."""

    ejecuta_id: int
    revisa_id: int | None
    regla_tipo: str
    regla_n: int | None
    modo_cierre: str = "igual"
    cargo_cierre_id: int | None = None
    revisa_cierre_id: int | None = None


def plan_actual(t: Tarea) -> Plan:
    return Plan(t.cargo_ejecuta_id, t.cargo_revisa_id, t.regla_tipo, t.regla_n, t.modo_cierre, t.cargo_cierre_id, t.cargo_revisa_cierre_id)


@dataclass
class Item:
    fecha: date
    cargo_id: int
    tarea_id: int
    codigo: str
    texto: str
    proceso: str
    horas: float
    tipo: str  # ejecución / revisión


@dataclass
class Contexto:
    anio: int
    mes: int
    cal: object
    min_dias: int
    desde: date
    hasta: date  # día 8 (reportes listos)
    dias: list  # fechas de la matriz: del primer día hábil a la entrega al Directorio
    pct_revision: float
    internos: dict  # cargo_id → Cargo (los que tienen capacidad)
    tareas: dict  # id → Tarea
    sin_horas: set = field(default_factory=set)

    def capacidad(self, cargo_id: int, fecha: date) -> float:
        return float(JORNADA_HORAS[fecha.weekday()]) if self.cal.es_habil(fecha) else 0.0


def contexto(anio: int, mes: int) -> Contexto:
    cal = calendario_confirmado()
    min_dias = parametros.entero("min_dias_habiles_d7_d10")
    desde, hasta = ventana_del_cierre(cal, anio, mes, min_dias)
    internos = {c.pk: c for c in Cargo.objects.filter(activo=True, es_externo=False)}
    tareas = {t.pk: t for t in Tarea.objects.filter(activa=True, requiere_revision=False).select_related("cargo_ejecuta", "cargo_revisa", "proceso", "padre")}
    return Contexto(anio, mes, cal, min_dias, desde, hasta, [f for _, f in kpi.hitos_del_mes(anio, mes)], parametros.entero("pct_horas_revision") / 100, internos, tareas)


def items_de(t: Tarea, plan: Plan, ctx: Contexto) -> list[Item]:
    """Lo que esa tarea carga cada día del mes según el plan: la ejecución (a quien la hace) y la revisión (a quien revisa)."""
    if not plan.regla_tipo:
        return []
    from nucleo.servicios.recurrencia import Regla
    regla = Regla(plan.regla_tipo, dia_semana=t.regla_dia_semana, n=plan.regla_n, dia=t.regla_dia, meses=tuple(int(m) for m in t.regla_meses.split(",") if m.strip()), ajuste=t.regla_ajuste)
    try:
        fechas = fechas_limite(regla, ctx.anio, ctx.mes, ctx.cal, min_dias_habiles_d7_d10=ctx.min_dias)
    except (ReglaIncompleta, ReglaInvalida, ValueError):
        return []
    horas = (t.minutos_estimados or 0) / 60
    if t.minutos_estimados is None:
        ctx.sin_horas.add(t.pk)
    items = []
    for f in fechas:
        ejecuta, revisa = plan.ejecuta_id, plan.revisa_id
        if plan.modo_cierre != "igual" and ctx.desde <= f <= ctx.hasta:
            if plan.modo_cierre == "pausar":
                continue
            if plan.cargo_cierre_id:
                ejecuta, revisa = plan.cargo_cierre_id, plan.revisa_cierre_id or plan.revisa_id
        if ejecuta in ctx.internos:
            items.append(Item(f, ejecuta, t.pk, t.codigo, t.subtarea, t.proceso.nombre, horas, "ejecución"))
        if revisa in ctx.internos and horas:
            items.append(Item(f, revisa, t.pk, t.codigo, t.subtarea, t.proceso.nombre, horas * ctx.pct_revision, "revisión"))
    return items


# ---- La matriz ---------------------------------------------------------------------------------------------------------------


@dataclass
class FilaDeCargo:
    cargo: Cargo
    horas: dict  # fecha → horas
    capacidad: dict  # fecha → horas disponibles
    items: dict  # fecha → [Item]
    total_mes: float = 0.0
    tope_mes: int | None = None
    hasta: date | None = None  # día 8: fin de la semana del cierre

    def exceso(self, fecha: date) -> float:
        return max(0.0, self.horas.get(fecha, 0.0) - self.capacidad.get(fecha, 0.0))

    def sobrecargados(self) -> list[date]:
        return [f for f in self.horas if self.exceso(f) > TOLERANCIA]

    @property
    def horas_semana_cierre(self) -> float:
        """Horas desde el primer día hábil hasta el día 8 (los reportes listos)."""
        return sum(h for f, h in self.horas.items() if self.hasta is None or f <= self.hasta)

    @property
    def capacidad_semana_cierre(self) -> float:
        return sum(c for f, c in self.capacidad.items() if self.hasta is None or f <= self.hasta)

    @property
    def ocupacion_pct(self) -> float:
        return round(self.horas_semana_cierre * 100 / self.capacidad_semana_cierre, 1) if self.capacidad_semana_cierre else 0.0

    @property
    def pasa_el_tope(self) -> bool:
        return self.tope_mes is not None and self.total_mes > self.tope_mes + TOLERANCIA


@dataclass
class Matriz:
    anio: int
    mes: int
    ctx: Contexto
    filas: list
    sin_horas: list

    @property
    def dias(self) -> list[date]:
        return self.ctx.dias

    def etiqueta(self, fecha: date) -> str:
        return kpi.descripciones_del_mes(self.anio, self.mes).get(fecha, "")

    def alertas(self) -> list[str]:
        textos = []
        for fila in self.filas:
            for f in fila.sobrecargados():
                textos.append(f"{fila.cargo.nombre}: {f:%a %d-%m} tiene {fila.horas[f]:.1f} h y caben {fila.capacidad[f]:.0f} h (+{fila.exceso(f):.1f} h).")
            if fila.pasa_el_tope:
                textos.append(f"{fila.cargo.nombre}: {fila.total_mes:.1f} h en el mes, sobre su tope de {fila.tope_mes} h.")
        if self.sin_horas:
            textos.append(f"{len(self.sin_horas)} tareas no tienen horas estimadas y no suman a la matriz.")
        return textos

    @property
    def exceso_total(self) -> float:
        return sum(fila.exceso(f) for fila in self.filas for f in fila.horas)

    @property
    def horas_semana_cierre(self) -> float:
        return sum(f.horas_semana_cierre for f in self.filas)

    @property
    def capacidad_semana_cierre(self) -> float:
        return sum(f.capacidad_semana_cierre for f in self.filas)

    @property
    def desequilibrio_pct(self) -> float:
        """Distancia entre el cargo más cargado y el menos cargado en la semana del cierre (en puntos de ocupación)."""
        ocupaciones = [f.ocupacion_pct for f in self.filas]
        return round(max(ocupaciones) - min(ocupaciones), 1) if ocupaciones else 0.0


def construir(anio: int, mes: int, planes: dict[int, Plan] | None = None, ctx: Contexto | None = None) -> Matriz:
    ctx = ctx or contexto(anio, mes)
    planes = planes or {}
    dias = set(ctx.dias)
    horas = {c: {f: 0.0 for f in ctx.dias} for c in ctx.internos}
    detalle = {c: {f: [] for f in ctx.dias} for c in ctx.internos}
    total_mes = {c: 0.0 for c in ctx.internos}
    for t in ctx.tareas.values():
        for it in items_de(t, planes.get(t.pk) or plan_actual(t), ctx):
            total_mes[it.cargo_id] += it.horas
            if it.fecha in dias:
                horas[it.cargo_id][it.fecha] += it.horas
                detalle[it.cargo_id][it.fecha].append(it)
    filas = [FilaDeCargo(c, horas[pk], {f: ctx.capacidad(pk, f) for f in ctx.dias}, detalle[pk], total_mes[pk], c.horas_mes_max, ctx.hasta) for pk, c in sorted(ctx.internos.items(), key=lambda kv: (kv[1].orden, kv[1].nombre))]
    return Matriz(anio, mes, ctx, filas, sorted(ctx.sin_horas))


# ---- La propuesta ------------------------------------------------------------------------------------------------------------


@dataclass
class Cambio:
    tarea: Tarea
    campo: str
    antes: str
    despues: str
    motivo: str


@dataclass
class Propuesta:
    planes: dict
    cambios: list
    sin_solucion: list  # (cargo, fecha, exceso) que no se pudo resolver con estas reglas
    antes: Matriz = None
    despues: Matriz = None


def _nombre(ctx: Contexto, cargo_id) -> str:
    return ctx.internos[cargo_id].nombre if cargo_id in ctx.internos else "—"


def _cargo_por_nombre(ctx: Contexto, nombre: str):
    return next((pk for pk, c in ctx.internos.items() if c.nombre == nombre), None)


def _aplicar_reglas_de_operacion(ctx: Contexto, planes: dict, cambios: list):
    """La Asistente cubre compras y pagos en la semana del cierre (el Contador solo revisa); lo demás de operación de los tres cargos enfocados se pausa."""
    analista, revisor = _cargo_por_nombre(ctx, CARGO_ANALISTA), _cargo_por_nombre(ctx, CARGO_REVISOR_DE_OPERACION)
    enfocados = {pk for nombre in CARGOS_ENFOCADOS_AL_CIERRE if (pk := _cargo_por_nombre(ctx, nombre))}
    for t in ctx.tareas.values():
        p = planes[t.pk]
        if p.regla_tipo not in OPERACION or p.ejecuta_id not in enfocados or p.modo_cierre != "igual":  # lo que Karla ya definió a mano no se toca
            continue
        if t.proceso.nombre in PROCESOS_QUE_CUBRE_LA_ANALISTA and analista:
            planes[t.pk] = replace(p, modo_cierre="reasignar", cargo_cierre_id=analista, revisa_cierre_id=revisor if revisor != analista else p.revisa_id)
            cambios.append(Cambio(t, "Semana del cierre", "Igual", f"Reasignar a {CARGO_ANALISTA} (revisa {CARGO_REVISOR_DE_OPERACION})", "La Asistente Contable cubre compras y pagos esa semana; los otros tres se enfocan en el cierre."))
        else:
            planes[t.pk] = replace(p, modo_cierre="pausar")
            cambios.append(Cambio(t, "Semana del cierre", "Igual", "Pausar", f"{_nombre(ctx, p.ejecuta_id)} se enfoca 100 % en el cierre: esta tarea se retoma después del día 8."))


def proponer(anio: int, mes: int, ctx: Contexto | None = None, max_pasos: int = 600) -> Propuesta:
    """Propuesta para el cierre de ese mes: primero las reglas de operación de Karla y luego se reparten las tareas del cierre para que nadie pase de su jornada.
    Una tarea del cierre solo se mueve a un día posterior (nunca antes: puede depender de información de su día) y como máximo hasta el día 8; solo se reasigna a un
    cargo que ya trabaja en ese mismo proceso, distinto de quien la revisa. Lo que no cabe se informa, no se esconde."""
    ctx = ctx or contexto(anio, mes)
    planes = {t.pk: plan_actual(t) for t in ctx.tareas.values()}
    cambios: list[Cambio] = []
    antes = construir(anio, mes, ctx=ctx)
    _aplicar_reglas_de_operacion(ctx, planes, cambios)

    habiles = ctx.cal.dias_habiles_del_mes(anio, mes)
    indice = {f: n for n, f in enumerate(habiles, start=1)}
    dias_del_cierre = [f for f in ctx.dias if f <= ctx.hasta]
    conocen = {}  # proceso → cargos que ya trabajan en él
    for t in ctx.tareas.values():
        if t.cargo_ejecuta_id in ctx.internos:
            conocen.setdefault(t.proceso_id, set()).add(t.cargo_ejecuta_id)
    tope = {pk: c.horas_mes_max for pk, c in ctx.internos.items() if c.horas_mes_max}

    items = {t.pk: items_de(t, planes[t.pk], ctx) for t in ctx.tareas.values()}
    carga = {pk: {f: 0.0 for f in ctx.dias} for pk in ctx.internos}
    mes_total = {pk: 0.0 for pk in ctx.internos}
    for lista in items.values():
        for it in lista:
            mes_total[it.cargo_id] += it.horas
            if it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] += it.horas

    def exceso(c, f):
        return max(0.0, carga[c][f] - ctx.capacidad(c, f))

    def aplicar(lista, signo):
        for it in lista:
            mes_total[it.cargo_id] += signo * it.horas
            if it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] += signo * it.horas

    movibles = [t for t in ctx.tareas.values() if planes[t.pk].regla_tipo == "CIERRE_DIA_HABIL" and planes[t.pk].ejecuta_id in ctx.internos]
    ya_movidas: dict[int, str] = {}
    sin_solucion = set()
    for _ in range(max_pasos):
        pendientes = [(exceso(c, f), c, f) for c in ctx.internos for f in dias_del_cierre if exceso(c, f) > TOLERANCIA and (c, f) not in sin_solucion]
        if not pendientes:
            break
        _, c0, f0 = max(pendientes)
        candidatas = [t for t in movibles if any(it.fecha == f0 and it.cargo_id == c0 and it.tipo == "ejecución" for it in items[t.pk])]
        mejor = None
        for t in sorted(candidatas, key=lambda t: -((t.minutos_estimados or 0))):
            p = planes[t.pk]
            actuales = items[t.pk]
            valor_actual = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
            for cargo in {p.ejecuta_id} | conocen.get(t.proceso_id, set()):
                if cargo == p.revisa_id or cargo not in ctx.internos or (cargo == _cargo_por_nombre(ctx, "Gerente AyF") and cargo != p.ejecuta_id and cargo in tope and mes_total[cargo] + (t.minutos_estimados or 0) / 60 > tope[cargo]):
                    continue
                for dia in dias_del_cierre:
                    n = indice.get(dia)
                    if n is None or n > 7 or (n < (p.regla_n or 1)) or (cargo == p.ejecuta_id and n == p.regla_n):
                        continue
                    nuevo = replace(p, ejecuta_id=cargo, regla_n=n)
                    nuevos = items_de(t, nuevo, ctx)
                    aplicar(actuales, -1)
                    aplicar(nuevos, +1)
                    valor = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
                    aplicar(nuevos, -1)
                    aplicar(actuales, +1)
                    clave = (round(valor, 6), cargo != p.ejecuta_id, abs(n - (p.regla_n or n)))  # menos exceso; mejor si no cambia de persona; mejor si se mueve poco
                    if valor < valor_actual - TOLERANCIA and (mejor is None or clave < mejor[0]):
                        mejor = (clave, t, nuevo, nuevos)
        if mejor is None:
            sin_solucion.add((c0, f0))
            continue
        _, t, nuevo, nuevos = mejor
        aplicar(items[t.pk], -1)
        aplicar(nuevos, +1)
        planes_antes = planes[t.pk]
        items[t.pk], planes[t.pk] = nuevos, nuevo
        ya_movidas[t.pk] = ya_movidas.get(t.pk, "") or f"{planes_antes.ejecuta_id}|{planes_antes.regla_n}"
    # Segunda pasada: aunque ya nadie pase de su jornada cada día, se acerca la ocupación de la semana del cierre entre los cargos (el más cargado le pasa trabajo al menos cargado)
    capacidad_ventana = {c: sum(ctx.capacidad(c, f) for f in dias_del_cierre) for c in ctx.internos}

    def ocupacion(c):
        return sum(carga[c][f] for f in dias_del_cierre) / capacidad_ventana[c] if capacidad_ventana[c] else 0.0

    for _ in range(max_pasos):
        ocupaciones = {c: ocupacion(c) for c in ctx.internos}
        c_alto = max(ocupaciones, key=ocupaciones.get)
        valor_actual = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
        mejor = None
        for t in movibles:
            p = planes[t.pk]
            if p.ejecuta_id != c_alto:
                continue
            horas_t = (t.minutos_estimados or 0) / 60
            for c_bajo in conocen.get(t.proceso_id, set()):  # solo a quien ya trabaja en ese proceso
                if c_bajo == c_alto or c_bajo == p.revisa_id or c_bajo not in ctx.internos or ocupaciones[c_alto] - ocupaciones[c_bajo] < 0.05:
                    continue
                if c_bajo in tope and mes_total[c_bajo] + horas_t > tope[c_bajo]:
                    continue
                actuales, nuevos = items[t.pk], items_de(t, replace(p, ejecuta_id=c_bajo), ctx)
                aplicar(actuales, -1)
                aplicar(nuevos, +1)
                valor = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
                nuevo_max = max(ocupacion(c_alto), ocupacion(c_bajo))
                aplicar(nuevos, -1)
                aplicar(actuales, +1)
                if valor <= valor_actual + TOLERANCIA and nuevo_max < ocupaciones[c_alto] - 1e-6 and (mejor is None or (nuevo_max, valor) < mejor[0]):
                    mejor = ((nuevo_max, valor), t, replace(p, ejecuta_id=c_bajo), nuevos)
        if mejor is None:
            break
        _, t, nuevo, nuevos = mejor
        aplicar(items[t.pk], -1)
        aplicar(nuevos, +1)
        items[t.pk], planes[t.pk] = nuevos, nuevo
    # los cambios de las tareas del cierre, una vez por tarea, comparando con lo original
    for t in movibles:
        p0, p1 = plan_actual(t), planes[t.pk]
        if p1.regla_n != p0.regla_n:
            cambios.append(Cambio(t, "Día hábil del cierre", f"Día hábil {p0.regla_n}", f"Día hábil {p1.regla_n}", "Se mueve a un día con espacio para no pasar de la jornada (nunca antes, y como máximo hasta el día 8)."))
        if p1.ejecuta_id != p0.ejecuta_id:
            cambios.append(Cambio(t, "Responsable", _nombre(ctx, p0.ejecuta_id), _nombre(ctx, p1.ejecuta_id), "Para repartir el cierre: su carga superaba la jornada o la de otro cargo era menor; el nuevo responsable ya trabaja en este proceso y no es quien la revisa."))
    despues = construir(anio, mes, planes, ctx)
    return Propuesta(planes, cambios, [(ctx.internos[c], f, exceso(c, f)) for c, f in sorted(sin_solucion, key=lambda x: (x[1], x[0])) if exceso(c, f) > TOLERANCIA], antes, despues)
