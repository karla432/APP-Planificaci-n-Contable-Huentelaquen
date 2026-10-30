"""Check List por cargo y responsable: quién es responsable de qué y cómo va, mes a mes."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Cargo, Ocurrencia
from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)
SCL = ZoneInfo("America/Santiago")


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa Gestión y Control"), cargo("Contadora Senior"), cargo("Gerente AyF")
    bodega = cargo("Bodega", externo=True)
    p = persona("Contadora", cont)
    persona("Jefa", jefa)
    u = usuario_con_rol("lectura", "LECTURA")
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=3)
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=4)
    tarea("TAR-0003", cont, "SEMANAL", revisa=jefa, proceso_nombre="Pagos", dia_semana=1)
    tarea("TAR-0004", bodega, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=2)
    periodos.abrir_mes(2026, 12, usuario=None)
    o = Ocurrencia.objects.get(tarea__codigo="TAR-0002")
    hora = datetime(2026, 12, 4, 10, 0, tzinfo=SCL)
    Ocurrencia.objects.filter(pk=o.pk).update(estado="hecha", primera_hecha_en=hora, hecha_en=hora)
    return {"u": u, "cont": cont, "bodega": bodega}


def ver(usuario, **params):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse("checklist_cargos"), params)
    assert r.status_code == 200
    return r.content.decode()


def test_lista_cada_cargo_con_su_responsable_y_sus_numeros(mundo):
    html = ver(mundo["u"])
    assert "Por cargo y responsable" in html or "Check List por cargo y responsable" in html
    assert "Contadora Senior" in html and "Contadora" in html  # cargo y responsable
    assert "Hechas" in html and "Atrasadas" in html


def test_los_cargos_externos_se_marcan_y_dicen_quien_registra(mundo):
    html = ver(mundo["u"])
    assert "Bodega" in html and "Externo" in html and "Recibido" in html


def test_el_detalle_de_un_cargo_lista_proceso_tarea_periodicidad_y_estado(mundo):
    html = ver(mundo["u"], cargo=mundo["cont"].pk)
    for texto in ("Compras", "Pagos", "Tarea TAR-0001", "Subtarea TAR-0001", "Día hábil 3 del cierre", "Cada martes", "Hecha", "Atrasada"):
        assert texto in html, texto
    assert "Subtarea TAR-0004" not in html  # es de Bodega


def test_el_mes_se_puede_cambiar_y_uno_sin_abrir_lo_dice(mundo):
    assert "no se ha abierto" in ver(mundo["u"], mes="2027-03").lower()


def test_sin_perfil_no_entra(mundo):
    c = Client()
    c.force_login(usuario_con_rol("fantasma", None))
    assert c.get(reverse("checklist_cargos")).status_code == 403
