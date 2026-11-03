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
from nucleo.servicios.carga import horas_de_revision
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
    minutos: int | None = None  # horas propuestas por ejecución (vacío = las vigentes)


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
    cierre: bool = False  # tarea del cierre (días hábiles 1 a 7 o días 8, 9 y 10)


@dataclass
class Contexto:
    anio: int
    mes: int
    cal: object
    desde: date
    hasta: date  # día 8 (reportes listos)
    dias: list  # fechas de la matriz: del primer día hábil a la entrega al Directorio
    min_revision: int  # minutos que tarda quien revisa, cuando la tarea no tiene su propio tiempo
    internos: dict  # cargo_id → Cargo (los que tienen capacidad)
    tareas: dict  # id → Tarea
    sin_horas: set = field(default_factory=set)
    hasta_pausa: date | None = None  # DH10: hasta aquí rige lo que se pausa o reasigna en las semanas de cierre

    def capacidad(self, cargo_id: int, fecha: date) -> float:
        return float(JORNADA_HORAS[fecha.weekday()]) if self.cal.es_habil(fecha) else 0.0


def contexto(anio: int, mes: int) -> Contexto:
    cal = calendario_confirmado()
    desde, hasta_pausa = ventana_del_cierre(cal, anio, mes)
    hasta = cal.dia_habil_n(anio, mes, 8)  # DH08: reportes listos
    internos = {c.pk: c for c in Cargo.objects.filter(activo=True, es_externo=False)}
    tareas = {t.pk: t for t in Tarea.objects.filter(activa=True, requiere_revision=False).select_related("cargo_ejecuta", "cargo_revisa", "proceso", "padre")}
    return Contexto(anio, mes, cal, desde, hasta, [cal.dia_habil_n(anio, mes, 0)] + [f for _, f in kpi.hitos_del_mes(anio, mes)], parametros.entero("minutos_revision"), internos, tareas, hasta_pausa=hasta_pausa)


def items_de(t: Tarea, plan: Plan, ctx: Contexto) -> list[Item]:
    """Lo que esa tarea carga cada día del mes según el plan: la ejecución (a quien la hace) y la revisión (a quien revisa)."""
    if not plan.regla_tipo:
        return []
    from nucleo.servicios.recurrencia import Regla
    regla = Regla(plan.regla_tipo, dia_semana=t.regla_dia_semana, n=plan.regla_n, dia=t.regla_dia, meses=tuple(int(m) for m in t.regla_meses.split(",") if m.strip()), ajuste=t.regla_ajuste)
    try:
        fechas = fechas_limite(regla, ctx.anio, ctx.mes, ctx.cal)
    except (ReglaIncompleta, ReglaInvalida, ValueError):
        return []
    minutos = plan.minutos if plan.minutos is not None else t.minutos_estimados
    horas = (minutos or 0) / 60
    if minutos is None:
        ctx.sin_horas.add(t.pk)
    es_cierre = plan.regla_tipo in CIERRE
    items = []
    for f in fechas:
        ejecuta, revisa = plan.ejecuta_id, plan.revisa_id
        if plan.modo_cierre != "igual" and ctx.desde <= f <= ctx.hasta_pausa:
            if plan.modo_cierre == "pausar":
                continue
            if plan.cargo_cierre_id:
                ejecuta, revisa = plan.cargo_cierre_id, plan.revisa_cierre_id or plan.revisa_id
        if ejecuta in ctx.internos:
            items.append(Item(f, ejecuta, t.pk, t.codigo, t.subtarea, t.proceso.nombre, horas, "ejecución", es_cierre))
        if revisa in ctx.internos and horas:
            items.append(Item(f, revisa, t.pk, t.codigo, t.subtarea, t.proceso.nombre, horas_de_revision(t, ctx.min_revision), "revisión", es_cierre))
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
    hasta: date | None = None  # DH08: reportes listos
    desde: date | None = None  # DH01: el DH00 (último hábil del mes anterior) se ve en la matriz pero no cuenta en la semana del cierre

    def exceso(self, fecha: date) -> float:
        return max(0.0, self.horas.get(fecha, 0.0) - self.capacidad.get(fecha, 0.0))

    def sobrecargados(self) -> list[date]:
        return [f for f in self.horas if self.exceso(f) > TOLERANCIA]

    @property
    def horas_semana_cierre(self) -> float:
        """Horas desde el primer día hábil (DH01) hasta DH08 (los reportes listos)."""
        return sum(h for f, h in self.horas.items() if self._en_la_semana(f))

    @property
    def capacidad_semana_cierre(self) -> float:
        return sum(c for f, c in self.capacidad.items() if self._en_la_semana(f))

    def _en_la_semana(self, f: date) -> bool:
        return (self.desde is None or f >= self.desde) and (self.hasta is None or f <= self.hasta)

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
        """«DH03», y a continuación qué pasa ese día si es una de las entregas (reportes listos, Gerente General, Directorio)."""
        dh = f"DH{self.ctx.dias.index(fecha):02d}" if fecha in self.ctx.dias else ""  # ctx.dias[0] es el DH00
        entrega = kpi.descripciones_del_mes(self.anio, self.mes).get(fecha, "")
        return f"{dh} · {entrega}" if entrega else dh

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

    def riesgo_de_cumplimiento(self) -> tuple[int, int]:
        """(tareas del cierre que caen en un día en que su responsable ya pasó de la jornada, tareas del cierre en la semana del cierre).
        Una tarea en un día que no cabe es una tarea que probablemente se entregue tarde."""
        en_riesgo = total = 0
        for fila in self.filas:
            for f, items in fila.items.items():
                if f > self.ctx.hasta:
                    continue
                n = sum(1 for it in items if it.tipo == "ejecución" and it.cierre)
                total += n
                if fila.exceso(f) > TOLERANCIA:
                    en_riesgo += n
        return en_riesgo, total

    @property
    def cumplimiento_esperado_pct(self) -> float:
        """Estimación gruesa del % de tareas del cierre que se entregan a tiempo: las que caen en días que caben en la jornada."""
        en_riesgo, total = self.riesgo_de_cumplimiento()
        return round((total - en_riesgo) * 100 / total, 1) if total else 100.0

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
    filas = [FilaDeCargo(c, horas[pk], {f: ctx.capacidad(pk, f) for f in ctx.dias}, detalle[pk], total_mes[pk], c.horas_mes_max, ctx.hasta, ctx.desde) for pk, c in sorted(ctx.internos.items(), key=lambda kv: (kv[1].orden, kv[1].nombre))]
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


HORAS_PAQUETE = 3.0  # con la skill, el paquete de reportes toma como máximo 3 h (Karla, 01-11-2026)
PROCESOS_DE_ENTREGA = ("Reportería día 7", "Revisión día 9", "Cierre día 10")  # el paquete del día 8, la revisión del 9 y el cierre del 10: fechas fijas
PROCESO_PAQUETE = "Reportería día 7"
PROCESO_ANALISIS = "Análisis de cuentas"
PROCESO_COSTEO = "Costeo y producción"
PREFIJOS_COSTO_EN_DESTINO = ("Costo en destino", "Informe de costos")  # lo último que se procesa antes del paquete
CARGOS_DE_ANALISIS = ("Contador Senior", "Jefa de Control", "Asistente Contable")  # pueden repartirse el análisis de cuentas en paralelo
GERENTE = "Gerente AyF"


def _clasificar(t: Tarea, plan: Plan) -> str:
    """paquete · fija · costo_en_destino · analisis · normal."""
    if t.proceso.nombre == PROCESO_PAQUETE and plan.ejecuta_id and t.cargo_ejecuta.nombre == GERENTE:
        return "paquete"
    if t.proceso.nombre in PROCESOS_DE_ENTREGA or (plan.regla_tipo == "CIERRE_HITO" and plan.regla_n in (9, 10)):
        return "fija"  # lo que va el día 9 (Gerente General) o el 10 (Directorio) no se mueve
    if t.proceso.nombre == PROCESO_COSTEO and t.tarea_principal.startswith(PREFIJOS_COSTO_EN_DESTINO):
        return "costo_en_destino"
    if t.proceso.nombre == PROCESO_ANALISIS:
        return "analisis"
    return "normal"


def _texto_dia(plan: Plan) -> str:
    if plan.regla_tipo == "CIERRE_HITO":
        return f"Día {plan.regla_n} del mes"
    return f"Día hábil {plan.regla_n}"


def proponer(anio: int, mes: int, ctx: Contexto | None = None, max_pasos: int = 300) -> Propuesta:
    """Propuesta «en cascada» para el cierre de un mes (control de gestión con foco en el cumplimiento), siguiendo la lógica de Karla:

    1. Las tareas del cierre se hacen **de menor a mayor**, en el orden de los procesos, **ocupando los días desde el 1 en adelante**.
    2. **Lo último que se procesa es el costo en destino** (el último día de proceso, el «día 7») y **en paralelo** se hace el **análisis de cuentas**, que se reparte
       entre el Contador Senior, la Jefa de Control y la Asistente Contable.
    3. El **día 8** solo se procesa: el Gerente AyF prepara el **paquete de reportes** (con la skill, **máximo 3 horas**).
    4. La Asistente cubre compras y pagos y los otros tres se enfocan en el cierre (reglas de operación).
    «Día 7» es el último día hábil de proceso antes de la entrega del día 8; si el día 7 cae en inhábil pasa al hábil siguiente.
    Nada se ejecuta: es una propuesta calculada con horas estimadas."""
    ctx = ctx or contexto(anio, mes)
    planes = {t.pk: plan_actual(t) for t in ctx.tareas.values()}
    cambios: list[Cambio] = []
    antes = construir(anio, mes, ctx=ctx)
    _aplicar_reglas_de_operacion(ctx, planes, cambios)

    habiles = ctx.cal.dias_habiles_del_mes(anio, mes)
    indice = {f: n for n, f in enumerate(habiles, start=1)}
    ultimo = min(ctx.cal.dia_habil_n(anio, mes, 7), ctx.hasta)  # DH07: el último día de proceso
    L = max(1, min(indice[ultimo], 7))
    dias = habiles[:L]
    gerente = _cargo_por_nombre(ctx, GERENTE)
    tope = {pk: c.horas_mes_max for pk, c in ctx.internos.items() if c.horas_mes_max}

    grupo = {t.pk: _clasificar(t, planes[t.pk]) for t in ctx.tareas.values() if planes[t.pk].regla_tipo in CIERRE and planes[t.pk].ejecuta_id in ctx.internos}
    movibles = {pk for pk, g in grupo.items() if g != "fija"}
    motivos: dict[int, str] = {}

    # El paquete de reportes: lo prepara el Gerente AyF el día 8 en un máximo de 3 horas (con la skill).
    paquete = [t for t in ctx.tareas.values() if grupo.get(t.pk) == "paquete"]
    total_min = sum(t.minutos_estimados or 0 for t in paquete)
    if paquete and total_min > HORAS_PAQUETE * 60:
        escala = HORAS_PAQUETE * 60 / total_min
        nuevos = [int(round((t.minutos_estimados or 0) * escala)) for t in paquete]
        nuevos[nuevos.index(max(nuevos))] += int(round(HORAS_PAQUETE * 60)) - sum(nuevos)
        for t, m in zip(paquete, nuevos):
            planes[t.pk] = replace(planes[t.pk], minutos=m)
            motivos[t.pk] = f"Con la skill, el paquete de reportes lo prepara el {GERENTE} el día 8 en un máximo de {HORAS_PAQUETE:g} h en total."
    movibles -= {t.pk for t in paquete}

    items = {t.pk: items_de(t, planes[t.pk], ctx) for t in ctx.tareas.values()}
    carga = {pk: {f: 0.0 for f in ctx.dias} for pk in ctx.internos}
    mes_total = {pk: 0.0 for pk in ctx.internos}
    for pk, lista in items.items():
        for it in lista:
            mes_total[it.cargo_id] += it.horas
            if pk not in movibles and it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] += it.horas  # lo que no se mueve ya ocupa su día; lo movible se coloca a continuación

    def libre(c, f):
        return ctx.capacidad(c, f) - carga[c][f]

    def exceso(c, f):
        return max(0.0, carga[c][f] - ctx.capacidad(c, f))

    def poner(t, cargo_id, dia):
        antes_items = items[t.pk]
        nuevo = replace(planes[t.pk], ejecuta_id=cargo_id, regla_tipo="CIERRE_DIA_HABIL", regla_n=indice[dia])
        nuevos = items_de(t, nuevo, ctx)
        for it in antes_items:
            mes_total[it.cargo_id] -= it.horas
        for it in nuevos:
            mes_total[it.cargo_id] += it.horas
            if it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] += it.horas
        planes[t.pk], items[t.pk] = nuevo, nuevos

    def horas_de(t):
        m = planes[t.pk].minutos if planes[t.pk].minutos is not None else t.minutos_estimados
        return (m or 0) / 60

    def cabe(t, cargo_id, dia, h):
        revisa = planes[t.pk].revisa_id
        return libre(cargo_id, dia) >= h - TOLERANCIA and (revisa not in ctx.internos or not h or libre(revisa, dia) >= horas_de_revision(t, ctx.min_revision) - TOLERANCIA)

    def peor_dia(t, cargo_id, h, entre):
        """Si no cabe en ningún día, el día con más espacio (el menor exceso)."""
        return max(entre, key=lambda d: (libre(cargo_id, d), -indice[d]))

    ordenadas = sorted((t for t in ctx.tareas.values() if t.pk in movibles), key=lambda t: (t.proceso.orden, t.secuencia, t.codigo))
    # 1) Lo normal: en orden de proceso, cada tarea en el primer día (desde el 1) en que su responsable tiene espacio.
    for t in (t for t in ordenadas if grupo[t.pk] == "normal"):
        c, h = planes[t.pk].ejecuta_id, horas_de(t)
        dia = next((d for d in dias if cabe(t, c, d, h)), None) or peor_dia(t, c, h, dias)
        poner(t, c, dia)
        motivos[t.pk] = "Se ocupan los días desde el 1 en adelante, en el orden de los procesos (de menor a mayor): primer día con espacio para su responsable."
    # 2) El análisis de cuentas: el último día de proceso, en paralelo entre el Contador Senior, la Jefa de Control y la Asistente Contable.
    analistas = [pk for nombre in CARGOS_DE_ANALISIS if (pk := _cargo_por_nombre(ctx, nombre))]
    for t in sorted((t for t in ordenadas if grupo[t.pk] == "analisis"), key=lambda t: -horas_de(t)):
        h = horas_de(t)
        elegible = [c for c in analistas if c != planes[t.pk].revisa_id]
        elegido = None
        for d in reversed(dias):  # del último día hacia atrás
            candidatos = [c for c in elegible if cabe(t, c, d, h)]
            if candidatos:
                elegido = (max(candidatos, key=lambda c: libre(c, d)), d)
                break
        if elegido is None:  # no cabe en ningún día: se reparte entre los últimos días de proceso, donde haya más espacio
            elegido = max(((c, d) for d in dias[-3:] for c in elegible), key=lambda cd: (libre(*cd), indice[cd[1]]))
        poner(t, *elegido)
        motivos[t.pk] = "El análisis de cuentas se hace el último día de proceso y en paralelo entre el Contador Senior, la Jefa de Control y la Asistente Contable."
    # 3) El costo en destino: lo último que se procesa; se llena hacia atrás desde el último día (el primero de la lista queda más temprano).
    for t in reversed([t for t in ordenadas if grupo[t.pk] == "costo_en_destino"]):
        c, h = planes[t.pk].ejecuta_id, horas_de(t)
        dia = next((d for d in reversed(dias) if cabe(t, c, d, h)), None) or peor_dia(t, c, h, dias[-3:])
        poner(t, c, dia)
        motivos[t.pk] = "El costo en destino es lo último que se procesa: termina el último día de proceso, antes del paquete del día 8."

    # 4) Equilibrio entre cargos: el más ocupado le pasa trabajo normal a otro que ya trabaja en ese proceso, sin cambiar el día y sin sobrecargar a nadie.
    conocen = {}
    for t in ctx.tareas.values():
        if t.cargo_ejecuta_id in ctx.internos:
            conocen.setdefault(t.proceso_id, set()).add(t.cargo_ejecuta_id)
    capacidad_ventana = {c: sum(ctx.capacidad(c, f) for f in dias) for c in ctx.internos}

    def ocupacion(c):
        return sum(carga[c][f] for f in dias) / capacidad_ventana[c] if capacidad_ventana[c] else 0.0

    for _ in range(max_pasos):
        ocupaciones = {c: ocupacion(c) for c in ctx.internos}
        c_alto = max(ocupaciones, key=ocupaciones.get)
        valor_actual = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
        mejor = None
        for t in ordenadas:
            p = planes[t.pk]
            if grupo[t.pk] != "normal" or p.ejecuta_id != c_alto:
                continue
            h = horas_de(t)
            for c_bajo in conocen.get(t.proceso_id, set()):
                if c_bajo == c_alto or c_bajo == p.revisa_id or c_bajo not in ctx.internos or ocupaciones[c_alto] - ocupaciones[c_bajo] < 0.05:
                    continue
                if c_bajo in tope and mes_total[c_bajo] + h > tope[c_bajo]:
                    continue
                dia = next(f for f in dias if indice[f] == p.regla_n) if p.regla_n in indice.values() and any(indice[f] == p.regla_n for f in dias) else dias[-1]
                nuevo = replace(p, ejecuta_id=c_bajo)
                actuales, nuevos = items[t.pk], items_de(t, nuevo, ctx)
                for it in actuales:
                    if it.fecha in carga[it.cargo_id]:
                        carga[it.cargo_id][it.fecha] -= it.horas
                for it in nuevos:
                    if it.fecha in carga[it.cargo_id]:
                        carga[it.cargo_id][it.fecha] += it.horas
                valor = sum(exceso(c, f) for c in ctx.internos for f in ctx.dias)
                nuevo_max = max(ocupacion(c_alto), ocupacion(c_bajo))
                for it in nuevos:
                    if it.fecha in carga[it.cargo_id]:
                        carga[it.cargo_id][it.fecha] -= it.horas
                for it in actuales:
                    if it.fecha in carga[it.cargo_id]:
                        carga[it.cargo_id][it.fecha] += it.horas
                if valor <= valor_actual + TOLERANCIA and nuevo_max < ocupaciones[c_alto] - 1e-6 and (mejor is None or (nuevo_max, valor) < mejor[0]):
                    mejor = ((nuevo_max, valor), t, nuevo, nuevos, actuales)
        if mejor is None:
            break
        _, t, nuevo, nuevos, actuales = mejor
        for it in actuales:
            mes_total[it.cargo_id] -= it.horas
            if it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] -= it.horas
        for it in nuevos:
            mes_total[it.cargo_id] += it.horas
            if it.fecha in carga[it.cargo_id]:
                carga[it.cargo_id][it.fecha] += it.horas
        planes[t.pk], items[t.pk] = nuevo, nuevos
        motivos[t.pk] = motivos.get(t.pk, "") + " Cambia de responsable para repartir el cierre: el nuevo ya trabaja en este proceso y no es quien la revisa."

    # Los cambios, una vez por tarea, comparando con lo vigente.
    for t in ctx.tareas.values():
        p0, p1 = plan_actual(t), planes[t.pk]
        if (p0.regla_tipo, p0.regla_n) != (p1.regla_tipo, p1.regla_n):
            cambios.append(Cambio(t, "Día del cierre", _texto_dia(p0), _texto_dia(p1), motivos.get(t.pk, "")))
        if p1.ejecuta_id != p0.ejecuta_id:
            cambios.append(Cambio(t, "Responsable", _nombre(ctx, p0.ejecuta_id), _nombre(ctx, p1.ejecuta_id), motivos.get(t.pk, "")))
        if p1.minutos is not None and p1.minutos != (t.minutos_estimados or 0):
            cambios.append(Cambio(t, "Horas por ejecución", f"{(t.minutos_estimados or 0) / 60:.2f} h", f"{p1.minutos / 60:.2f} h", motivos.get(t.pk, "")))
    despues = construir(anio, mes, planes, ctx)
    sin_solucion = [(ctx.internos[c], f, exceso(c, f)) for c in ctx.internos for f in ctx.dias if exceso(c, f) > TOLERANCIA and f <= ctx.hasta]
    return Propuesta(planes, cambios, sorted(sin_solucion, key=lambda x: (x[1], x[0].orden)), antes, despues)


def horas_por_proceso(m: Matriz, solo_cierre: bool = True) -> list[tuple[str, float]]:
    """Dónde se van las horas hasta el día 8: (proceso, horas de ejecución), de mayor a menor."""
    total: dict[str, float] = {}
    for fila in m.filas:
        for f, items in fila.items.items():
            if f <= m.ctx.hasta:
                for it in items:
                    if it.tipo == "ejecución" and (it.cierre or not solo_cierre):
                        total[it.proceso] = total.get(it.proceso, 0.0) + it.horas
    return sorted(total.items(), key=lambda kv: -kv[1])


def diagnostico(prop: Propuesta) -> list[str]:
    """Lectura de control de gestión, con foco en el cumplimiento: qué dice la matriz y qué hay que decidir. Solo cifras de la propia matriz."""
    antes, d = prop.antes, prop.despues
    demanda, capacidad = d.horas_semana_cierre, d.capacidad_semana_cierre
    lineas = [f"Hasta el día 8 hay {demanda:.0f} h de trabajo (cierre, operación que continúa y revisiones) y el equipo tiene {capacidad:.0f} h de jornada: ocupación de {demanda * 100 / capacidad:.0f} %." if capacidad else "No hay capacidad en esas fechas."]
    brecha = demanda - capacidad
    if brecha > 0:
        lineas.append(f"Faltan {brecha:.0f} h. Aunque el reparto fuera perfecto el trabajo no cabe: hay que bajar horas estimadas, mover trabajo más allá del día 8 o sumar apoyo.")
    else:
        lineas.append("En total el trabajo cabe en la jornada del equipo.")
    lineas.append(f"Tareas del cierre que caen en un día que cabe en la jornada de su responsable (indicador de cumplimiento a tiempo): {antes.cumplimiento_esperado_pct:.0f} % hoy → {d.cumplimiento_esperado_pct:.0f} % con la propuesta. La meta es 95 %.")
    mas = max(d.filas, key=lambda f: f.ocupacion_pct)
    menos = min(d.filas, key=lambda f: f.ocupacion_pct)
    lineas.append(f"El cargo más exigido es {mas.cargo.nombre} ({mas.ocupacion_pct:.0f} %) y el menos exigido {menos.cargo.nombre} ({menos.ocupacion_pct:.0f} %).")
    analista = next((f for f in d.filas if f.cargo.nombre == CARGO_ANALISTA), None)
    if analista is not None and analista.capacidad_semana_cierre:
        operacion = sum(it.horas for items in analista.items.values() for it in items if it.tipo == "ejecución" and not it.cierre and it.fecha <= d.ctx.hasta)
        dias = len([f for f in analista.capacidad if f <= d.ctx.hasta])
        lineas.append(f"La Asistente Contable, al cubrir compras y pagos, tiene {operacion / dias:.1f} h al día solo de operación (caben 9 h de lunes a jueves y 5 h el viernes): "
                      + ("no le queda tiempo para tareas del cierre." if operacion >= analista.capacidad_semana_cierre else "le queda poco para tareas del cierre."))
    procesos = horas_por_proceso(d)[:4]
    if procesos:
        lineas.append("Los procesos del cierre que más horas consumen: " + "; ".join(f"{nombre} ({h:.0f} h)" for nombre, h in procesos) + ".")
    return lineas
