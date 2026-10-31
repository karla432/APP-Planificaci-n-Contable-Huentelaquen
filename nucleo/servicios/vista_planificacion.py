"""La planificación como árbol (proceso → tarea → subtarea) y como tabla, con filtros. La usan la pantalla y la exportación a Excel."""
from dataclasses import dataclass, field
from datetime import date

from django.db.models import Q

from nucleo.models import ESTADOS_PLAN, CambioDeCodigo, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import estructura

ETIQUETA_ESTADO = dict(ESTADOS_PLAN)


@dataclass
class Filtros:
    proceso: int | None = None
    tarea: str = ""
    subtarea: str = ""
    orden_desde: int | None = None
    orden_hasta: int | None = None
    estado: str = ""
    activos: str = "1"  # «1» solo activos · «0» solo inactivos · «todos»
    q: str = ""  # un código (también uno anterior) o parte de un nombre

    @property
    def filtra_hojas(self) -> bool:
        return bool(self.tarea or self.subtarea or self.estado or self.q or self.activos == "0")  # con estos filtros solo se muestran las ramas que coinciden


def desde_get(get) -> Filtros:
    def entero(clave):
        try:
            return int(get.get(clave, ""))
        except ValueError:
            return None

    activos = get.get("activos", "1")
    return Filtros(proceso=entero("proceso"), tarea=get.get("tarea", "").strip(), subtarea=get.get("subtarea", "").strip(), orden_desde=entero("orden_desde"),
                   orden_hasta=entero("orden_hasta"), estado=get.get("estado", "") if get.get("estado", "") in ETIQUETA_ESTADO else "",
                   activos=activos if activos in ("1", "0", "todos") else "1", q=get.get("q", "").strip())


@dataclass
class NodoTarea:
    tarea: TareaPrincipal
    subtareas: list = field(default_factory=list)


@dataclass
class NodoProceso:
    proceso: Proceso
    depende_de: list = field(default_factory=list)
    tareas: list = field(default_factory=list)

    @property
    def n_subtareas(self) -> int:
        return sum(len(t.subtareas) for t in self.tareas)


@dataclass
class Fila:
    nivel: int
    codigo: str
    orden: int
    proceso: str
    tarea: str
    subtarea: str
    responsable: str
    estado: str
    fecha_inicio: date | None
    fecha_termino: date | None
    observaciones: str
    activo: bool
    depende_de: str = ""
    codigo_anterior: str = ""


def _ids_por_codigo_anterior(q: str) -> dict[int, set[int]]:
    ids: dict[int, set[int]] = {1: set(), 2: set(), 3: set()}
    for nivel, objeto_id in CambioDeCodigo.objects.filter(codigo_anterior__icontains=q).values_list("nivel", "objeto_id"):
        ids[nivel].add(objeto_id)
    return ids


def construir(f: Filtros) -> list[NodoProceso]:
    procesos = Proceso.objects.select_related("responsable").order_by("orden")
    if f.proceso:
        procesos = procesos.filter(pk=f.proceso)
    if f.orden_desde:
        procesos = procesos.filter(orden__gte=f.orden_desde)
    if f.orden_hasta:
        procesos = procesos.filter(orden__lte=f.orden_hasta)
    hojas = Tarea.objects.select_related("padre", "cargo_ejecuta").order_by("padre__numero", "numero")
    if f.activos == "1":
        hojas = hojas.filter(activa=True)
    elif f.activos == "0":
        hojas = hojas.filter(activa=False)
    if f.tarea:
        hojas = hojas.filter(Q(padre__nombre__icontains=f.tarea) | Q(padre__codigo__icontains=f.tarea))
    if f.subtarea:
        hojas = hojas.filter(Q(subtarea__icontains=f.subtarea) | Q(codigo__icontains=f.subtarea))
    if f.estado:
        hojas = hojas.filter(estado_plan=f.estado)
    if f.q:
        antes = _ids_por_codigo_anterior(f.q)
        hojas = hojas.filter(Q(codigo__icontains=f.q) | Q(subtarea__icontains=f.q) | Q(padre__nombre__icontains=f.q) | Q(proceso__codigo__icontains=f.q) | Q(proceso__nombre__icontains=f.q)
                             | Q(pk__in=antes[3]) | Q(padre_id__in=antes[2]) | Q(proceso_id__in=antes[1]))
    por_tarea: dict[int, list] = {}
    for t in hojas:
        por_tarea.setdefault(t.padre_id, []).append(t)
    tareas_por_proceso: dict[int, list] = {}
    for tp in TareaPrincipal.objects.select_related("responsable").order_by("numero"):
        tareas_por_proceso.setdefault(tp.proceso_id, []).append(tp)
    deps = estructura.dependencias_de()
    arbol = []
    for p in procesos:
        nodo = NodoProceso(p, deps.get(p.pk, []))
        for tp in tareas_por_proceso.get(p.pk, []):
            subs = por_tarea.get(tp.pk, [])
            if f.filtra_hojas and not subs:
                continue  # con filtros de tarea/subtarea solo se muestran las ramas que coinciden
            if f.activos == "1" and not tp.activa:
                continue
            nodo.tareas.append(NodoTarea(tp, subs))
        if f.filtra_hojas and not nodo.tareas:
            continue
        if f.activos == "1" and not p.activo:
            continue
        arbol.append(nodo)
    return arbol


def aplanar(arbol: list[NodoProceso]) -> list[Fila]:
    filas = []
    for n in arbol:
        p = n.proceso
        filas.append(Fila(1, p.codigo, p.orden, p.nombre, "", "", p.responsable.nombre if p.responsable else "", ETIQUETA_ESTADO[p.estado_plan], p.fecha_inicio, p.fecha_termino,
                          p.observaciones, p.activo, ", ".join(d.codigo for d in n.depende_de)))
        for nt in n.tareas:
            tp = nt.tarea
            filas.append(Fila(2, tp.codigo, p.orden, p.nombre, tp.nombre, "", tp.responsable.nombre if tp.responsable else "", ETIQUETA_ESTADO[tp.estado_plan], tp.fecha_inicio,
                              tp.fecha_termino, tp.observaciones, tp.activa))
            for t in nt.subtareas:
                filas.append(Fila(3, t.codigo, p.orden, p.nombre, tp.nombre, t.subtarea, t.cargo_ejecuta.nombre, ETIQUETA_ESTADO[t.estado_plan], t.fecha_inicio, t.fecha_termino,
                                  t.observaciones, t.activa))
    return filas
