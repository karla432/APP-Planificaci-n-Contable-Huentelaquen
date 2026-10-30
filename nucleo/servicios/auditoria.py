"""Bitácora append-only con sello encadenado.

Los triggers de la migración 0002 impiden UPDATE y DELETE. Como quien tenga acceso al archivo de la base puede quitarlos,
cada evento lleva además un sello SHA-256 que encadena el del evento anterior: `verificar_cadena` detecta cualquier fila alterada.
"""
import hashlib
import json
from datetime import timezone as _tz

from django.db import transaction
from django.utils import timezone

from nucleo.models import EventoAuditoria


def _momento_texto(momento) -> str:
    return momento.astimezone(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sello(momento, usuario_id, accion, entidad, entidad_id, antes, despues, motivo, sello_anterior) -> str:
    cuerpo = json.dumps(
        [_momento_texto(momento), usuario_id, accion, entidad, entidad_id, antes, despues, motivo, sello_anterior],
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()


def registrar(accion, usuario=None, entidad="", entidad_id="", antes=None, despues=None, motivo="") -> EventoAuditoria:
    with transaction.atomic():
        ultimo = EventoAuditoria.objects.order_by("-id").first()
        anterior = ultimo.sello if ultimo else ""
        momento = timezone.now()
        usuario_id = usuario.pk if usuario is not None else None
        sello = _sello(momento, usuario_id, accion, entidad, str(entidad_id), antes, despues, motivo, anterior)
        return EventoAuditoria.objects.create(
            momento=momento, usuario=usuario, usuario_texto=str(usuario) if usuario is not None else "",
            accion=accion, entidad=entidad, entidad_id=str(entidad_id), antes=antes, despues=despues,
            motivo=motivo, sello_anterior=anterior, sello=sello,
        )


def verificar_cadena() -> list[int]:
    """Ids de los eventos cuyo sello no calza con su contenido o que rompen el encadenado. Lista vacía = íntegra."""
    malos, anterior = [], ""
    for ev in EventoAuditoria.objects.order_by("id"):
        esperado = _sello(ev.momento, ev.usuario_id, ev.accion, ev.entidad, ev.entidad_id, ev.antes, ev.despues, ev.motivo, ev.sello_anterior)
        if ev.sello != esperado or ev.sello_anterior != anterior:
            malos.append(ev.pk)
        anterior = ev.sello
    return malos
