"""Modo de prueba sin clave: solo para trabajar en un computador local; imposible en producción."""
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from config.entorno import acceso_rapido_permitido
from pruebas.ayudas import cargo, persona, usuario_con_rol


# ---- La decisión de activarlo -------------------------------------------------------------------


def test_apagado_por_defecto():
    assert acceso_rapido_permitido(None, produccion=False) is False
    assert acceso_rapido_permitido("0", produccion=True) is False


def test_se_enciende_solo_en_desarrollo_con_la_variable_en_1():
    assert acceso_rapido_permitido("1", produccion=False) is True


def test_en_produccion_pedirlo_impide_arrancar():
    with pytest.raises(ImproperlyConfigured, match="producción"):
        acceso_rapido_permitido("1", produccion=True)


# ---- La pantalla ----------------------------------------------------------------------------------


@pytest.fixture
def equipo(db):
    p = persona("Contadora de ejemplo", cargo("Contador Senior"))
    return usuario_con_rol("contadora", "COLABORADOR", p), usuario_con_rol("gerente", "GERENTE")


def test_con_el_modo_apagado_la_ruta_no_existe(client, settings, equipo):
    settings.ACCESO_RAPIDO = False
    assert client.get(reverse("acceso_rapido")).status_code == 404
    assert client.post(reverse("acceso_rapido"), {"usuario": "gerente"}).status_code == 404
    assert "_auth_user_id" not in client.session


def test_con_el_modo_encendido_lista_a_los_usuarios_y_entra_sin_clave(client, settings, equipo):
    settings.ACCESO_RAPIDO = True
    html = client.get(reverse("acceso_rapido")).content.decode()
    assert "contadora" in html and "gerente" in html and "sin clave" in html.lower()
    r = client.post(reverse("acceso_rapido"), {"usuario": "gerente"})
    assert r.status_code == 302 and client.session["_auth_user_id"] == str(equipo[1].pk)


def test_un_usuario_inexistente_no_entra(client, settings, equipo):
    settings.ACCESO_RAPIDO = True
    assert client.post(reverse("acceso_rapido"), {"usuario": "fantasma"}).status_code == 404
    assert "_auth_user_id" not in client.session


def test_el_ingreso_con_clave_sigue_funcionando_y_avisa_del_modo_de_prueba(client, settings, equipo):
    settings.ACCESO_RAPIDO = True
    html = client.get(reverse("login")).content.decode()
    assert "Entrar sin clave" in html and "MODO DE PRUEBA" in html


def test_con_el_modo_apagado_la_pantalla_de_ingreso_no_lo_menciona(client, settings, equipo):
    settings.ACCESO_RAPIDO = False
    html = client.get(reverse("login")).content.decode()
    assert "sin clave" not in html.lower() and "MODO DE PRUEBA" not in html


def test_despues_de_entrar_sin_clave_la_siguiente_pagina_reconoce_la_sesion(client, settings, equipo):
    """Regresión: el navegador real volvía al ingreso porque la sesión se guardaba con un respaldo de autenticación no registrado."""
    settings.ACCESO_RAPIDO = True
    r = client.post(reverse("acceso_rapido"), {"usuario": "gerente"}, follow=True)
    assert r.redirect_chain[-1][0] == reverse("hoy")
    assert r.status_code == 200 and "Salir" in r.content.decode()
    assert r.wsgi_request.user.is_authenticated
