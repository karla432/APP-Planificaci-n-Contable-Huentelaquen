"""Ejecución de tareas: marcar, revisar, devolver, «recibido» y «no aplica».

Todas las reglas de permiso y de segregación de funciones se validan aquí, en el servidor:
- La hora de la marca la fija el servidor; ninguna función acepta una hora.
- Cada persona marca solo lo suyo; nadie revisa lo que marcó; el solicitante de «no aplica» no lo aprueba.
- Las acciones por excepción exigen motivo y quedan marcadas en la auditoría.
"""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from nucleo import permisos
from nucleo.models import Asignacion, Colaborador, EventoAuditoria, Ocurrencia, SolicitudNoAplica
from nucleo.servicios import auditoria, evidencias
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


def parsear_horas(texto) -> int | None:
    """«1,5», «1.5» o «1:30» → minutos. Vacío → None (las horas son opcionales). Lo que no se entiende se rechaza con un mensaje claro."""
    t = (texto or "").strip()
    if not t:
        return None
    try:
        if ":" in t:
            horas, minutos = (int(x) for x in t.split(":"))
            if not 0 <= minutos < 60:
                raise ValueError
            total = horas * 60 + minutos
        else:
            total = round(float(t.replace(",", ".")) * 60)
    except (ValueError, OverflowError):
        raise ErrorDeNegocio("Escribe las horas como 1,5 o como 1:30 (horas y minutos).") from None
    if not 1 <= total <= 24 * 60:
        raise ErrorDeNegocio("Las horas deben ser más de 0 y no más de 24.")
    return total


@transaction.atomic
def marcar_hecha(o: Ocurrencia, usuario, minutos_reales: int | None = None):
    rol = _exigir_rol(usuario)
    if o.tipo_marca == "RECIBIDA":
        raise PermisoDenegado("Las tareas de responsables externos las marca como «Recibido» quien las revisa.")
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo puedes marcar tus propias tareas.")
    if o.estado not in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
        raise ErrorDeNegocio(f"Solo se puede marcar una tarea pendiente o devuelta (estado actual: {o.estado}).")
    _exigir_periodo_abierto(o)
    _marcar(o, usuario, "ocurrencia.hecha", **({"minutos_reales": minutos_reales} if minutos_reales is not None else {}))


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


# ---- Qué puede hacer cada persona, comentarios e historial -------------------------------------------------


def puede_registrar_horas(o: Ocurrencia, usuario) -> bool:
    rol = permisos.rol_de(usuario)
    return rol is not None and o.tipo_marca == "HECHA" and o.estado != Ocurrencia.NO_APLICA and o.periodo.estado != "cerrado" and _es_dueno(usuario, rol, o)


@transaction.atomic
def registrar_horas(o: Ocurrencia, usuario, minutos: int | None):
    """Quien ejecuta la tarea anota (o corrige) las horas reales que ocupó. Cada cambio queda en la bitácora."""
    rol = _exigir_rol(usuario)
    if o.tipo_marca == "RECIBIDA":
        raise PermisoDenegado("Las tareas de responsables externos no llevan horas.")
    if not _es_dueno(usuario, rol, o):
        raise PermisoDenegado("Solo quien ejecuta la tarea anota sus horas.")
    if o.estado == Ocurrencia.NO_APLICA:
        raise ErrorDeNegocio("Una tarea que no aplica no lleva horas.")
    _exigir_periodo_abierto(o)
    if minutos is None:
        raise ErrorDeNegocio("Indica las horas que ocupaste.")
    antes = {"minutos_reales": o.minutos_reales}
    o.minutos_reales = minutos
    o.save(update_fields=["minutos_reales"])
    auditoria.registrar("ocurrencia.horas_reales", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes, despues={"minutos_reales": minutos}, motivo=f"{minutos / 60:.2f} h".replace(".", ","))


ESTADOS_REASIGNABLES = (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA, Ocurrencia.BLOQUEADA)


def _cargos_internos_vigentes(colaborador: Colaborador, fecha=None) -> list:
    """Los cargos del equipo (no externos) que esa persona ejerce hoy, el principal primero."""
    fecha = fecha or timezone.localdate()
    asignaciones = (Asignacion.objects.filter(colaborador=colaborador, desde__lte=fecha, cargo__es_externo=False, cargo__activo=True).exclude(hasta__lt=fecha)
                    .select_related("cargo").order_by("cargo__orden", "cargo__nombre"))
    return [a.cargo for a in asignaciones]


def puede_reasignar(o: Ocurrencia, usuario) -> bool:
    """Cualquier persona del equipo puede cambiar quién hace una tarea que aún no está hecha (la reestructuración exige flexibilidad)."""
    rol = permisos.rol_de(usuario)
    return (rol in permisos.QUE_MARCAN and permisos.colaborador_de(usuario) is not None and o.tipo_marca == "HECHA"
            and o.estado in ESTADOS_REASIGNABLES and o.periodo.estado != "cerrado")


def candidatos_a_ejecutar(o: Ocurrencia) -> list[Colaborador]:
    """Quiénes pueden hacerla: personas activas con un cargo del equipo, que no sean quien ya la hace ni quien la revisa."""
    candidatos = []
    for c in Colaborador.objects.filter(activo=True).order_by("nombre"):
        cargos = _cargos_internos_vigentes(c)
        if cargos and c.pk != o.colaborador_id and not (o.cargo_revisa_id and any(x.pk == o.cargo_revisa_id for x in cargos)):
            candidatos.append(c)
    return candidatos


@transaction.atomic
def reasignar(o: Ocurrencia, usuario, colaborador_id, motivo: str = ""):
    """Cambia quién ejecuta ESTA vez la tarea. Queda en la bitácora con quién la tenía y quién la toma; quien la revisa nunca puede ser quien la hace."""
    _exigir_rol(usuario)
    if o.tipo_marca == "RECIBIDA":
        raise ErrorDeNegocio("Las tareas de responsables externos no se reasignan: las registra quien recibe.")
    if not puede_reasignar(o, usuario):
        if o.estado not in ESTADOS_REASIGNABLES:
            raise ErrorDeNegocio(f"Una tarea {o.get_estado_display().lower()} ya no se puede reasignar.")
        raise PermisoDenegado("Tu perfil no puede cambiar quién hace esta tarea.")
    nuevo = Colaborador.objects.filter(pk=colaborador_id, activo=True).first() if colaborador_id else None
    if nuevo is None:
        raise ErrorDeNegocio("Elige a la persona que la va a hacer.")
    if nuevo.pk == o.colaborador_id:
        raise ErrorDeNegocio("Esa persona ya es quien la hace.")
    cargos = _cargos_internos_vigentes(nuevo)
    if not cargos:
        raise ErrorDeNegocio(f"{nuevo.nombre} no tiene un cargo vigente en el equipo.")
    if o.cargo_revisa_id and any(c.pk == o.cargo_revisa_id for c in cargos):
        raise PermisoDenegado("Quien revisa la tarea no puede ser quien la hace: elige a otra persona.")
    antes = {"colaborador": o.colaborador.nombre if o.colaborador_id else None, "cargo_ejecuta": o.cargo_ejecuta.nombre}
    o.colaborador, o.cargo_ejecuta = nuevo, cargos[0]
    o.save(update_fields=["colaborador", "cargo_ejecuta"])
    auditoria.registrar("ocurrencia.reasignada", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, antes=antes,
                        despues={"colaborador": nuevo.nombre, "cargo_ejecuta": cargos[0].nombre}, motivo=(motivo or "").strip())


def acciones_disponibles(o: Ocurrencia, usuario) -> list[str]:
    """Las acciones que esta persona puede ejecutar ahora sobre la tarea (la pantalla solo ofrece estas; el servidor igual las valida)."""
    rol = permisos.rol_de(usuario)
    if rol is None or o.periodo.estado == "cerrado":
        return []
    acciones = []
    if o.tipo_marca == "HECHA" and _es_dueno(usuario, rol, o):
        if o.estado in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA):
            acciones += ["hecha", "bloquear"]
        elif o.estado == Ocurrencia.BLOQUEADA:
            acciones.append("retomar")
    if o.tipo_marca == "RECIBIDA" and o.estado in (Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA) and _es_revisor(usuario, o):
        acciones.append("recibida")
    if o.tipo_marca == "HECHA" and o.estado == Ocurrencia.HECHA and o.hecha_por_id != usuario.pk and _es_revisor(usuario, o):
        acciones += ["revisar", "devolver"]
    return acciones


@transaction.atomic
def comentar(o: Ocurrencia, usuario, texto: str, archivo=None):
    """Un comentario, con un documento o evidencia adjunto si se quiere. Lo ven quien ejecuta la tarea y a quien se reporta (la revisión)."""
    rol = _exigir_rol(usuario)
    if rol not in permisos.QUE_MARCAN:
        raise PermisoDenegado("Tu perfil no puede comentar tareas.")
    if not (texto or "").strip() and archivo is None:
        raise ErrorDeNegocio("Escribe un comentario o adjunta un documento.")
    _exigir_periodo_abierto(o)
    if archivo is not None:
        evidencias.validar(archivo)  # se rechaza antes de registrar nada
        archivo.seek(0)
    despues = None
    adjunto = None
    if archivo is not None:
        adjunto = evidencias.guardar(o, usuario, archivo)
        despues = {"archivo": adjunto.nombre_original, "tamano": adjunto.tamano, "sha256": adjunto.sha256}
    evento = auditoria.registrar("ocurrencia.comentario", usuario=usuario, entidad="Ocurrencia", entidad_id=o.pk, despues=despues, motivo=(texto or "").strip())
    if adjunto is not None:
        adjunto.evento = evento
        adjunto.save(update_fields=["evento"])
    return evento


TEXTOS_DEL_HISTORIAL = {
    "ocurrencia.hecha": "Marcó hecha", "ocurrencia.hecha_por_excepcion": "Marcó hecha por excepción", "ocurrencia.recibida": "Marcó recibido",
    "ocurrencia.revisada": "Revisó", "ocurrencia.devuelta": "Devolvió", "ocurrencia.bloqueada": "Marcó bloqueada", "ocurrencia.retomada": "Retomó la tarea",
    "ocurrencia.comentario": "Comentó", "ocurrencia.reasignada": "Cambió quién la hace", "ocurrencia.horas_reales": "Anotó horas reales", "no_aplica.solicitada": "Pidió «no aplica»", "no_aplica.aprobada": "Aprobó «no aplica»", "no_aplica.rechazada": "Rechazó «no aplica»",
}


@dataclass
class EntradaDeHistorial:
    momento: object
    quien: str
    texto: str
    comentario: str
    adjuntos: list = field(default_factory=list)


def historial_de(o: Ocurrencia) -> list[EntradaDeHistorial]:
    eventos = EventoAuditoria.objects.filter(entidad="Ocurrencia", entidad_id=str(o.pk), accion__in=TEXTOS_DEL_HISTORIAL).select_related("usuario").order_by("id")
    adjuntos: dict[int, list] = {}
    for ev in o.evidencias.all():
        adjuntos.setdefault(ev.evento_id, []).append(ev)
    resultado = []
    for e in eventos:
        c = permisos.colaborador_de(e.usuario) if e.usuario_id else None
        resultado.append(EntradaDeHistorial(e.momento, c.nombre if c else e.usuario_texto, TEXTOS_DEL_HISTORIAL[e.accion], e.motivo, adjuntos.get(e.pk, [])))
    return resultado
