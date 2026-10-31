"""Códigos jerárquicos OO-PPP.TT.SSS (Karla, 31-10-2026).

    Nivel 1 · Proceso     02-VEN          OO = orden de ejecución (campo aparte) · PPP = sigla de tres letras
    Nivel 2 · Tarea       02-VEN.01       TT = correlativo de la tarea dentro del proceso
    Nivel 3 · Subtarea    02-VEN.01.003   SSS = correlativo de la subtarea dentro de la tarea

- Todo código se genera solo; las personas nunca lo escriben.
- La identidad de cada cosa es su clave (pk); el código es una etiqueta que sigue a su posición. Si el orden de un proceso cambia, el prefijo OO de todo
  su árbol se actualiza en la misma transacción y el código anterior queda en `CambioDeCodigo` (sigue siendo buscable).
- Un código que no tiene esta forma (por ejemplo, los de las pruebas) no se toca nunca.
"""
import re

from nucleo.models import CambioDeCodigo, Proceso, Tarea, TareaPrincipal

PATRON = re.compile(r"^\d{2}-[A-Z]{3}(\.\d{2}(\.\d{3})?)?$")
MAX_TAREAS = 99
MAX_SUBTAREAS = 999


def es_jerarquico(codigo: str) -> bool:
    return bool(PATRON.match(codigo or ""))


def _anotar(cambios: list, nivel: int, objeto_id: int, anterior: str, nuevo: str, motivo: str, usuario=None):
    if anterior and es_jerarquico(anterior) and anterior != nuevo:
        cambios.append(CambioDeCodigo(nivel=nivel, objeto_id=objeto_id, codigo_anterior=anterior, codigo_nuevo=nuevo, motivo=motivo[:160], usuario=usuario))


def al_cambiar_el_codigo_del_proceso(p: Proceso, anterior: str, motivo: str = "Cambió el orden o la sigla del proceso", usuario=None):
    """El proceso ya tiene su código nuevo: lo registra y actualiza, en cascada, las tareas y subtareas. Se llama desde `Proceso.save`."""
    cambios: list[CambioDeCodigo] = []
    _anotar(cambios, 1, p.pk, anterior, p.codigo, motivo, usuario)
    for tp in TareaPrincipal.objects.filter(proceso=p):
        nuevo_tp = f"{p.codigo}.{tp.numero:02d}"
        _anotar(cambios, 2, tp.pk, tp.codigo, nuevo_tp, motivo, usuario)
        if tp.codigo != nuevo_tp:
            TareaPrincipal.objects.filter(pk=tp.pk).update(codigo=nuevo_tp)
        for t in Tarea.objects.filter(padre=tp):
            nuevo_t = f"{nuevo_tp}.{t.numero:03d}"
            if t.codigo != nuevo_t and es_jerarquico(t.codigo):
                _anotar(cambios, 3, t.pk, t.codigo, nuevo_t, motivo, usuario)
                Tarea.objects.filter(pk=t.pk).update(codigo=nuevo_t)
    CambioDeCodigo.objects.bulk_create(cambios)


def _tarea_principal(proceso: Proceso, nombre: str) -> TareaPrincipal:
    existente = TareaPrincipal.objects.filter(proceso=proceso, nombre__iexact=nombre).first()
    return existente or TareaPrincipal.objects.create(proceso=proceso, nombre=nombre)


def preparar_subtarea(t: Tarea):
    """Antes de guardar una subtarea: que cuelgue de su tarea (nivel 2), tenga su correlativo y su código. Se llama desde `Tarea.save`."""
    nombre = re.sub(r"\s+", " ", t.tarea_principal or "").strip()
    padre = t.padre if t.padre_id else None
    if padre is not None and (padre.proceso_id != t.proceso_id or padre.nombre.casefold() != nombre.casefold()):
        padre = None  # cambió de proceso o de tarea: se vuelve a ubicar
    if padre is None:
        padre = _tarea_principal(t.proceso, nombre)
    t.tarea_principal = padre.nombre  # una sola forma de escribir la tarea
    cambio_de_padre = t.padre_id != padre.pk
    anterior = t.codigo
    t.padre = padre
    if not t.numero or cambio_de_padre:
        otras = Tarea.objects.filter(padre=padre)
        if t.pk:
            otras = otras.exclude(pk=t.pk)
        t.numero = (max(otras.values_list("numero", flat=True), default=0)) + 1
    if t.numero > MAX_SUBTAREAS:
        raise ValueError("Una tarea admite hasta 999 subtareas (el correlativo SSS tiene tres dígitos).")
    if not t.codigo or es_jerarquico(t.codigo):
        t.codigo = f"{padre.codigo}.{t.numero:03d}"
        if t.pk and anterior != t.codigo:
            cambios: list[CambioDeCodigo] = []
            _anotar(cambios, 3, t.pk, anterior, t.codigo, "La subtarea cambió de tarea o de proceso")
            CambioDeCodigo.objects.bulk_create(cambios)
