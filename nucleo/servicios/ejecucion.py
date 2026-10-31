"""Ejecución de tareas: marcar, revisar, devolver, «recibido» y «no aplica».

Todas las reglas de permiso y de segregación de funciones se validan aquí, en el servidor:
- La hora de la marca la fija el servidor; ninguna función acepta una hora.
- Cada persona marca solo lo suyo; nadie revisa lo que marcó; el solicitante de «no aplica» no lo aprueba.
- Las acciones por excepción exigen motivo y quedan marcadas en la auditoría.
"""
from django.db import transaction
from django.utils import timezone

from nucleo import permisos
from nucleo.models import Ocurrencia, SolicitudNoAplica
from nucleo.servicios import auditoria
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado


def _estado(o: Ocurrencia) -> dict:
    return {"estado": o.estado, "tipo_marca": o.tipo_marca, "fecha_limite": str(o.fecha_limite)}


def _exigir_rol(usuario):
    rol = permisos.rol_de(usuario)
    if rol is None:
        raise PermisoDenegado("Tu cuenta no tiene un perfil asignado.")
    return rol


def _exigir_periodo_abierto(o: Ocurrencia):
    if o.periodo.estado == "cerrado":
        raise ErrorDeNegocio(f"El período {o.periodo} está cerrado: no admite cambios.")


def _es_revisor(usuario, o: Ocurrencia) -> bool:
    return o.cargo_revisa_id is not None and o.cargo_revisa_id in permisos.cargos_vigentes_de(usuario)


def _es_dueno(usuario, rol: str, o: Ocurrencia) -> bool:
    c = permisos.colaborador_de(usuario)
    return rol in permisos.QUE_MARCAN and c is not None and o.colaborador_id == c.pk


def _marcar(o: Ocurrencia, usuario, accion: str, **extra):
    antes = _estado(o)
    ahora = timezone.now()  # la hora la fija el servidor
    o.estado, o.hecha_en, o.hecha_por = Ocurrencia.HECHA, ahora, usuario
    if o.primera_hecha_en is None:
        o.primera_hecha_en = ahora  # base del KPI «a tiempo»: nunca cambia
    for campo, valor in extra.items():
        setattr(o, campo, valor)
    o.save()
    auditoria.registrar(accion, usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o), motivo=extra.get("motivo_excepcion", ""))


@transaction.atomic
def marcar_hecha(o: Ocurrencia, usuario):
    rol = _exigir_rol(usuario)
    if o.tipo_marca == "RECIBIDA":
        raise PermisoDenegado("Las tareas de responsables externos las marca como «Recibido» quien las revisa.")
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo puedes marcar tus propias tareas.")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede marcar una tarea pendiente o devuelta (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    _marcar(o, usuario, "ocurrencia.hecha")


@transaction.atomic
def marcar_recibida(o: Ocurrencia, usuario):
    _exigir_rol(usuario)
    if not _es_revisor(usuario, o):
        raise PermisoDenegado("Solo quien revisa esta tarea puede marcarla como recibida.")
    if o.tipo_marca != "RECIBIDA":
        raise ErrorDeNegocio("Esta tarea no es de un responsable externo: la marca su ejecutor como «Hecha».")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede marcar una tarea pendiente (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    _marcar(o, usuario, "ocurrencia.recibida")


@transaction.atomic
def marcar_por_excepcion(o: Ocurrencia, usuario, motivo: str):
    rol = _exigir_rol(usuario)
    if rol != permisos.GERENTE:
        raise PermisoDenegado("Solo el Gerente puede registrar una marca por excepción.")
    if not (motivo or "").strip():
        raise ErrorDeNegocio("La marca por excepción exige un motivo.")
    if o.tipo_marca == "RECIBIDA":
        raise ErrorDeNegocio("Las tareas de externos se marcan como recibidas por quien las revisa.")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede marcar una tarea pendiente o devuelta (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    _marcar(o, usuario, "ocurrencia.hecha_por_excepcion", por_excepcion=True, motivo_excepcion=motivo.strip())


@transaction.atomic
def marcar_bloqueada(o: Ocurrencia, usuario, motivo: str):
    """El dueño avisa que no puede avanzar (por ejemplo, falta un insumo). Exige motivo; aparece como riesgo en el panel."""
    rol = _exigir_rol(usuario)
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo puedes bloquear tus propias tareas.")
    if not (motivo or "").strip():
        raise ErrorDeNegocio("Bloquear una tarea exige un motivo.")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede bloquear una tarea pendiente o devuelta (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    antes = _estado(o)
    o.estado, o.motivo_bloqueo = Ocurrencia.BLOQUEADA, motivo.strip()
    o.save()
    auditoria.registrar("ocurrencia.bloqueada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o), motivo=o.motivo_bloqueo)


@transaction.atomic
def retomar(o: Ocurrencia, usuario):
    rol = _exigir_rol(usuario)
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo puedes retomar tus propias tareas.")
    if o.estado != Ocurrencia.BLOQUEADA:
        raise ErrorDeNegocio(f"Solo se puede retomar una tarea bloqueada (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    antes = _estado(o)
    o.estado = Ocurrencia.PENDIENTE
    o.save()
    auditoria.registrar("ocurrencia.retomada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o))


def _exigir_puede_revisar(o: Ocurrencia, usuario):
    _exigir_rol(usuario)
    if o.tipo_marca == "RECIBIDA":
        raise ErrorDeNegocio("Una tarea recibida no requiere revisión.")
    if o.estado != Ocurrencia.HECHA:
        raise ErrorDeNegocio(f"La tarea debe estar hecha para revisarla (estado actual: {o.estado}).")
    if o.hecha_por_id == usuario.pk:
        raise PermisoDenegado("No puedes revisar una tarea que marcaste tú: la revisión propia no está permitida.")
    if not _es_revisor(usuario, o):
        raise PermisoDenegado("Solo quien revisa esta tarea puede revisarla o devolverla.")
    _exigir_periodo_abierto(o)


@transaction.atomic
def revisar(o: Ocurrencia, usuario):
    _exigir_puede_revisar(o, usuario)
    antes = _estado(o)
    ahora = timezone.now()
    o.estado, o.revisada_por, o.revisada_en = Ocurrencia.REVISADA, usuario, ahora
    if o.primera_revision_en is None:
        o.primera_revision_en = ahora
    o.save()
    auditoria.registrar("ocurrencia.revisada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o))


@transaction.atomic
def devolver(o: Ocurrencia, usuario, comentario: str):
    _exigir_puede_revisar(o, usuario)
    if not (comentario or "").strip():
        raise ErrorDeNegocio("Al devolver una tarea hay que escribir un comentario.")
    antes = _estado(o)
    o.estado, o.comentario_devolucion, o.revisada_por, o.revisada_en = Ocurrencia.DEVUELTA, comentario.strip(), None, None
    o.veces_devuelta += 1
    if o.primera_revision_en is None:
        o.primera_revision_en = timezone.now()
    o.save()
    auditoria.registrar("ocurrencia.devuelta", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o), motivo=comentario.strip())


# ---- No aplica --------------------------------------------------------------------------------------


@transaction.atomic
def solicitar_no_aplica(o: Ocurrencia, usuario, motivo: str) -> SolicitudNoAplica:
    rol = _exigir_rol(usuario)
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo puedes pedir «no aplica» para tus propias tareas.")
    if not (motivo or "").strip():
        raise ErrorDeNegocio("«No aplica» exige un motivo.")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede pedir «no aplica» de una tarea pendiente (estado actual: {o.estado}).")
    if o.solicitudes_no_aplica.filter(estado="pendiente").exists():
        raise ErrorDeNegocio("Ya hay una solicitud de «no aplica» pendiente para esta tarea.")
    _exigir_periodo_abierto(o)
    s = SolicitudNoAplica.objects.create(ocurrencia=o, motivo=motivo.strip(), solicitante=usuario)
    auditoria.registrar("no_aplica.solicitada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, motivo=s.motivo)
    return s


@transaction.atomic
def resolver_no_aplica(s: SolicitudNoAplica, usuario, aprobar: bool):
    rol = _exigir_rol(usuario)
    o = s.ocurrencia
    if s.estado != "pendiente":
        raise ErrorDeNegocio("La solicitud ya fue resuelta.")
    if s.solicitante_id == usuario.pk:
        raise PermisoDenegado("No puedes resolver una solicitud de «no aplica» que hiciste tú.")
    if not (rol == permisos.GERENTE or (rol in (permisos.JEFATURA,) and _es_revisor(usuario, o))):
        raise PermisoDenegado("Solo el revisor de la tarea o el Gerente pueden resolver «no aplica».")
    _exigir_periodo_abierto(o)
    s.estado, s.resuelta_por, s.resuelta_en = ("aprobada" if aprobar else "rechazada"), usuario, timezone.now()
    s.save()
    if aprobar:
        antes = _estado(o)
        o.estado = Ocurrencia.NO_APLICA
        o.save()
        auditoria.registrar("no_aplica.aprobada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues=_estado(o), motivo=s.motivo)
    else:
        auditoria.registrar("no_aplica.rechazada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, motivo=s.motivo)
