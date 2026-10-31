"""Roles (grupos), reloj de desarrollo y datos de ejemplo (solo desarrollo)."""
from datetime import date

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError

from nucleo import permisos
from nucleo.models import Colaborador, Ocurrencia, Periodo, Tarea
from nucleo.servicios import reloj

pytestmark = pytest.mark.django_db


def test_los_cinco_roles_existen_tras_migrar():
    assert set(Group.objects.values_list("name", flat=True)) >= set(permisos.ROLES)


def test_el_reloj_de_desarrollo_se_puede_fijar_con_una_variable(monkeypatch):
    monkeypatch.setenv("PLANIFICACION_HOY", "2026-12-04")
    assert reloj.hoy() == date(2026, 12, 4)


def test_el_reloj_ignora_la_variable_en_produccion(monkeypatch, settings):
    settings.PRODUCCION = True
    monkeypatch.setenv("PLANIFICACION_HOY", "2026-12-04")
    assert reloj.hoy() != date(2026, 12, 4)


def test_datos_de_ejemplo_arma_un_mes_de_diciembre_navegable():
    call_command("datos_de_ejemplo", "--password", "ejemplo-ejemplo-1")
    assert Tarea.objects.count() == 195  # 195 filas del Excel, una repetida, más la revisión del día 9
    assert Colaborador.objects.filter(usuario__isnull=False).count() == 4
    assert Periodo.objects.filter(anio=2026, mes=12, estado="abierto").exists()
    assert Ocurrencia.objects.filter(periodo__mes=12).exists()
    roles = {permisos.rol_de(c.usuario) for c in Colaborador.objects.filter(usuario__isnull=False)}
    assert roles == {"GERENTE", "JEFATURA", "COLABORADOR"}


def test_datos_de_ejemplo_se_niega_a_correr_en_produccion(settings):
    settings.PRODUCCION = True
    with pytest.raises(CommandError, match="producción"):
        call_command("datos_de_ejemplo", "--password", "ejemplo-ejemplo-1")
    assert Tarea.objects.count() == 0
