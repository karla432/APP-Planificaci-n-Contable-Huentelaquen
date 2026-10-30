"""Mantenedor de usuarios: perfil, cargo y estado. La clave se asigna en la etapa de seguridad (queda sin clave por ahora)."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from nucleo import permisos
from nucleo.models import Asignacion, Colaborador, EventoAuditoria
from nucleo.servicios import mantenedor
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    cont, anal, jefa, ger = cargo("Contadora Senior"), cargo("Analista Contable"), cargo("Jefa Gestión y Control"), cargo("Gerente AyF")
    p = persona("Gerente", ger)
    return {"ger_cargo": ger, "cont": cont, "anal": anal, "jefa_cargo": jefa,
            "ger": usuario_con_rol("ger", "GERENTE", p), "admin": usuario_con_rol("admin", "ADMIN_SISTEMA"),
            "jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", jefa)), "cont_u": usuario_con_rol("cont", "COLABORADOR", persona("Cont", cont)),
            "lectura": usuario_con_rol("lectura", "LECTURA")}


def crear(mundo, actor="ger", **kw):
    datos = dict(username="analista", nombre="Analista de ejemplo", correo="", rol="COLABORADOR", cargo_id=mundo["anal"].pk)
    datos.update(kw)
    return mantenedor.crear_usuario(mundo[actor], **datos)


# ---- Crear ------------------------------------------------------------------------------------------------


def test_crear_un_usuario_con_perfil_cargo_y_sin_clave_todavia(mundo):
    u = crear(mundo)
    assert permisos.rol_de(u) == "COLABORADOR" and not u.has_usable_password()
    c = Colaborador.objects.get(usuario=u)
    a = Asignacion.objects.get(colaborador=c)
    assert c.nombre == "Analista de ejemplo" and a.cargo == mundo["anal"] and a.desde == HOY and a.hasta is None
    assert EventoAuditoria.objects.filter(accion="usuario.creado", entidad_id=str(u.pk)).exists()


def test_el_administrador_tambien_crea_usuarios(mundo):
    assert crear(mundo, actor="admin", username="otra").pk


@pytest.mark.parametrize("quien", ["jefa", "cont_u", "lectura"])
def test_solo_gerente_y_administrador_gestionan_usuarios(mundo, quien):
    with pytest.raises(PermisoDenegado):
        crear(mundo, actor=quien)
    assert not get_user_model().objects.filter(username="analista").exists()


def test_el_gerente_no_crea_administradores_el_administrador_si(mundo):
    with pytest.raises(PermisoDenegado, match="administrador"):
        crear(mundo, rol="ADMIN_SISTEMA", cargo_id=None)
    u = crear(mundo, actor="admin", rol="ADMIN_SISTEMA", cargo_id=None)
    assert permisos.rol_de(u) == "ADMIN_SISTEMA"


def test_los_perfiles_que_ejecutan_tareas_exigen_cargo_y_los_demas_no_lo_llevan(mundo):
    for rol in ("COLABORADOR", "JEFATURA", "GERENTE"):
        with pytest.raises(ErrorDeNegocio, match="cargo"):
            crear(mundo, username=f"x_{rol}", rol=rol, cargo_id=None)
    u = crear(mundo, username="solo_lee", rol="LECTURA", cargo_id=None)
    assert not Colaborador.objects.filter(usuario=u).exists()


@pytest.mark.parametrize("cambios,mensaje", [(dict(username="ger"), "ya existe"), (dict(username="a b"), "usuario"), (dict(username=""), "usuario"), (dict(nombre=" "), "nombre"), (dict(rol="SUPER"), "perfil")])
def test_datos_invalidos_no_crean_nada(mundo, cambios, mensaje):
    antes = get_user_model().objects.count()
    with pytest.raises(ErrorDeNegocio, match=mensaje):
        crear(mundo, **cambios)
    assert get_user_model().objects.count() == antes


# ---- Editar ------------------------------------------------------------------------------------------------


def test_cambiar_de_cargo_cierra_la_asignacion_anterior_y_abre_otra(mundo):
    u = crear(mundo)
    c = Colaborador.objects.get(usuario=u)
    Asignacion.objects.filter(colaborador=c).update(desde=date(2026, 1, 1))
    mantenedor.editar_usuario(mundo["ger"], u, nombre=c.nombre, correo="", rol="COLABORADOR", cargo_id=mundo["cont"].pk, activo=True)
    anterior, nueva = Asignacion.objects.filter(colaborador=c).order_by("desde")
    assert anterior.cargo == mundo["anal"] and anterior.hasta == date(2026, 12, 3)
    assert nueva.cargo == mundo["cont"] and nueva.desde == HOY and nueva.hasta is None
    ev = EventoAuditoria.objects.filter(accion="usuario.editado").get()
    assert ev.antes["cargo"] == "Analista Contable" and ev.despues["cargo"] == "Contadora Senior"


def test_nadie_cambia_su_propio_perfil_ni_se_desactiva(mundo):
    with pytest.raises(PermisoDenegado, match="propio"):
        mantenedor.editar_usuario(mundo["ger"], mundo["ger"], nombre="Gerente", correo="", rol="LECTURA", cargo_id=None, activo=True)
    with pytest.raises(PermisoDenegado, match="propio"):
        mantenedor.editar_usuario(mundo["ger"], mundo["ger"], nombre="Gerente", correo="", rol="GERENTE", cargo_id=mundo["ger_cargo"].pk, activo=False)
    assert permisos.rol_de(mundo["ger"]) == "GERENTE" and mundo["ger"].is_active


def test_si_puede_corregir_su_propio_nombre_y_correo(mundo):
    mantenedor.editar_usuario(mundo["ger"], mundo["ger"], nombre="Karla M.", correo="k@ejemplo.cl", rol="GERENTE", cargo_id=mundo["ger_cargo"].pk, activo=True)
    mundo["ger"].refresh_from_db()
    assert mundo["ger"].email == "k@ejemplo.cl" and Colaborador.objects.get(usuario=mundo["ger"]).nombre == "Karla M."


def test_el_gerente_no_toca_a_un_administrador(mundo):
    with pytest.raises(PermisoDenegado, match="administrador"):
        mantenedor.editar_usuario(mundo["ger"], mundo["admin"], nombre="x", correo="", rol="LECTURA", cargo_id=None, activo=True)
    assert permisos.rol_de(mundo["admin"]) == "ADMIN_SISTEMA"


def test_cambiar_el_perfil_deja_un_solo_rol(mundo):
    u = crear(mundo)
    mantenedor.editar_usuario(mundo["ger"], u, nombre="Analista de ejemplo", correo="", rol="JEFATURA", cargo_id=mundo["jefa_cargo"].pk, activo=True)
    assert permisos.rol_de(u) == "JEFATURA" and u.groups.count() == 1


def test_desactivar_un_usuario_no_lo_borra(mundo):
    u = crear(mundo)
    mantenedor.editar_usuario(mundo["ger"], u, nombre="Analista de ejemplo", correo="", rol="COLABORADOR", cargo_id=mundo["anal"].pk, activo=False)
    u.refresh_from_db()
    assert not u.is_active and Colaborador.objects.get(usuario=u).activo is False
