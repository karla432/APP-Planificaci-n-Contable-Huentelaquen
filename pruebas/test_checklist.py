"""Menú tipo Arqueo y Check List: Mi día, Mi semana, Mi mes, con el cumplimiento de cada usuario a la vista."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia
from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)  # viernes


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa Gestión y Control"), cargo("Contadora Senior"), cargo("Gerente AyF")
    p = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont), "ger": persona("Gerente", ger)}
    u = {k: usuario_con_rol(k, r, p[k]) for k, r in (("jefa", "JEFATURA"), ("cont", "COLABORADOR"), ("ger", "GERENTE"))}
    u["admin"] = usuario_con_rol("admin", "ADMIN_SISTEMA")
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=3)  # jueves 03-12, sin hacer
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=4)  # viernes 04-12 (hoy)
    tarea("TAR-0003", jefa, "CIERRE_HITO", revisa=ger, n=7)  # lunes 07-12
    periodos.abrir_mes(2026, 12, usuario=None)
    return {"p": p, "u": u, "o": {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}}


def ver(usuario, nombre, **params):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse(nombre), params)
    assert r.status_code == 200, r.status_code
    return r.content.decode()


# ---- Menú ---------------------------------------------------------------------------------------


def test_el_menu_tiene_informes_y_check_list_con_dia_semana_y_mes(mundo):
    html = ver(mundo["u"]["cont"], "hoy")
    for texto in ("Informes", "Check List", "Mi día", "Mi semana", "Mi mes", "Por cargo y responsable"):
        assert texto in html, texto


def test_el_mantenedor_solo_aparece_a_quien_corresponde(mundo):
    assert "Mantenedor" not in ver(mundo["u"]["cont"], "hoy")
    jefa = ver(mundo["u"]["jefa"], "hoy")
    assert "Mantenedor" in jefa and "Tareas" in jefa and "Usuarios" not in jefa
    ger = ver(mundo["u"]["ger"], "hoy")
    assert "Mantenedor" in ger and "Usuarios" in ger
    assert "Usuarios" in ver(mundo["u"]["admin"], "hoy")


def test_el_menu_marca_donde_estoy(mundo):
    assert 'nav-on' in ver(mundo["u"]["cont"], "hoy")


# ---- Mi cumplimiento ------------------------------------------------------------------------------


def test_cada_usuario_ve_su_cumplimiento_con_meta_y_texto(mundo):
    html = ver(mundo["u"]["cont"], "hoy")
    assert "Mi cumplimiento" in html and "Meta 95" in html
    assert "0 de 1" in html  # 1 tarea vencida (TAR-0001) y ninguna a tiempo
    assert "muestra insuficiente" in html.lower()  # con 1 tarea no se colorea el semáforo


def test_al_mirar_a_otra_persona_se_ve_su_cumplimiento(mundo):
    html = ver(mundo["u"]["jefa"], "hoy", persona=mundo["p"]["cont"].pk)
    assert "Cumplimiento de Contadora" in html and "0 de 1" in html


def test_sin_tareas_vencidas_dice_sin_datos(mundo):
    assert "sin datos" in ver(mundo["u"]["ger"], "hoy").lower()


# ---- Semana ---------------------------------------------------------------------------------------


def test_la_semana_muestra_lunes_a_viernes_con_sus_tareas(mundo):
    html = ver(mundo["u"]["cont"], "semana")
    for f in ("30-11-2026", "01-12-2026", "02-12-2026", "03-12-2026", "04-12-2026"):
        assert f in html, f
    assert html.index("Subtarea TAR-0001") < html.index("Subtarea TAR-0002")  # jueves antes que viernes
    assert "Subtarea TAR-0003" not in html


def test_la_semana_siguiente_muestra_el_feriado_explicito(mundo):
    html = ver(mundo["u"]["cont"], "semana", fecha="2026-12-07")
    assert "08-12-2026" in html and "Feriado de prueba" in html and "0 h" in html


def test_la_semana_tiene_flechas_anterior_y_siguiente(mundo):
    html = ver(mundo["u"]["cont"], "semana")
    assert "Semana anterior" in html and "Semana siguiente" in html and "fecha=2026-12-07" in html


# ---- Mes ------------------------------------------------------------------------------------------


def test_el_mes_muestra_la_ruta_del_cierre_y_las_tareas_de_la_persona(mundo):
    html = ver(mundo["u"]["cont"], "mes")
    for texto in ("Ruta del cierre", "Día 1", "Día 4", "Día 8", "Día 10", "11-12-2026", "15-12-2026"):
        assert texto in html, texto
    assert "Subtarea TAR-0001" in html and "Subtarea TAR-0002" in html and "Subtarea TAR-0003" not in html
    assert "Pendiente" in html


def test_el_mes_se_puede_cambiar(mundo):
    html = ver(mundo["u"]["cont"], "mes", mes="2026-11")
    assert "noviembre" in html.lower() and "Subtarea TAR-0001" not in html
    assert "Mes anterior" in html and "Mes siguiente" in html


def test_las_tres_vistas_son_pestanas_de_lo_mismo(mundo):
    for nombre in ("hoy", "semana", "mes"):
        html = ver(mundo["u"]["cont"], nombre)
        assert reverse("hoy") in html and reverse("semana") in html and reverse("mes") in html
