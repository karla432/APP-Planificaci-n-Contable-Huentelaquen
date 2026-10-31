"""Cierre mensual → Abrir mes: feriados confirmados, vista previa con avisos y confirmación. Solo Gerente y administrador."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Anio, EventoAuditoria, Feriado, Ocurrencia, Periodo
from pruebas.ayudas import cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 11, 20)


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    ger, cont, vacio = cargo("Gerente AyF"), cargo("Contador Senior"), cargo("Cargo vacío")
    persona("Gerente", ger)
    pc = persona("Contadora", cont)
    u = {"ger": usuario_con_rol("ger", "GERENTE", persona("Gerente 2", ger)), "admin": usuario_con_rol("admin", "ADMIN_SISTEMA"),
         "jefa": usuario_con_rol("jefa", "JEFATURA"), "cont": usuario_con_rol("cont", "COLABORADOR", pc)}
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    tarea("TAR-0002", cont, "DIARIA_HABIL")
    tarea("TAR-0003", vacio, "CIERRE_DIA_HABIL", n=1)  # sin persona responsable: aviso
    t = tarea("TAR-0004", cont, "SEMANAL")  # le falta el día: para revisión
    t.requiere_revision, t.motivo_revision = True, "Periodicidad semanal sin día de la semana."
    t.save()
    return u


def cli(usuario):
    c = Client()
    c.force_login(usuario)
    return c


URL = "abrir_mes"


@pytest.mark.parametrize("quien,esperado", [("ger", 200), ("admin", 200), ("jefa", 403), ("cont", 403)])
def test_solo_gerente_y_administrador_abren_el_mes(mundo, quien, esperado):
    assert cli(mundo[quien]).get(reverse(URL)).status_code == esperado
    assert cli(mundo[quien]).post(reverse(URL), {"accion": "abrir_mes"}).status_code in (esperado, 302 if esperado == 200 else esperado)


def test_el_menu_muestra_abrir_mes_solo_a_quien_corresponde(mundo):
    assert "Abrir mes" in cli(mundo["ger"]).get(reverse("hoy")).content.decode()
    assert "Abrir mes" not in cli(mundo["cont"]).get(reverse("hoy")).content.decode()


def test_el_flujo_completo_feriados_anio_y_mes(mundo):
    c = cli(mundo["ger"])
    html = c.get(reverse(URL), {"mes": "2026-12"}).content.decode()
    assert "Cargar los feriados de 2026" in html and "Abrir diciembre 2026" not in html
    # 1) cargar la propuesta de la librería (queda sin confirmar)
    assert c.post(reverse(URL), {"accion": "cargar_feriados", "mes": "2026-12"}).status_code == 302
    assert Feriado.objects.filter(fecha=date(2026, 12, 8)).exists() and not Feriado.objects.filter(confirmado=True).exists()
    assert "Sin confirmar" in c.get(reverse(URL), {"mes": "2026-12"}).content.decode()
    # no se abre el año con feriados sin confirmar
    r = c.post(reverse(URL), {"accion": "abrir_anio", "mes": "2026-12"}, follow=True)
    assert "sin confirmar" in r.content.decode() and Anio.objects.filter(estado="abierto").count() == 0
    # 2) confirmar y abrir el año
    c.post(reverse(URL), {"accion": "confirmar_feriados", "mes": "2026-12"})
    c.post(reverse(URL), {"accion": "abrir_anio", "mes": "2026-12"})
    assert Anio.objects.get(anio=2026).estado == "abierto"
    assert set(EventoAuditoria.objects.values_list("accion", flat=True)) >= {"feriados.confirmados", "anio.abierto"}


@pytest.fixture
def anio_listo(mundo):
    c = cli(mundo["ger"])
    for accion in ("cargar_feriados", "confirmar_feriados", "abrir_anio"):
        c.post(reverse(URL), {"accion": accion, "mes": "2026-12"})
    return c


def test_la_vista_previa_cuenta_lo_que_se_generara_y_avisa_lo_que_no(anio_listo):
    html = anio_listo.get(reverse(URL), {"mes": "2026-12"}).content.decode()
    assert "Vista previa" in html and "Abrir diciembre 2026" in html
    assert "Sin persona responsable" in html and "TAR-0003" in html  # no se genera hasta corregirlo
    assert "Requiere revisión" in html and "TAR-0004" in html
    assert "Día 3" in html and "Todos los días hábiles" in html  # resumen por tipo de regla y por día del cierre


def test_abrir_el_mes_genera_y_repetirlo_no_duplica(anio_listo):
    anio_listo.post(reverse(URL), {"accion": "abrir_mes", "mes": "2026-12", "inicio_medicion": "2026-12-01"})
    periodo = Periodo.objects.get(anio=2026, mes=12)
    assert periodo.inicio_medicion == date(2026, 12, 1) and Ocurrencia.objects.filter(periodo=periodo).exists()
    cuenta = Ocurrencia.objects.count()
    r = anio_listo.post(reverse(URL), {"accion": "abrir_mes", "mes": "2026-12"}, follow=True)
    assert Ocurrencia.objects.count() == cuenta and "ya existían" in r.content.decode().lower()
    assert EventoAuditoria.objects.filter(accion="periodo.abierto").count() == 2


def test_con_el_anio_cerrado_o_sin_abrir_no_se_puede_abrir_el_mes(mundo):
    r = cli(mundo["ger"]).post(reverse(URL), {"accion": "abrir_mes", "mes": "2026-12"}, follow=True)
    assert "no está abierto" in r.content.decode() and not Periodo.objects.exists()


def test_un_mes_ya_abierto_lo_dice(anio_listo):
    anio_listo.post(reverse(URL), {"accion": "abrir_mes", "mes": "2026-12"})
    assert "Este mes ya está abierto" in anio_listo.get(reverse(URL), {"mes": "2026-12"}).content.decode()


def test_agregar_un_feriado_decretado_queda_sin_confirmar(anio_listo):
    r = anio_listo.post(reverse(URL), {"accion": "agregar_feriado", "mes": "2026-12", "fecha": "2026-12-31", "nombre": "Feriado decretado", "tipo": "decretado"}, follow=True)
    f = Feriado.objects.get(fecha=date(2026, 12, 31))
    assert not f.confirmado and f.origen == "manual" and "sin confirmar" in r.content.decode().lower()
    # una fecha de otro año o sin nombre se rechaza con un mensaje claro
    r = anio_listo.post(reverse(URL), {"accion": "agregar_feriado", "mes": "2026-12", "fecha": "2027-01-01", "nombre": "x", "tipo": "legal"}, follow=True)
    assert "fecha de 2026" in r.content.decode() and not Feriado.objects.filter(fecha=date(2027, 1, 1)).exists()


def test_el_inicio_de_medicion_debe_estar_dentro_del_mes(anio_listo):
    r = anio_listo.post(reverse(URL), {"accion": "abrir_mes", "mes": "2026-12", "inicio_medicion": "2026-11-30"}, follow=True)
    assert "dentro del mes" in r.content.decode() and not Periodo.objects.exists()


def test_un_mes_o_una_accion_invalida_no_rompe_la_pantalla(mundo):
    c = cli(mundo["ger"])
    assert c.get(reverse(URL), {"mes": "basura"}).status_code == 200
    assert c.get(reverse(URL), {"mes": "2026-13"}).status_code == 200
    assert "Acción desconocida" in c.post(reverse(URL), {"accion": "x", "mes": "2026-12"}, follow=True).content.decode()
