"""Pantalla «Hoy»: lo mío, lo que reviso y lo que recibo; acciones por POST validadas en el servidor."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia
from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)  # viernes, Día 4 del cierre


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    jefa, cont, ger, bodega = cargo("Jefa de Control"), cargo("Contador Senior"), cargo("Gerente AyF"), cargo("Bodega", externo=True)
    p = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont), "ger": persona("Gerente", ger)}
    u = {k: usuario_con_rol(k, r, p[k]) for k, r in (("jefa", "JEFATURA"), ("cont", "COLABORADOR"), ("ger", "GERENTE"))}
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=3)  # venció el jueves 03-12 (atrasada)
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=4)  # vence hoy
    tarea("TAR-0003", jefa, "CIERRE_HITO", revisa=ger, n=8)  # próxima: miércoles 09-12 (el 8 es feriado)
    tarea("TAR-0004", bodega, "CIERRE_DIA_HABIL", revisa=jefa, n=4)  # externo, vence hoy
    periodos.abrir_mes(2026, 12, usuario=None)
    o = {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}
    return {"p": p, "u": u, "o": o}


def cliente(usuario):
    c = Client()
    c.force_login(usuario)
    return c


def test_la_contadora_ve_lo_suyo_separado_en_atrasadas_hoy_y_proximas(mundo):
    html = cliente(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()
    assert "Atrasadas" in html and "Vencen hoy" in html
    assert "Subtarea TAR-0001" in html and "Subtarea TAR-0002" in html
    assert "Subtarea TAR-0003" not in html  # es de la Jefa
    assert "Atrasada 1 día" in html  # con texto, no solo color
    assert "03-12-2026" in html  # fechas dd-mm-aaaa


def test_se_puede_mirar_el_dia_de_otra_persona_pero_solo_de_lectura(mundo):
    r = cliente(mundo["u"]["jefa"]).get(reverse("hoy"), {"persona": mundo["p"]["cont"].pk})
    html = r.content.decode()
    assert "Subtarea TAR-0001" in html and "Solo lectura" in html
    assert f"/ocurrencias/{mundo['o']['TAR-0001'].pk}/hecha/" not in html


def test_el_dueno_marca_hecha_y_queda_con_hora_del_servidor(mundo):
    o = mundo["o"]["TAR-0002"]
    r = cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]))
    assert r.status_code == 302
    o.refresh_from_db()
    assert o.estado == "hecha" and o.hecha_por == mundo["u"]["cont"] and o.hecha_en is not None


def test_otra_persona_no_puede_marcar_tareas_ajenas_por_la_url(mundo):
    o = mundo["o"]["TAR-0002"]
    for quien in ("jefa", "ger"):
        r = cliente(mundo["u"][quien]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]))
        assert r.status_code == 403
    o.refresh_from_db()
    assert o.estado == "pendiente"


def test_las_acciones_exigen_post_y_sesion_y_csrf(mundo):
    o = mundo["o"]["TAR-0002"]
    url = reverse("ocurrencia_accion", args=[o.pk, "hecha"])
    assert cliente(mundo["u"]["cont"]).get(url).status_code == 405
    assert Client().post(url).status_code == 302  # sin sesión → al ingreso
    c = Client(enforce_csrf_checks=True)
    c.force_login(mundo["u"]["cont"])
    assert c.post(url).status_code == 403  # sin token CSRF


def test_una_accion_desconocida_es_404(mundo):
    o = mundo["o"]["TAR-0002"]
    assert cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "borrar"])).status_code == 404


def test_la_jefa_ve_lo_que_debe_revisar_y_lo_revisa(mundo):
    o = mundo["o"]["TAR-0002"]
    cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]))
    c = cliente(mundo["u"]["jefa"])
    assert "Subtarea TAR-0002" in c.get(reverse("hoy")).content.decode().split("Por revisar")[1]
    assert c.post(reverse("ocurrencia_accion", args=[o.pk, "revisar"])).status_code == 302
    o.refresh_from_db()
    assert o.estado == "revisada" and o.revisada_por == mundo["u"]["jefa"]


def test_devolver_sin_comentario_no_devuelve_y_con_comentario_si(mundo):
    o = mundo["o"]["TAR-0002"]
    cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]))
    c = cliente(mundo["u"]["jefa"])
    url = reverse("ocurrencia_accion", args=[o.pk, "devolver"])
    c.post(url, {"comentario": "  "})
    o.refresh_from_db()
    assert o.estado == "hecha"
    c.post(url, {"comentario": "Falta el respaldo"})
    o.refresh_from_db()
    assert o.estado == "devuelta"
    html = cliente(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()
    assert "Falta el respaldo" in html  # la contadora ve por qué se la devolvieron


def test_la_jefa_recibe_lo_del_externo_y_el_colaborador_no(mundo):
    o = mundo["o"]["TAR-0004"]
    assert "Subtarea TAR-0004" in cliente(mundo["u"]["jefa"]).get(reverse("hoy")).content.decode().split("Por recibir")[1]
    assert cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "recibida"])).status_code == 403
    assert cliente(mundo["u"]["jefa"]).post(reverse("ocurrencia_accion", args=[o.pk, "recibida"])).status_code == 302
    o.refresh_from_db()
    assert o.estado == "hecha" and o.tipo_marca == "RECIBIDA"


def test_sin_mes_abierto_dice_que_no_hay_nada_que_hacer(mundo):
    from nucleo.models import Periodo
    Periodo.objects.update(estado="cerrado")
    assert "No hay un mes abierto" in cliente(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()


def test_el_texto_de_los_motivos_se_escapa_contra_xss(mundo):
    o = mundo["o"]["TAR-0002"]
    cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "hecha"]))
    cliente(mundo["u"]["jefa"]).post(reverse("ocurrencia_accion", args=[o.pk, "devolver"]), {"comentario": "<script>alert(1)</script>"})
    html = cliente(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_el_dueno_bloquea_desde_la_pantalla_con_motivo_y_se_ve_el_motivo(mundo):
    o = mundo["o"]["TAR-0002"]
    url = reverse("ocurrencia_accion", args=[o.pk, "bloquear"])
    c = cliente(mundo["u"]["cont"])
    c.post(url, {"comentario": "  "})
    o.refresh_from_db()
    assert o.estado == "pendiente"  # sin motivo no bloquea
    assert c.post(url, {"comentario": "Falta la liquidación de Lechería"}).status_code == 302
    o.refresh_from_db()
    assert o.estado == "bloqueada"
    html = c.get(reverse("hoy")).content.decode()
    assert "Bloqueada" in html and "Falta la liquidación de Lechería" in html and "Retomar" in html


def test_retomar_y_la_proteccion_de_lo_ajeno(mundo):
    o = mundo["o"]["TAR-0002"]
    cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "bloquear"]), {"comentario": "Falta un insumo"})
    assert cliente(mundo["u"]["jefa"]).post(reverse("ocurrencia_accion", args=[o.pk, "retomar"])).status_code == 403
    assert cliente(mundo["u"]["cont"]).post(reverse("ocurrencia_accion", args=[o.pk, "retomar"])).status_code == 302
    o.refresh_from_db()
    assert o.estado == "pendiente"
