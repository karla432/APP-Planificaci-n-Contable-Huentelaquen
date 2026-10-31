"""Mantenedor de procesos, tareas y usuarios. Los permisos y las reglas se validan aquí, en el servidor; cada cambio queda en la bitácora.

Un cambio en una tarea rige desde el período siguiente que se abra: las ocurrencias ya generadas guardan su propia copia y no se tocan.
"""
import re
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction

from nucleo import permisos
from nucleo.models import Asignacion, Cargo, Colaborador, Proceso, Tarea
from nucleo.servicios import auditoria, reloj
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from nucleo.servicios.importador import CARGO_JEFA, _clave, normalizar
from nucleo.servicios.recurrencia import AJUSTES, TIPOS


def _exigir_edita_tareas(usuario):
    if permisos.rol_de(usuario) not in (permisos.GERENTE, permisos.JEFATURA):
        raise PermisoDenegado("Solo el Gerente y la Jefatura pueden modificar procesos y tareas.")


@dataclass
class DatosTarea:
    proceso_id: int
    tarea_principal: str
    subtarea: str
    cargo_ejecuta_id: int
    tipo: str
    dia_semana: int | None = None
    franja: str = ""
    n: int | None = None
    dia: int | None = None
    meses: tuple = ()
    ajuste: str = "siguiente"
    referencia: str = ""
    activa: bool = True
    cargo_revisa_id: int | None = None  # quien revisa (o recibe, si la tarea es de un externo); vacío = sin revisor
    minutos: int | None = None  # minutos estimados por ejecución


def _validar(d: DatosTarea) -> str:
    """Lanza ErrorDeNegocio si hay un dato inválido. Devuelve un motivo de revisión si la regla queda incompleta, o ''."""
    if not normalizar(d.tarea_principal):
        raise ErrorDeNegocio("Falta la tarea principal.")
    if not normalizar(d.subtarea):
        raise ErrorDeNegocio("Falta la subtarea.")
    if d.tipo not in TIPOS:
        raise ErrorDeNegocio(f"La periodicidad «{d.tipo}» no existe.")
    if d.ajuste not in AJUSTES:
        raise ErrorDeNegocio("El ajuste para días inhábiles debe ser «siguiente» o «anterior».")
    if d.tipo == "SEMANAL" and d.dia_semana not in range(5):
        raise ErrorDeNegocio("Falta el día de la semana (lunes a viernes).")
    if d.tipo == "CIERRE_DIA_HABIL" and d.n not in range(1, 11):
        raise ErrorDeNegocio("El día hábil del cierre debe estar entre 1 y 10.")
    if d.tipo == "CIERRE_HITO" and d.n not in (7, 10):
        raise ErrorDeNegocio("El hito del cierre debe ser 7 o 10.")
    if d.tipo == "DIA_FIJO" and d.dia not in range(1, 32):
        raise ErrorDeNegocio("El día del mes debe estar entre 1 y 31.")
    if d.tipo == "MESES":
        if not d.meses or any(m not in range(1, 13) for m in d.meses):
            raise ErrorDeNegocio("Elige al menos un mes.")
        if d.dia is not None and d.dia not in range(1, 32):
            raise ErrorDeNegocio("El día del mes debe estar entre 1 y 31.")
        if d.dia is None:
            return "Falta el día del mes en que vence."
    return ""


def ejecuciones_por_mes(tipo: str, meses=()):
    """Cuántas veces se ejecuta la tarea en un mes típico (21 días hábiles, 4,33 semanas). Las de evento no tienen un valor fijo."""
    if tipo == "DIARIA_HABIL":
        return 21
    if tipo == "SEMANAL":
        return 4.33
    if tipo in ("CIERRE_DIA_HABIL", "CIERRE_HITO", "DIA_FIJO", "FIN_DE_MES"):
        return 1
    return round(len(meses) / 12, 3) if tipo == "MESES" and meses else None


def _instantanea(t: Tarea) -> dict:
    return {
        "proceso": t.proceso.nombre, "tarea_principal": t.tarea_principal, "subtarea": t.subtarea, "cargo_ejecuta": t.cargo_ejecuta.nombre,
        "cargo_revisa": t.cargo_revisa.nombre if t.cargo_revisa else None, "regla_tipo": t.regla_tipo, "regla_dia_semana": t.regla_dia_semana,
        "regla_n": t.regla_n, "regla_dia": t.regla_dia, "regla_meses": t.regla_meses, "regla_ajuste": t.regla_ajuste, "regla_franja": t.regla_franja,
        "referencia_normativa": t.referencia_normativa, "activa": t.activa, "requiere_revision": t.requiere_revision,
        "minutos_estimados": t.minutos_estimados,
    }


def _aplicar(t: Tarea, d: DatosTarea, motivo: str):
    try:
        proceso, ejecuta = Proceso.objects.get(pk=d.proceso_id), Cargo.objects.get(pk=d.cargo_ejecuta_id)
    except (Proceso.DoesNotExist, Cargo.DoesNotExist):
        raise ErrorDeNegocio("El proceso o el responsable elegido no existe.") from None
    t.proceso, t.tarea_principal, t.subtarea = proceso, normalizar(d.tarea_principal), normalizar(d.subtarea)
    t.cargo_ejecuta = ejecuta
    revisa = Cargo.objects.filter(pk=d.cargo_revisa_id).first() if d.cargo_revisa_id else None
    if revisa is None and ejecuta.es_externo:
        revisa = Cargo.objects.filter(nombre=CARGO_JEFA).first()  # quien registra «Recibido» (supuesto, igual que en el importador)
    t.cargo_revisa = revisa  # sin revisor se queda sin revisor: no se inventa
    t.minutos_estimados = d.minutos
    t.ejecuciones_mes = ejecuciones_por_mes(d.tipo, d.meses)
    t.regla_tipo, t.regla_dia_semana, t.regla_n, t.regla_dia = d.tipo, d.dia_semana, d.n, d.dia
    t.regla_meses = ",".join(str(m) for m in sorted(d.meses))
    t.regla_ajuste, t.regla_franja, t.regla_estado = d.ajuste, d.franja, "confirmado"
    t.referencia_normativa, t.activa = d.referencia.strip(), d.activa
    t.requiere_revision, t.motivo_revision = bool(motivo), motivo


def _exigir_no_repetida(d: DatosTarea, excepto: Tarea | None = None):
    proceso = Proceso.objects.filter(pk=d.proceso_id).first()
    if proceso is None:
        raise ErrorDeNegocio("El proceso elegido no existe.")
    clave = _clave(proceso.nombre, d.tarea_principal, d.subtarea)
    repetida = Tarea.objects.filter(clave_estable=clave)
    if excepto is not None:
        repetida = repetida.exclude(pk=excepto.pk)
    if repetida.exists():
        raise ErrorDeNegocio("Esa tarea ya existe en el proceso.")
    return clave


@transaction.atomic
def crear_tarea(usuario, d: DatosTarea) -> Tarea:
    _exigir_edita_tareas(usuario)
    motivo = _validar(d)
    clave = _exigir_no_repetida(d)
    ultimo = Tarea.objects.order_by("-codigo").values_list("codigo", flat=True).first()
    t = Tarea(codigo=f"TAR-{(int(ultimo.split('-')[1]) + 1) if ultimo else 1:04d}", clave_estable=clave)
    _aplicar(t, d, motivo)
    t.save()
    auditoria.registrar("tarea.creada", usuario=usuario, entidad="Tarea", entidad_id=t.pk, despues=_instantanea(t))
    return t


@transaction.atomic
def editar_tarea(usuario, t: Tarea, d: DatosTarea) -> Tarea:
    _exigir_edita_tareas(usuario)
    motivo = _validar(d)
    _exigir_no_repetida(d, excepto=t)
    antes = _instantanea(t)
    _aplicar(t, d, motivo)  # el código y la clave estable no cambian
    t.save()
    auditoria.registrar("tarea.editada", usuario=usuario, entidad="Tarea", entidad_id=t.pk, antes=antes, despues=_instantanea(t))
    return t


# ---- Procesos ----------------------------------------------------------------------------------------------


def _nombre_de_proceso(nombre: str, excepto: Proceso | None = None) -> str:
    nombre = normalizar(nombre)
    if not nombre:
        raise ErrorDeNegocio("Falta el nombre del proceso.")
    repetido = Proceso.objects.filter(nombre__iexact=nombre)
    if excepto is not None:
        repetido = repetido.exclude(pk=excepto.pk)
    if repetido.exists():
        raise ErrorDeNegocio("Ese proceso ya existe.")
    return nombre


@transaction.atomic
def crear_proceso(usuario, nombre: str) -> Proceso:
    _exigir_edita_tareas(usuario)
    p = Proceso.objects.create(nombre=_nombre_de_proceso(nombre))
    auditoria.registrar("proceso.creado", usuario=usuario, entidad="Proceso", entidad_id=p.pk, despues={"nombre": p.nombre})
    return p


@transaction.atomic
def renombrar_proceso(usuario, p: Proceso, nombre: str, activo: bool | None = None) -> Proceso:
    _exigir_edita_tareas(usuario)
    antes = {"nombre": p.nombre, "activo": p.activo}
    p.nombre = _nombre_de_proceso(nombre, excepto=p)
    if activo is not None:
        p.activo = activo
    p.save()
    auditoria.registrar("proceso.editado", usuario=usuario, entidad="Proceso", entidad_id=p.pk, antes=antes, despues={"nombre": p.nombre, "activo": p.activo})
    return p


# ---- Usuarios ----------------------------------------------------------------------------------------------
# La clave se asigna en la etapa de seguridad: por ahora el usuario queda sin clave (solo entra por el modo de prueba local).

ROLES_CON_CARGO = (permisos.GERENTE, permisos.JEFATURA, permisos.COLABORADOR)
USUARIO_VALIDO = re.compile(r"^[\w.@+-]+$")


def _exigir_gestiona_usuarios(actor) -> str:
    rol = permisos.rol_de(actor)
    if rol not in (permisos.GERENTE, permisos.ADMIN_SISTEMA):
        raise PermisoDenegado("Solo el Gerente y el administrador del sistema gestionan usuarios.")
    return rol


def _exigir_puede_con_administradores(rol_actor: str, rol_afectado: str | None):
    if rol_afectado == permisos.ADMIN_SISTEMA and rol_actor != permisos.ADMIN_SISTEMA:
        raise PermisoDenegado("Solo un administrador del sistema puede crear o modificar administradores.")


def _validar_perfil_y_cargo(nombre: str, rol: str, cargo_id) -> Cargo | None:
    if not normalizar(nombre):
        raise ErrorDeNegocio("Falta el nombre de la persona.")
    if rol not in permisos.ROLES:
        raise ErrorDeNegocio(f"El perfil «{rol}» no existe.")
    if rol not in ROLES_CON_CARGO:
        return None
    cargo = Cargo.objects.filter(pk=cargo_id, activo=True).first() if cargo_id else None
    if cargo is None:
        raise ErrorDeNegocio("Este perfil necesita un cargo.")
    return cargo


def _asignacion_vigente(colaborador, hoy):
    return Asignacion.objects.filter(colaborador=colaborador, desde__lte=hoy).exclude(hasta__lt=hoy).order_by("-desde").first()


def _poner_cargo(colaborador, cargo: Cargo | None, hoy):
    """Deja a la persona en `cargo` desde hoy, cerrando la asignación anterior sin borrarla (subrogancias y reemplazos)."""
    vigente = _asignacion_vigente(colaborador, hoy)
    if vigente is not None and cargo is not None and vigente.cargo_id == cargo.pk:
        return
    if vigente is not None:
        if vigente.desde >= hoy:
            if cargo is not None:
                vigente.cargo = cargo
                vigente.save()
                return
            vigente.hasta = vigente.desde - timedelta(days=1)
            vigente.save()
            return
        vigente.hasta = hoy - timedelta(days=1)
        vigente.save()
    if cargo is not None:
        Asignacion.objects.create(cargo=cargo, colaborador=colaborador, desde=hoy)


def _instantanea_usuario(u, hoy) -> dict:
    c = Colaborador.objects.filter(usuario=u).first()
    a = _asignacion_vigente(c, hoy) if c else None
    return {"usuario": u.get_username(), "nombre": c.nombre if c else u.first_name, "correo": u.email, "rol": permisos.rol_de(u),
            "cargo": a.cargo.nombre if a else None, "activo": u.is_active}


@transaction.atomic
def crear_usuario(actor, username: str, nombre: str, correo: str, rol: str, cargo_id=None):
    rol_actor = _exigir_gestiona_usuarios(actor)
    username = (username or "").strip()
    if not username or not USUARIO_VALIDO.match(username):
        raise ErrorDeNegocio("El nombre de usuario solo puede llevar letras, números y los signos . @ + - _ (sin espacios).")
    User = get_user_model()
    if User.objects.filter(username__iexact=username).exists():
        raise ErrorDeNegocio("Ese usuario ya existe.")
    cargo = _validar_perfil_y_cargo(nombre, rol, cargo_id)
    _exigir_puede_con_administradores(rol_actor, rol)
    u = User.objects.create_user(username, email=(correo or "").strip(), first_name=normalizar(nombre))  # sin clave todavía
    u.groups.add(Group.objects.get(name=rol))
    if cargo is not None:
        c = Colaborador.objects.create(usuario=u, nombre=normalizar(nombre), correo=u.email)
        _poner_cargo(c, cargo, reloj.hoy())
    auditoria.registrar("usuario.creado", usuario=actor, entidad="Usuario", entidad_id=u.pk, despues=_instantanea_usuario(u, reloj.hoy()))
    return u


@transaction.atomic
def editar_usuario(actor, u, nombre: str, correo: str, rol: str, cargo_id=None, activo: bool = True):
    rol_actor = _exigir_gestiona_usuarios(actor)
    hoy = reloj.hoy()
    antes = _instantanea_usuario(u, hoy)
    _exigir_puede_con_administradores(rol_actor, antes["rol"])
    cargo = _validar_perfil_y_cargo(nombre, rol, cargo_id)
    _exigir_puede_con_administradores(rol_actor, rol)
    if u.pk == actor.pk and (rol != antes["rol"] or activo is not True or (cargo.nombre if cargo else None) != antes["cargo"]):
        raise PermisoDenegado("No puedes cambiar tu propio perfil, tu cargo ni desactivarte.")
    u.first_name, u.email, u.is_active = normalizar(nombre), (correo or "").strip(), bool(activo)
    u.save()
    u.groups.remove(*Group.objects.filter(name__in=permisos.ROLES))
    u.groups.add(Group.objects.get(name=rol))
    c = Colaborador.objects.filter(usuario=u).first()
    if c is None and cargo is not None:
        c = Colaborador(usuario=u)
    if c is not None:
        c.nombre, c.correo, c.activo = normalizar(nombre), u.email, bool(activo)
        c.save()
        _poner_cargo(c, cargo, hoy)
    auditoria.registrar("usuario.editado", usuario=actor, entidad="Usuario", entidad_id=u.pk, antes=antes, despues=_instantanea_usuario(u, hoy))
    return u
