"""Estructura de la planificación: procesos (nivel 1), tareas (nivel 2) y su orden de ejecución y dependencias.

Las subtareas (nivel 3) se crean y editan en `mantenedor.crear_tarea` / `editar_tarea`; allí se les asigna su tarea y su código.

- Los códigos (OO-PPP.TT.SSS) los genera `codigos`; aquí solo se cambia lo que los afecta (orden, sigla, tarea de una subtarea) y la cascada es automática.
- Reordenar es una operación controlada: una sola transacción, orden único, el prefijo de todo el árbol se actualiza y nunca se deja a un proceso
  antes de otro del que depende.
- Permisos: Gerente y Jefatura (los mismos que editan tareas). Cada cambio queda en la bitácora.
"""
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.db.models import F

from nucleo import permisos, siglas
from nucleo.models import ESTADOS_PLAN, Cargo, DependenciaProceso, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import auditoria, codigos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado

MAX_PROCESOS = 99


def _exigir(usuario):
    if permisos.rol_de(usuario) not in (permisos.GERENTE, permisos.JEFATURA):
        raise PermisoDenegado("Solo el Gerente y la Jefatura pueden modificar la estructura de la planificación.")


def _norm(texto: str) -> str:
    return " ".join((texto or "").split())


@dataclass
class DatosPlan:
    """Responsable, estado, fechas y observaciones. Valen para procesos y tareas."""

    responsable_id: int | None = None
    estado_plan: str = "pendiente"
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    observaciones: str = ""


def _validar_plan(d: DatosPlan):
    if d.estado_plan not in dict(ESTADOS_PLAN):
        raise ErrorDeNegocio("El estado elegido no existe.")
    if d.fecha_inicio and d.fecha_termino and d.fecha_termino < d.fecha_inicio:
        raise ErrorDeNegocio("La fecha de término no puede ser anterior a la fecha de inicio.")
    if d.responsable_id and not Cargo.objects.filter(pk=d.responsable_id).exists():
        raise ErrorDeNegocio("El responsable elegido no existe.")


def _poner_plan(obj, d: DatosPlan):
    obj.responsable_id, obj.estado_plan = d.responsable_id or None, d.estado_plan
    obj.fecha_inicio, obj.fecha_termino, obj.observaciones = d.fecha_inicio, d.fecha_termino, d.observaciones.strip()


def _plan_de(obj) -> dict:
    return {"responsable": obj.responsable_id, "estado_plan": obj.estado_plan, "fecha_inicio": str(obj.fecha_inicio or ""), "fecha_termino": str(obj.fecha_termino or ""),
            "observaciones": obj.observaciones}


# ---- Procesos ----------------------------------------------------------------------------------------------------------


def validar_sigla(sigla: str, excepto: Proceso | None = None) -> str:
    sigla = (sigla or "").strip().upper()
    if not siglas.valida(sigla):
        raise ErrorDeNegocio("La sigla son exactamente 3 letras, de la A a la Z y sin tildes (por ejemplo VEN).")
    repetida = Proceso.objects.filter(sigla=sigla)
    if excepto is not None:
        repetida = repetida.exclude(pk=excepto.pk)
    if repetida.exists():
        raise ErrorDeNegocio(f"La sigla {sigla} ya la usa otro proceso.")
    return sigla


def _nombre_de_proceso(nombre: str, excepto: Proceso | None = None) -> str:
    nombre = _norm(nombre)
    if not nombre:
        raise ErrorDeNegocio("Falta el nombre del proceso.")
    repetido = Proceso.objects.filter(nombre__iexact=nombre)
    if excepto is not None:
        repetido = repetido.exclude(pk=excepto.pk)
    if repetido.exists():
        raise ErrorDeNegocio("Ese proceso ya existe.")
    return nombre


@transaction.atomic
def crear_proceso(usuario, nombre: str, sigla: str = "", plan: DatosPlan | None = None, orden: int | None = None, validar_permiso: bool = True) -> Proceso:
    """Un proceso nuevo queda al final del orden (o en la posición pedida). Sin sigla, la app propone una."""
    if validar_permiso:
        _exigir(usuario)
    nombre = _nombre_de_proceso(nombre)
    if Proceso.objects.count() >= MAX_PROCESOS:
        raise ErrorDeNegocio(f"Se admiten hasta {MAX_PROCESOS} procesos (el orden OO tiene dos dígitos).")
    sigla = validar_sigla(sigla) if sigla else siglas.derivar(nombre, set(Proceso.objects.values_list("sigla", flat=True)))
    plan = plan or DatosPlan()
    _validar_plan(plan)
    p = Proceso(nombre=nombre, sigla=sigla)
    _poner_plan(p, plan)
    p.save()
    if orden is not None and orden != p.orden:
        mover_a_posicion(usuario, p, orden, validar_permiso=validar_permiso)
        p.refresh_from_db()
    auditoria.registrar("proceso.creado", usuario=usuario, entidad="Proceso", entidad_id=p.pk, despues={"nombre": p.nombre, "codigo": p.codigo, **_plan_de(p)})
    return p


@transaction.atomic
def editar_proceso(usuario, p: Proceso, nombre: str, sigla: str, plan: DatosPlan) -> Proceso:
    """Cambiar la sigla cambia el código de todo el proceso (queda el anterior en el historial). El orden se cambia solo con `reordenar_procesos`."""
    _exigir(usuario)
    antes = {"nombre": p.nombre, "sigla": p.sigla, "codigo": p.codigo, **_plan_de(p)}
    p.nombre = _nombre_de_proceso(nombre, excepto=p)
    p.sigla = validar_sigla(sigla, excepto=p)
    _validar_plan(plan)
    _poner_plan(p, plan)
    p.save()
    auditoria.registrar("proceso.editado", usuario=usuario, entidad="Proceso", entidad_id=p.pk, antes=antes, despues={"nombre": p.nombre, "sigla": p.sigla, "codigo": p.codigo, **_plan_de(p)})
    return p


@transaction.atomic
def fijar_activo_proceso(usuario, p: Proceso, activo: bool, con_hijos: bool = False) -> Proceso:
    """Desactivar un proceso desactiva también sus tareas y subtareas (dejan de generarse). Reactivarlo no reactiva lo de abajo salvo que se pida."""
    _exigir(usuario)
    if p.activo == activo and not (activo and con_hijos):
        return p
    p.activo = activo
    p.save(update_fields=["activo"])
    n_tareas = n_subtareas = 0
    if not activo or con_hijos:
        n_tareas = TareaPrincipal.objects.filter(proceso=p).exclude(activa=activo).update(activa=activo)
        n_subtareas = Tarea.objects.filter(proceso=p).exclude(activa=activo).update(activa=activo)
    auditoria.registrar("proceso.activado" if activo else "proceso.desactivado", usuario=usuario, entidad="Proceso", entidad_id=p.pk, despues={"tareas": n_tareas, "subtareas": n_subtareas})
    return p


# ---- Orden de ejecución ---------------------------------------------------------------------------------------------------


def _dependencias() -> dict[int, set[int]]:
    mapa: dict[int, set[int]] = {}
    for proceso_id, depende_de_id in DependenciaProceso.objects.values_list("proceso_id", "depende_de_id"):
        mapa.setdefault(proceso_id, set()).add(depende_de_id)
    return mapa


def _violaciones(orden_de: dict[int, int], deps: dict[int, set[int]]) -> list[tuple[int, int]]:
    """(proceso, del que depende) cuando el prerrequisito no queda antes en el orden."""
    return [(p, d) for p, ds in deps.items() for d in ds if p in orden_de and d in orden_de and orden_de[d] >= orden_de[p]]


@transaction.atomic
def reordenar_procesos(usuario, ids_en_orden: list[int], motivo: str = "", validar_permiso: bool = True, desde: int | None = None) -> list[Proceso]:
    """Fija el orden de ejecución de todos los procesos (lista completa, sin repetidos). Actualiza los códigos de todo el árbol, sin duplicados.
    `validar_permiso=False` solo lo usan las cargas que ya validaron el permiso de quien las pidió."""
    if validar_permiso:
        _exigir(usuario)
    existentes = {p.pk: p for p in Proceso.objects.all()}
    if len(ids_en_orden) != len(set(ids_en_orden)) or set(ids_en_orden) != set(existentes):
        raise ErrorDeNegocio("El orden debe incluir todos los procesos, cada uno una sola vez.")
    if desde is None:  # si existe el proceso 00 («Control del cierre»), el primero de la lista es el 00
        desde = 0 if any(p.orden == 0 for p in existentes.values()) else 1
    nuevo = {pk: i for i, pk in enumerate(ids_en_orden, start=desde)}
    malas = _violaciones(nuevo, _dependencias())
    if malas:
        p, d = malas[0]
        raise ErrorDeNegocio(f"«{existentes[p].nombre}» depende de «{existentes[d].nombre}», así que no puede ir antes. Cambia la dependencia o el orden.")
    antes = {existentes[pk].codigo: pk for pk in existentes}
    if all(existentes[pk].orden == i for pk, i in nuevo.items()):
        return list(Proceso.objects.all())
    Proceso.objects.update(orden=F("orden") + 1000)  # libera el rango: el orden es único y no puede haber choques a medio camino
    for pk in ids_en_orden:
        p = Proceso.objects.get(pk=pk)
        p.orden = nuevo[pk]
        p.save()  # recalcula el código y el de todo su árbol, y deja el anterior en el historial
    despues = list(Proceso.objects.all())
    auditoria.registrar("proceso.reordenado", usuario=usuario, entidad="Proceso", antes={"orden": list(antes)}, despues={"orden": [p.codigo for p in despues]}, motivo=motivo)
    return despues


def mover_proceso(usuario, p: Proceso, hacia: str) -> list[Proceso]:
    """Sube o baja un lugar."""
    ids = list(Proceso.objects.values_list("pk", flat=True))
    i = ids.index(p.pk)
    j = i - 1 if hacia == "subir" else i + 1
    if not 0 <= j < len(ids):
        return list(Proceso.objects.all())
    ids[i], ids[j] = ids[j], ids[i]
    return reordenar_procesos(usuario, ids, motivo=f"{p.nombre}: {hacia}")


def mover_a_posicion(usuario, p: Proceso, posicion: int, validar_permiso: bool = True) -> list[Proceso]:
    ids = [pk for pk in Proceso.objects.values_list("pk", flat=True) if pk != p.pk]
    if not 1 <= posicion <= len(ids) + 1:
        raise ErrorDeNegocio(f"La posición debe estar entre 1 y {len(ids) + 1}.")
    ids.insert(posicion - 1, p.pk)
    return reordenar_procesos(usuario, ids, motivo=f"{p.nombre} pasa a la posición {posicion}", validar_permiso=validar_permiso)


# ---- Dependencias y etapas -------------------------------------------------------------------------------------------------


def _alcanza(origen: int, destino: int, deps: dict[int, set[int]]) -> bool:
    """¿Siguiendo «depende de» desde `origen` se llega a `destino`?"""
    visto, pila = set(), [origen]
    while pila:
        actual = pila.pop()
        if actual == destino:
            return True
        if actual in visto:
            continue
        visto.add(actual)
        pila.extend(deps.get(actual, ()))
    return False


@transaction.atomic
def fijar_dependencias(usuario, p: Proceso, depende_de_ids, validar_permiso: bool = True) -> Proceso:
    """Deja a `p` dependiendo exactamente de esos procesos. Rechaza dependerse a sí mismo, ciclos y prerrequisitos que van después en el orden."""
    if validar_permiso:
        _exigir(usuario)
    nuevos = {int(i) for i in depende_de_ids}
    existentes = {x.pk: x for x in Proceso.objects.filter(pk__in=nuevos | {p.pk})}
    if p.pk in nuevos:
        raise ErrorDeNegocio("Un proceso no puede depender de sí mismo.")
    if not nuevos <= set(existentes):
        raise ErrorDeNegocio("Alguno de los procesos elegidos no existe.")
    deps = _dependencias()
    deps[p.pk] = set(nuevos)
    for d in nuevos:
        if existentes[d].orden >= p.orden:
            raise ErrorDeNegocio(f"«{p.nombre}» no puede depender de «{existentes[d].nombre}» porque ese proceso va después en el orden. Reordénalos primero.")
        if _alcanza(d, p.pk, deps):
            raise ErrorDeNegocio(f"Eso crearía un ciclo: «{existentes[d].nombre}» ya depende de «{p.nombre}».")
    antes = sorted(DependenciaProceso.objects.filter(proceso=p).values_list("depende_de__codigo", flat=True))
    DependenciaProceso.objects.filter(proceso=p).delete()
    DependenciaProceso.objects.bulk_create([DependenciaProceso(proceso=p, depende_de_id=d) for d in sorted(nuevos)])
    despues = sorted(existentes[d].codigo for d in nuevos)
    if antes != despues:
        auditoria.registrar("proceso.dependencias", usuario=usuario, entidad="Proceso", entidad_id=p.pk, antes={"depende_de": antes}, despues={"depende_de": despues})
    return p


@dataclass
class Etapa:
    numero: int
    procesos: list = field(default_factory=list)

    @property
    def en_paralelo(self) -> bool:
        return len(self.procesos) > 1


def etapas() -> list[Etapa]:
    """Agrupa los procesos activos en etapas: la 1 no depende de nadie; cada una de las siguientes, de algo de las anteriores. Los de una misma etapa pueden
    ejecutarse en paralelo. Dentro de cada etapa se respeta el orden de ejecución."""
    procesos = list(Proceso.objects.filter(activo=True))
    ids = {p.pk for p in procesos}
    deps = {p: {d for d in ds if d in ids} for p, ds in _dependencias().items() if p in ids}
    nivel: dict[int, int] = {}

    def de(pk, en_curso=()):
        if pk not in nivel:
            nivel[pk] = 1 + max((de(d, en_curso + (pk,)) for d in deps.get(pk, ()) if d not in en_curso), default=0)
        return nivel[pk]

    for p in procesos:
        de(p.pk)
    resultado: dict[int, Etapa] = {}
    for p in procesos:
        resultado.setdefault(nivel[p.pk], Etapa(nivel[p.pk])).procesos.append(p)
    return [resultado[n] for n in sorted(resultado)]


def dependencias_de() -> dict[int, list[Proceso]]:
    """Proceso → procesos de los que depende (para mostrar «depende de»)."""
    por_id = {p.pk: p for p in Proceso.objects.all()}
    return {pk: sorted((por_id[d] for d in ds), key=lambda x: x.orden) for pk, ds in _dependencias().items()}


# ---- Tareas (nivel 2) ----------------------------------------------------------------------------------------------------------


def _nombre_de_tarea(proceso: Proceso, nombre: str, excepto: TareaPrincipal | None = None) -> str:
    nombre = _norm(nombre)
    if not nombre:
        raise ErrorDeNegocio("Falta el nombre de la tarea.")
    repetida = TareaPrincipal.objects.filter(proceso=proceso, nombre__iexact=nombre)
    if excepto is not None:
        repetida = repetida.exclude(pk=excepto.pk)
    if repetida.exists():
        raise ErrorDeNegocio("Ese proceso ya tiene una tarea con ese nombre.")
    return nombre


@transaction.atomic
def crear_tarea_principal(usuario, proceso: Proceso, nombre: str, plan: DatosPlan | None = None) -> TareaPrincipal:
    _exigir(usuario)
    nombre = _nombre_de_tarea(proceso, nombre)
    if not Proceso.objects.filter(pk=proceso.pk, activo=True).exists():
        raise ErrorDeNegocio("El proceso está desactivado: actívalo antes de agregarle tareas.")
    if TareaPrincipal.objects.filter(proceso=proceso).count() >= codigos.MAX_TAREAS:
        raise ErrorDeNegocio(f"Un proceso admite hasta {codigos.MAX_TAREAS} tareas.")
    plan = plan or DatosPlan()
    _validar_plan(plan)
    tp = TareaPrincipal(proceso=proceso, nombre=nombre)
    _poner_plan(tp, plan)
    tp.save()
    auditoria.registrar("tarea_principal.creada", usuario=usuario, entidad="TareaPrincipal", entidad_id=tp.pk, despues={"codigo": tp.codigo, "nombre": tp.nombre, **_plan_de(tp)})
    return tp


@transaction.atomic
def editar_tarea_principal(usuario, tp: TareaPrincipal, nombre: str, plan: DatosPlan) -> TareaPrincipal:
    """Renombrar actualiza el texto «tarea principal» de todas sus subtareas; el código no cambia."""
    _exigir(usuario)
    antes = {"nombre": tp.nombre, **_plan_de(tp)}
    nuevo = _nombre_de_tarea(tp.proceso, nombre, excepto=tp)
    _validar_plan(plan)
    tp.nombre = nuevo
    _poner_plan(tp, plan)
    tp.save()
    Tarea.objects.filter(padre=tp).update(tarea_principal=nuevo)
    auditoria.registrar("tarea_principal.editada", usuario=usuario, entidad="TareaPrincipal", entidad_id=tp.pk, antes=antes, despues={"nombre": tp.nombre, **_plan_de(tp)})
    return tp


@transaction.atomic
def fijar_activa_tarea_principal(usuario, tp: TareaPrincipal, activa: bool, con_hijos: bool = False) -> TareaPrincipal:
    _exigir(usuario)
    if activa and not Proceso.objects.filter(pk=tp.proceso_id, activo=True).exists():  # se lee de nuevo: el objeto en memoria puede estar desactualizado
        raise ErrorDeNegocio("El proceso está desactivado: actívalo primero.")
    tp.activa = activa
    tp.save(update_fields=["activa"])
    n = 0
    if not activa or con_hijos:
        n = Tarea.objects.filter(padre=tp).exclude(activa=activa).update(activa=activa)
    auditoria.registrar("tarea_principal.activada" if activa else "tarea_principal.desactivada", usuario=usuario, entidad="TareaPrincipal", entidad_id=tp.pk, despues={"subtareas": n})
    return tp


# ---- Catálogo base ------------------------------------------------------------------------------------------------------------------


@transaction.atomic
def cargar_catalogo_base(usuario, validar_permiso: bool = True) -> dict:
    """Agrega los procesos del catálogo base que aún no existen (por sigla o por nombre), al final del orden y con sus dependencias propuestas.
    Todo es editable después. Una dependencia que contradiga el orden actual se omite y se informa.
    `validar_permiso=False` solo lo usa el comando de ejemplo de desarrollo."""
    if validar_permiso:
        _exigir(usuario)
    creados, existentes, omitidas = [], [], []
    for sigla, nombre, _ in siglas.CATALOGO_BASE:
        if Proceso.objects.filter(sigla=sigla).exists() or Proceso.objects.filter(nombre__iexact=nombre).exists():
            existentes.append(sigla)
            continue
        crear_proceso(usuario, nombre, sigla, validar_permiso=validar_permiso)
        creados.append(sigla)
    por_sigla = {p.sigla: p for p in Proceso.objects.all()}
    for sigla, _, deps in siglas.CATALOGO_BASE:
        p = por_sigla.get(sigla)
        if p is None or sigla not in creados or not deps:
            continue
        validas = [d for d in deps if d in por_sigla and por_sigla[d].orden < p.orden]
        omitidas += [f"{sigla}→{d}" for d in deps if d not in validas]
        if validas:
            fijar_dependencias(usuario, p, [por_sigla[d].pk for d in validas], validar_permiso=validar_permiso)
    resumen = {"creados": creados, "ya_existian": existentes, "dependencias_omitidas": omitidas}
    auditoria.registrar("catalogo.cargado", usuario=usuario, entidad="Proceso", despues=resumen)
    return resumen
