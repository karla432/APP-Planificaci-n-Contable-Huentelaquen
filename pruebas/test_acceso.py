"""Ingreso: contraseña, bloqueo por intentos fallidos y registro en la bitácora (AM-05, AM-06)."""
import pytest
from django.urls import reverse

from nucleo.models import EventoAuditoria
from pruebas.ayudas import usuario_con_rol

pytestmark = pytest.mark.django_db
CLAVE = "x" * 12


def ingresar(client, usuario="karla", clave=CLAVE):
    return client.post(reverse("login"), {"username": usuario, "password": clave})


def test_sin_ingresar_se_redirige_al_formulario(client):
    r = client.get("/")
    assert r.status_code == 302 and r["Location"].startswith(reverse("login"))


def test_ingreso_correcto_lleva_al_inicio_y_queda_en_la_bitacora(client):
    usuario_con_rol("karla", "GERENTE")
    r = ingresar(client)
    assert r.status_code == 302 and r["Location"] == "/"
    assert EventoAuditoria.objects.filter(accion="sesion.iniciada", usuario__username="karla").exists()


def test_clave_incorrecta_no_entra_y_no_revela_si_el_usuario_existe(client):
    usuario_con_rol("karla", "GERENTE")
    r1 = ingresar(client, "karla", "equivocada1")
    r2 = ingresar(client, "no_existe", "equivocada1")
    assert r1.status_code == r2.status_code == 200
    assert r1.context["form"].errors.as_text() == r2.context["form"].errors.as_text()


def test_cinco_fallos_bloquean_y_ni_la_clave_correcta_entra(client):
    usuario_con_rol("karla", "GERENTE")
    for _ in range(5):
        ingresar(client, "karla", "equivocada1")
    r = ingresar(client, "karla", CLAVE)
    assert r.status_code == 200 and "bloqueada" in r.content.decode()
    assert "_auth_user_id" not in client.session
    assert EventoAuditoria.objects.filter(accion="sesion.cuenta_bloqueada").exists()


def test_un_ingreso_correcto_borra_los_fallos(client):
    usuario_con_rol("karla", "GERENTE")
    for _ in range(4):
        ingresar(client, "karla", "equivocada1")
    assert ingresar(client).status_code == 302
    client.post(reverse("logout"))
    for _ in range(4):
        ingresar(client, "karla", "equivocada1")
    assert ingresar(client).status_code == 302  # no se acumularon los 4 anteriores


def test_salir_cierra_la_sesion_y_queda_en_la_bitacora(client):
    usuario_con_rol("karla", "GERENTE")
    ingresar(client)
    r = client.post(reverse("logout"))
    assert r.status_code == 302 and "_auth_user_id" not in client.session
    assert EventoAuditoria.objects.filter(accion="sesion.cerrada").exists()
