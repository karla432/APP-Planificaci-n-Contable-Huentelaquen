"""Segundo factor (TOTP): obligatorio para el Gerente AyF y el administrador; falla cerrada; un código no se usa dos veces; bloqueo tras 5 errores."""
import time

import pyotp
import pytest
from django.test import Client
from django.urls import reverse

from nucleo import permisos
from nucleo.models import EventoAuditoria, SegundoFactor
from nucleo.servicios import segundo_factor
from nucleo.servicios.errores import ErrorDeNegocio
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def exige_2fa(settings):
    settings.EXIGE_2FA = True


@pytest.fixture
def ger():
    return usuario_con_rol("ger", "GERENTE", persona("Gerente", cargo("Gerente AyF")))


def entra(usuario):
    c = Client()
    c.force_login(usuario)
    return c


def codigo(sf, desplazamiento=0):
    return pyotp.TOTP(sf.secreto).at((int(time.time()) // 30 + desplazamiento) * 30)


def test_el_gerente_no_ve_nada_hasta_dar_su_segundo_factor(ger):
    c = entra(ger)
    for ruta in ("hoy", "mant_tareas", "informe_panel", "inicio"):
        r = c.get(reverse(ruta))
        assert r.status_code == 302 and r["Location"].startswith(reverse("segundo_factor")), ruta
    assert c.post(reverse("mant_tareas_cargar"), {"accion": "cancelar"}).status_code == 302  # tampoco se puede actuar a ciegas
    assert c.get(reverse("segundo_factor")).status_code == 200  # solo la pantalla del código
    assert c.get(reverse("logout")).status_code in (200, 302, 405)


def test_la_primera_vez_muestra_la_clave_y_el_codigo_la_confirma(ger):
    c = entra(ger)
    html = c.get(reverse("segundo_factor")).content.decode()
    sf = SegundoFactor.objects.get(usuario=ger)
    assert sf.visible_en_pantalla and not sf.confirmado and segundo_factor.clave_legible(sf) in html and "Menú principal" not in html
    r = c.post(reverse("segundo_factor"), {"codigo": codigo(sf), "siguiente": reverse("mant_tareas")})
    assert r.status_code == 302 and r["Location"] == reverse("mant_tareas")
    sf.refresh_from_db()
    assert sf.confirmado and not sf.visible_en_pantalla
    assert c.get(reverse("hoy")).status_code == 200 and EventoAuditoria.objects.filter(accion="2fa.activado").exists()


def test_despues_de_confirmar_la_clave_no_se_vuelve_a_mostrar(ger):
    sf = segundo_factor.crear(ger, visible_en_pantalla=True)
    c = entra(ger)
    c.post(reverse("segundo_factor"), {"codigo": codigo(sf)})
    otra = entra(ger)
    html = otra.get(reverse("segundo_factor")).content.decode()
    assert segundo_factor.clave_legible(sf) not in html and "Primera vez" not in html


def test_un_codigo_errado_no_deja_pasar_y_queda_en_la_bitacora(ger):
    c = entra(ger)
    c.get(reverse("segundo_factor"))
    r = c.post(reverse("segundo_factor"), {"codigo": "000000"}, follow=True)
    assert "no es válido" in r.content.decode() and c.get(reverse("hoy")).status_code == 302
    assert EventoAuditoria.objects.filter(accion="2fa.fallido").exists()


def test_un_codigo_no_se_puede_usar_dos_veces(ger):
    sf = segundo_factor.crear(ger)
    c = codigo(sf)
    assert segundo_factor.verificar(ger, c) is True
    assert segundo_factor.verificar(ger, c) is False  # el mismo código ya no sirve
    assert segundo_factor.verificar(ger, codigo(sf, +1)) is True  # el siguiente sí


def test_acepta_el_codigo_anterior_y_el_siguiente_pero_no_uno_lejano(ger):
    sf = segundo_factor.crear(ger)
    assert segundo_factor.verificar(ger, codigo(sf, -1)) is True
    assert segundo_factor.verificar(ger, codigo(sf, +3)) is False


def test_cinco_codigos_errados_bloquean_quince_minutos_incluso_con_el_codigo_correcto(ger):
    sf = segundo_factor.crear(ger)
    for _ in range(5):
        assert segundo_factor.verificar(ger, "111111") is False
    with pytest.raises(ErrorDeNegocio, match="Demasiados códigos errados"):
        segundo_factor.verificar(ger, codigo(sf))
    segundo_factor.reiniciar(ger)
    assert not SegundoFactor.objects.filter(usuario=ger).exists()


def test_quien_no_lo_necesita_entra_normal(settings):
    colaborador = usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior")))
    assert not segundo_factor.exige(colaborador)
    assert entra(colaborador).get(reverse("hoy")).status_code == 200
    assert entra(colaborador).get(reverse("segundo_factor")).status_code == 302  # no le corresponde


def test_el_administrador_tambien_lo_necesita():
    admin = usuario_con_rol("admin", "ADMIN_SISTEMA")
    assert segundo_factor.exige(admin) and permisos.rol_de(admin) == "ADMIN_SISTEMA"
    assert entra(admin).get(reverse("mant_usuarios"))["Location"].startswith(reverse("segundo_factor"))


def test_en_desarrollo_sin_la_variable_no_se_exige(settings, ger):
    settings.EXIGE_2FA = False
    assert entra(ger).get(reverse("hoy")).status_code == 200


def test_el_siguiente_no_puede_llevar_a_otro_sitio(ger):
    sf = segundo_factor.crear(ger)
    r = entra(ger).post(reverse("segundo_factor"), {"codigo": codigo(sf), "siguiente": "https://malo.example/"})
    assert r.status_code == 302 and r["Location"] == reverse("hoy")


def test_en_produccion_el_segundo_factor_esta_siempre_encendido_aunque_la_variable_diga_otra_cosa():
    import os
    import subprocess
    import sys
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    entorno = {**os.environ, "PLANIFICACION_ENTORNO": "produccion", "DJANGO_SECRET_KEY": "x" * 50, "DJANGO_ALLOWED_HOSTS": "app.example", "PLANIFICACION_2FA": "0"}
    r = subprocess.run([sys.executable, "-c", "import config.settings as s; print(s.PRODUCCION, s.EXIGE_2FA, s.ACCESO_RAPIDO)"], cwd=raiz, env=entorno, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "True True False", r.stderr


def test_cada_persona_puede_cambiar_su_clave_con_las_reglas_de_12_caracteres(settings):
    settings.EXIGE_2FA = False
    u = usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior")))
    u.set_password("clave-actual-123")
    u.save()
    c = Client()
    c.force_login(u)
    assert "Cambiar mi clave" in c.get(reverse("hoy")).content.decode()
    corta = c.post(reverse("cambiar_clave"), {"old_password": "clave-actual-123", "new_password1": "corta", "new_password2": "corta"})
    assert corta.status_code == 200 and "al menos 12" in corta.content.decode()
    ok = c.post(reverse("cambiar_clave"), {"old_password": "clave-actual-123", "new_password1": "clave-nueva-larga-9", "new_password2": "clave-nueva-larga-9"}, follow=True)
    assert ok.status_code == 200 and "Tu clave quedó cambiada" in ok.content.decode()
    u.refresh_from_db()
    assert u.check_password("clave-nueva-larga-9") and EventoAuditoria.objects.filter(accion="cuenta.clave_cambiada").exists()
