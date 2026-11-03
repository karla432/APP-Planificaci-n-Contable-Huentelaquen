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


def test_datos_de_ejemplo_arma_noviembre_como_primer_mes_navegable():
    call_command("datos_de_ejemplo", "--password", "ejemplo-ejemplo-1")
    assert Tarea.objects.filter(activa=True).count() == 206 and Tarea.objects.count() == 214  # la Planificación 2.0 (206 tareas) encima del listado anterior (8 quedan desactivadas)
    assert Colaborador.objects.filter(usuario__isnull=False).count() == 4
    assert list(Periodo.objects.values_list("anio", "mes")) == [(2026, 11)]  # el calendario empieza en noviembre; diciembre se abre después
    assert Periodo.objects.get(mes=11).inicio_medicion == date(2026, 11, 5)
    assert Ocurrencia.objects.filter(periodo__mes=11).exists() and not Ocurrencia.objects.filter(fecha_limite__lt=date(2026, 11, 5)).exists()
    roles = {permisos.rol_de(c.usuario) for c in Colaborador.objects.filter(usuario__isnull=False)}
    assert roles == {"GERENTE", "JEFATURA", "COLABORADOR"}


def test_datos_de_ejemplo_se_niega_a_correr_en_produccion(settings):
    settings.PRODUCCION = True
    with pytest.raises(CommandError, match="producción"):
        call_command("datos_de_ejemplo", "--password", "ejemplo-ejemplo-1")
    assert Tarea.objects.count() == 0


def test_cargar_ejemplo_planificacion_trae_el_catalogo_y_el_ejemplo_de_ventas():
    from nucleo.models import Proceso, TareaPrincipal
    call_command("cargar_ejemplo_planificacion")
    assert [p.codigo for p in Proceso.objects.all()][:3] == ["01-PLA", "02-VEN", "03-CXC"] and Proceso.objects.count() == 11
    assert [t.codigo for t in TareaPrincipal.objects.all()] == ["02-VEN.01", "02-VEN.02", "02-VEN.03"]
    assert list(Tarea.objects.order_by("codigo").values_list("codigo", flat=True)) == [
        "02-VEN.01.001", "02-VEN.01.002", "02-VEN.01.003", "02-VEN.02.001", "02-VEN.02.002", "02-VEN.02.003", "02-VEN.03.001", "02-VEN.03.002"]


def test_el_ejemplo_de_planificacion_se_niega_en_produccion_y_si_ya_hay_procesos(settings):
    from nucleo.models import Proceso
    Proceso.objects.create(nombre="Ya existe", sigla="YAE")
    with pytest.raises(CommandError, match="ya tiene procesos"):
        call_command("cargar_ejemplo_planificacion")
    settings.PRODUCCION = True
    with pytest.raises(CommandError, match="producción"):
        call_command("cargar_ejemplo_planificacion")
