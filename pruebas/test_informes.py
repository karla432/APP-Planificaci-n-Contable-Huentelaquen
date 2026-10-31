"""Menú Informes: Panel del cierre y Cumplimiento por colaborador (visibles para todo el equipo, solo lectura)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia
from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)  # viernes, día hábil 4; el 08-12 es feriado
SCL = ZoneInfo("America/Santiago")


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa Gestión y Control"), cargo("Contadora Senior"), cargo("Gerente AyF")
    bodega = cargo("Bodega", externo=True)
    p = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont)}
    u = {"cont": usuario_con_rol("cont", "COLABORADOR", p["cont"]), "jefa": usuario_con_rol("jefa", "JEFATURA", p["jefa"]), "lectura": usuario_con_rol("lectura", "LECTURA")}
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=3)  # vencida y sin hacer
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=4)  # vence hoy, hecha a tiempo
    tarea("TAR-0003", jefa, "CIERRE_HITO", revisa=ger, proceso_nombre="Conciliación", n=7)  # aún no vence
    tarea("TAR-0004", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Conciliación", n=1)  # hecha tarde
    tarea("TAR-0005", bodega, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=2)  # externo, sin recibir
    periodos.abrir_mes(2026, 12, usuario=None)
    o = {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}
    for codigo, dia in (("TAR-0002", 4), ("TAR-0004", 2)):
        hora = datetime(2026, 12, dia, 10, 0, tzinfo=SCL)
        Ocurrencia.objects.filter(pk=o[codigo].pk).update(estado="hecha", primera_hecha_en=hora, hecha_en=hora)
    return {"u": u}


def ver(usuario, nombre, **params):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse(nombre), params)
    assert r.status_code == 200, r.status_code
    return r.content.decode()


# ---- Panel del cierre -----------------------------------------------------------------------------


def test_el_panel_muestra_el_cierre_del_mes_y_los_dias_habiles_que_faltan(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Cierre contable" in html and "diciembre 2026" in html
    assert "día hábil 4" in html
    assert "1 día hábil" in html and "3 días hábiles" in html  # D7 el lunes 07; D10 el jueves 10 (el 08 es feriado)


def test_el_panel_tiene_la_ruta_del_cierre_con_sus_fechas(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Ruta del cierre" in html
    for texto in ("Día 1", "Día 2", "Día 3", "Día 4", "D7", "D10", "01-12-2026", "07-12-2026", "10-12-2026"):
        assert texto in html, texto


def test_el_panel_resume_avance_atrasadas_y_cumplimiento_del_equipo(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Avance del cierre" in html and "2 de 5" in html  # hechas 2 de 5 tareas del cierre
    assert "Atrasadas sin hacer" in html
    assert "Cumplimiento a tiempo del equipo" in html and "0 de 2" in html  # TAR-0001 y TAR-0004 vencidas, ninguna a tiempo (la del externo no entra al equipo)


def test_el_panel_muestra_el_avance_por_proceso_con_texto(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Avance por proceso" in html and "Compras" in html and "Conciliación" in html
    assert "Atrasado" in html and "Por vencer" in html


def test_el_panel_incluye_el_cumplimiento_por_colaborador(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Cumplimiento por colaborador" in html and "Contadora" in html and "Meta 95%" in html


def test_un_mes_sin_abrir_lo_dice(mundo):
    assert "no se ha abierto" in ver(mundo["u"]["lectura"], "informe_panel", mes="2027-03").lower()


# ---- Cumplimiento por colaborador -----------------------------------------------------------------


def test_el_cumplimiento_lista_a_cada_colaborador_con_su_porcentaje_y_texto(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Contadora" in html and "Jefa" in html
    assert "0 de 2" in html  # la Contadora: TAR-0001 (sin hacer) y TAR-0004 (tarde)
    assert "Muestra insuficiente" in html and "Sin datos" in html


def test_los_externos_se_miden_aparte_y_no_entran_en_el_cuadro_del_equipo(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Insumos de responsables externos" in html and "Bodega" in html
    cuadro = html.split("Insumos de responsables externos")[0]
    assert "Bodega" not in cuadro


def test_el_cumplimiento_incluye_la_revision(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Cumplimiento de revisión" in html and "Jefa Gestión y Control" in html


def test_cualquier_perfil_con_acceso_puede_verlo_pero_sin_perfil_no(mundo):
    sin = usuario_con_rol("fantasma", None)
    c = Client()
    c.force_login(sin)
    assert c.get(reverse("informe_panel")).status_code == 403
    assert c.get(reverse("informe_cumplimiento")).status_code == 403


def test_el_panel_lista_los_feriados_confirmados_del_mes_y_no_inventa_ninguno(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Feriados del mes" in html and "08-12-2026" in html and "25-12-2026" in html
    from nucleo.models import Feriado
    Feriado.objects.all().delete()
    sin = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Feriados del mes" not in sin and "08 de diciembre" not in sin


def test_el_cumplimiento_lista_a_las_personas_en_el_orden_de_los_cargos(mundo):
    """Gerente AyF, Jefa, Contadora Senior, Asistente Contable: el orden que definió Karla, no el alfabético."""
    from nucleo.models import Cargo
    for nombre, orden in (("Gerente AyF", 1), ("Jefa Gestión y Control", 2), ("Contadora Senior", 3), ("Asistente Contable", 4)):
        Cargo.objects.update_or_create(nombre=nombre, defaults={"orden": orden})
    asistente = cargo("Asistente Contable")
    ger = persona("Aaa Gerente", cargo("Gerente AyF"))
    pa = persona("Zzz Asistente", asistente)
    tarea("TAR-0090", asistente, "CIERRE_DIA_HABIL", revisa=cargo("Jefa Gestión y Control"), n=1)
    tarea("TAR-0091", cargo("Gerente AyF"), "CIERRE_DIA_HABIL", revisa=cargo("Jefa Gestión y Control"), n=1)
    periodos.abrir_mes(2026, 12, usuario=None)
    html = ver(mundo["u"]["lectura"], "informe_cumplimiento")
    cuadro = html.split("Cumplimiento de revisión")[0]
    posiciones = [cuadro.index(n) for n in ("Aaa Gerente", "Jefa", "Contadora", "Zzz Asistente")]
    assert posiciones == sorted(posiciones)
