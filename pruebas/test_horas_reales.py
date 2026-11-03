"""Horas reales: cada persona anota cuánto ocupó en su tarea, al marcarla hecha o después. Se comparan con lo estimado."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import EventoAuditoria, Ocurrencia
from nucleo.servicios import carga, ejecucion, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    ger, cont, asist, bodega = cargo("Gerente AyF"), cargo("Contador Senior"), cargo("Analista Contable"), cargo("Bodega", externo=True)
    p = {"ger": persona("Gerente", ger), "cont": persona("Contador", cont), "asist": persona("Asistente", asist)}
    u = {k: usuario_con_rol(k, r, p[k]) for k, r in (("ger", "GERENTE"), ("cont", "COLABORADOR"), ("asist", "COLABORADOR"))}
    anio_abierto()
    t = tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    t.minutos_estimados = 90
    t.save()
    t2 = tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=ger, n=4)
    t2.minutos_estimados = 60
    t2.save()
    tarea("TAR-0003", asist, "CIERRE_DIA_HABIL", n=3)
    tarea("TAR-0004", bodega, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    periodos.abrir_mes(2026, 12, usuario=None)
    return {"u": u, "o": {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}}


# ---- Cómo se escribe el tiempo ---------------------------------------------------------------------------------


@pytest.mark.parametrize("texto,minutos", [("1,5", 90), ("1.5", 90), ("2", 120), ("0,25", 15), ("1:30", 90), (" 0:45 ", 45), ("", None), ("   ", None)])
def test_el_tiempo_se_entiende_en_horas_con_coma_punto_o_horas_y_minutos(texto, minutos):
    assert ejecucion.parsear_horas(texto) == minutos


@pytest.mark.parametrize("texto", ["abc", "-1", "0", "25", "1:75", "1,5,5", "9999"])
def test_un_tiempo_invalido_se_rechaza_con_un_mensaje_claro(texto):
    with pytest.raises(ErrorDeNegocio):
        ejecucion.parsear_horas(texto)


# ---- Registrar --------------------------------------------------------------------------------------------------


def test_se_pueden_anotar_las_horas_al_marcar_hecha(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"], minutos_reales=100)
    o.refresh_from_db()
    assert o.estado == "hecha" and o.minutos_reales == 100


def test_marcar_hecha_sin_horas_sigue_funcionando(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    o.refresh_from_db()
    assert o.estado == "hecha" and o.minutos_reales is None


def test_las_horas_se_pueden_anotar_o_corregir_despues_y_queda_en_la_bitacora(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    ejecucion.registrar_horas(o, mundo["u"]["cont"], 75)
    ejecucion.registrar_horas(o, mundo["u"]["cont"], 80)
    o.refresh_from_db()
    assert o.minutos_reales == 80
    eventos = list(EventoAuditoria.objects.filter(accion="ocurrencia.horas_reales", entidad_id=str(o.pk)).order_by("id"))
    assert [(e.antes["minutos_reales"], e.despues["minutos_reales"]) for e in eventos] == [(None, 75), (75, 80)]


def test_solo_quien_ejecuta_la_tarea_anota_sus_horas(mundo):
    o = mundo["o"]["TAR-0001"]
    for quien in ("asist", "ger"):
        with pytest.raises(PermisoDenegado):
            ejecucion.registrar_horas(o, mundo["u"][quien], 60)


def test_una_tarea_de_un_externo_no_lleva_horas(mundo):
    with pytest.raises(PermisoDenegado):
        ejecucion.registrar_horas(mundo["o"]["TAR-0004"], mundo["u"]["ger"], 60)


def test_un_periodo_cerrado_no_admite_cambios_de_horas(mundo):
    o = mundo["o"]["TAR-0001"]
    o.periodo.estado = "cerrado"
    o.periodo.save()
    with pytest.raises(ErrorDeNegocio):
        ejecucion.registrar_horas(o, mundo["u"]["cont"], 60)


def test_puede_registrar_horas_dice_a_la_pantalla_cuando_ofrecer_el_campo(mundo):
    o = mundo["o"]["TAR-0001"]
    assert ejecucion.puede_registrar_horas(o, mundo["u"]["cont"]) and not ejecucion.puede_registrar_horas(o, mundo["u"]["asist"])
    assert not ejecucion.puede_registrar_horas(mundo["o"]["TAR-0004"], mundo["u"]["ger"])


# ---- Pantallas ------------------------------------------------------------------------------------------------


def cli(u):
    c = Client()
    c.force_login(u)
    return c


def test_marcar_hecha_desde_la_lista_con_horas(mundo):
    o = mundo["o"]["TAR-0001"]
    r = cli(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]), {"horas": "1,25", "siguiente": reverse("hoy")})
    assert r.status_code == 302
    o.refresh_from_db()
    assert o.estado == "hecha" and o.minutos_reales == 75


def test_un_tiempo_mal_escrito_no_marca_la_tarea_y_avisa(mundo):
    o = mundo["o"]["TAR-0001"]
    r = cli(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]), {"horas": "mucho", "siguiente": reverse("hoy")}, follow=True)
    o.refresh_from_db()
    assert o.estado == "pendiente" and "horas" in r.content.decode().lower()


def test_la_accion_horas_corrige_el_tiempo_y_otro_usuario_recibe_403(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    assert cli(mundo["u"]["asist"]).post(reverse("ocurrencia_accion", args=[o.pk, "horas"]), {"horas": "2"}).status_code == 403
    cli(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "horas"]), {"horas": "2", "siguiente": reverse("hoy")})
    o.refresh_from_db()
    assert o.minutos_reales == 120


def test_el_detalle_muestra_estimado_y_real_y_ofrece_el_campo_solo_a_quien_corresponde(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"], minutos_reales=105)
    html = cli(mundo["u"]["cont"]).get(reverse("detalle_ocurrencia", args=[o.pk])).content.decode()
    assert "Horas reales" in html and "1,75 h" in html and "Registrar horas reales" in html
    assert "Registrar horas reales" not in cli(mundo["u"]["ger"]).get(reverse("detalle_ocurrencia", args=[o.pk])).content.decode()


def test_la_lista_de_mis_tareas_pide_las_horas_de_forma_opcional(mundo):
    html = cli(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()
    assert 'name="horas"' in html and "Horas reales" in html


# ---- Estimado contra real ---------------------------------------------------------------------------------------


def test_estimado_contra_real_compara_solo_lo_que_tiene_horas_reales(mundo):
    ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], mundo["u"]["cont"], minutos_reales=120)  # estimado 90
    ejecucion.marcar_hecha(mundo["o"]["TAR-0002"], mundo["u"]["cont"])  # hecha, sin horas reales
    periodo = mundo["o"]["TAR-0001"].periodo
    filas = {f.colaborador.nombre: f for f in carga.real_vs_estimado(periodo)}
    c = filas["Contador"]
    assert (c.con_horas, c.hechas, c.sin_horas) == (1, 2, 1)
    assert c.horas_estimadas == pytest.approx(1.5) and c.horas_reales == pytest.approx(2.0)
    assert c.diferencia_pct == pytest.approx(33.3, abs=0.1)
    assert filas["Asistente"].con_horas == 0 and filas["Asistente"].diferencia_pct is None


def test_el_informe_de_carga_muestra_el_real_contra_el_estimado(mundo):
    ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], mundo["u"]["cont"], minutos_reales=120)
    html = cli(mundo["u"]["ger"]).get(reverse("informe_carga")).content.decode()
    assert "Horas reales del mes" in html and "Contador" in html and "2,0" in html
