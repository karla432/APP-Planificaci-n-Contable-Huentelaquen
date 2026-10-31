"""El calendario empieza en el primer mes abierto (noviembre de 2026): Mi semana y Mi mes no retroceden más atrás."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 11, 9))


@pytest.fixture
def cliente():
    cont = cargo("Contador Senior")
    u = usuario_con_rol("cont", "COLABORADOR", persona("Cont", cont))
    anio_abierto(feriados=())
    tarea("T-1", cont, "CIERRE_DIA_HABIL", n=5)
    periodos.abrir_mes(2026, 11, usuario=None, inicio_medicion=date(2026, 11, 5))
    c = Client()
    c.force_login(u)
    return c


def anterior_activo(html: str, texto: str) -> bool:
    return f'>‹ {texto}</a>' in html


def test_la_primera_semana_no_tiene_semana_anterior_pero_la_segunda_si(cliente):
    primera = cliente.get(reverse("semana"), {"fecha": "2026-11-04"}).content.decode()
    assert "Semana del 02-11-2026 al 06-11-2026" in primera and not anterior_activo(primera, "Semana anterior") and "‹ Semana anterior" in primera
    segunda = cliente.get(reverse("semana"), {"fecha": "2026-11-09"}).content.decode()
    assert anterior_activo(segunda, "Semana anterior")
    assert 'Semana siguiente ›' in segunda


def test_el_primer_mes_no_tiene_mes_anterior(cliente):
    nov = cliente.get(reverse("mes"), {"mes": "2026-11"}).content.decode()
    assert not anterior_activo(nov, "Mes anterior") and "Mes siguiente ›" in nov
    dic = cliente.get(reverse("mes"), {"mes": "2026-12"}).content.decode()
    assert anterior_activo(dic, "Mes anterior")


def test_sin_ningun_mes_abierto_la_navegacion_no_se_limita():
    cont = cargo("Contador Senior")
    c = Client()
    c.force_login(usuario_con_rol("cont", "COLABORADOR", persona("Cont", cont)))
    assert anterior_activo(c.get(reverse("mes")).content.decode(), "Mes anterior")
