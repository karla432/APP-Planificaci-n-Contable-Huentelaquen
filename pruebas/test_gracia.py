"""Gracia de arranque (Karla, 17-11-2026): durante 3 semanas desde el inicio nada cuenta como atrasado; se puede registrar igual."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia
from nucleo.servicios import agenda, ejecucion, gracia, kpi, periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
INICIO = date(2026, 12, 2)  # día desde el que corre la gracia; dura 21 días, hasta el 23-12-2026


@pytest.fixture
def mundo():
    anio_abierto()
    cont = cargo("Contador Senior")
    p = persona("Contadora", cont)
    u = usuario_con_rol("cont", "COLABORADOR", p)
    tarea("D-1", cont, "DIARIA_HABIL")
    return {"p": p, "u": u}


def abrir(mundo, con_gracia=True):
    if con_gracia:
        gracia.configurar(INICIO, 21)
    periodos.abrir_mes(2026, 12, usuario=None)
    return Ocurrencia.objects.get(fecha_limite=date(2026, 12, 1))


def test_sin_gracia_lo_anterior_esta_atrasado_como_siempre(mundo):
    o = abrir(mundo, con_gracia=False)
    assert o.vence_el == o.fecha_limite == date(2026, 12, 1)
    assert o in agenda.agenda_de(mundo["p"], date(2026, 12, 4))["atrasadas"]


def test_con_gracia_nada_es_atrasado_hasta_que_termina_pero_se_puede_registrar(mundo):
    o = abrir(mundo)
    assert o.fecha_limite == date(2026, 12, 1) and o.vence_el == date(2026, 12, 23)  # conserva su fecha del plan
    a = agenda.agenda_de(mundo["p"], date(2026, 12, 4))
    assert a["atrasadas"] == [] and a["gracia_hasta"] == date(2026, 12, 23)
    assert [x.fecha_limite for x in a["por_registrar"]] == [date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3)]
    assert [x.fecha_limite for x in a["hoy"]] == [date(2026, 12, 4)] and all(x.fecha_limite > date(2026, 12, 4) for x in a["proximas"])
    # también lo que vence DENTRO de la gracia (antes del 23) queda protegido; lo del 23 en adelante rige lo normal
    assert Ocurrencia.objects.get(fecha_limite=date(2026, 12, 22)).vence_el == date(2026, 12, 23)
    normal = Ocurrencia.objects.get(fecha_limite=date(2026, 12, 23))
    assert normal.vence_el == normal.fecha_limite


def _kpi(mundo, periodo, hoy):
    return next(k for k in kpi.por_colaborador(periodo, hoy) if k.colaborador.pk == mundo["p"].pk)


def test_el_cumplimiento_no_cuenta_lo_anterior_mientras_dura_la_gracia(mundo):
    o = abrir(mundo, con_gracia=False)
    assert _kpi(mundo, o.periodo, date(2026, 12, 4)).vencidas == 3  # sin gracia: el 01, el 02 y el 03 ya vencieron y están sin hacer
    gracia.configurar(INICIO, 21)
    k = _kpi(mundo, o.periodo, date(2026, 12, 4))
    assert k.vencidas == 0 and k.pendientes_vencidas == 0  # con gracia, nada cuenta todavía


def test_lo_registrado_en_la_gracia_cuenta_a_tiempo_y_lo_pendiente_se_atrasa_al_terminar(mundo, monkeypatch):
    o = abrir(mundo)
    monkeypatch.setattr("django.utils.timezone.now", lambda: datetime(2026, 12, 5, 10, 0, tzinfo=ZoneInfo("America/Santiago")))
    ejecucion.marcar_hecha(o, mundo["u"])  # el equipo registra el 05-12 lo que hizo el 01-12
    k = _kpi(mundo, o.periodo, date(2026, 12, 24))
    assert k.a_tiempo == 1 and k.vencidas == 16 and k.pendientes_vencidas == 15  # la registrada cuenta a tiempo; las otras, vencidas sin hacer
    assert agenda.agenda_de(mundo["p"], date(2026, 12, 24))["por_registrar"] == []


def test_pasada_la_gracia_lo_anterior_que_sigue_pendiente_se_ve_atrasado(mundo):
    o = abrir(mundo)
    assert o not in agenda.agenda_de(mundo["p"], date(2026, 12, 23))["atrasadas"]  # el último día de gracia todavía no
    a = agenda.agenda_de(mundo["p"], date(2026, 12, 24))
    assert o in a["atrasadas"] and a["por_registrar"] == []


def test_configurar_la_gracia_tambien_alcanza_a_lo_que_ya_estaba_generado(mundo):
    o = abrir(mundo, con_gracia=False)
    assert o.vence_el == date(2026, 12, 1)
    assert gracia.configurar(INICIO, 21) >= 1
    o.refresh_from_db()
    assert o.vence_el == date(2026, 12, 23) and o.fecha_limite == date(2026, 12, 1)
    gracia.configurar(None)  # apagarla devuelve todo a su fecha normal
    o.refresh_from_db()
    assert o.vence_el == o.fecha_limite and gracia.inicio_de_operacion() is None


def test_mi_dia_explica_la_gracia_y_deja_registrar(mundo, monkeypatch):
    abrir(mundo)
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))
    c = Client()
    c.force_login(mundo["u"])
    html = c.get(reverse("hoy")).content.decode()
    assert "Por registrar" in html and "No cuentan como atrasadas hasta el 23-12-2026" in html
    assert "Atrasada" not in html.split("Por registrar")[1].split("</section>")[0]


def test_el_comando_fija_y_apaga_la_gracia(mundo):
    abrir(mundo, con_gracia=False)
    call_command("configurar_gracia", "--inicio", "2026-12-02", "--dias", "21")
    assert gracia.inicio_de_operacion() == INICIO and gracia.gracia_hasta() == date(2026, 12, 23)
    call_command("configurar_gracia", "--quitar")
    assert gracia.inicio_de_operacion() is None
