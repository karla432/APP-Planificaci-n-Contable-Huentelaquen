"""Tablero de estados y cronograma por día hábil: el cierre de un vistazo."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia, Proceso
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
    ger, cont, asis = cargo("Gerente AyF"), cargo("Contador Senior"), cargo("Asistente Contable")
    persona("Gerente", ger)
    p = {"cont": persona("Contadora", cont), "asis": persona("Asistente", asis)}
    u = {"cont": usuario_con_rol("cont", "COLABORADOR", p["cont"]), "lectura": usuario_con_rol("lectura", "LECTURA")}
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=ger, proceso_nombre="Compras", n=3)  # pendiente y atrasada
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=ger, proceso_nombre="Compras", n=3)  # bloqueada
    tarea("TAR-0003", cont, "CIERRE_DIA_HABIL", revisa=ger, proceso_nombre="Pagos", n=2)  # hecha: por revisar
    tarea("TAR-0004", cont, "CIERRE_DIA_HABIL", revisa=ger, proceso_nombre="Pagos", n=1)  # revisada
    tarea("TAR-0005", asis, "CIERRE_DIA_HABIL", proceso_nombre="Bancos", n=1)  # hecha, sin revisor: queda hecha
    tarea("TAR-0006", cont, "CIERRE_DIA_HABIL", revisa=ger, proceso_nombre="Bancos", n=4)  # devuelta
    tarea("TAR-0007", cont, "DIARIA_HABIL", proceso_nombre="Bancos")  # diaria: no es del cierre, no va al tablero
    periodos.abrir_mes(2026, 12, usuario=None)
    o = {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}
    hora = datetime(2026, 12, 2, 10, 0, tzinfo=SCL)
    for codigo, estado in (("TAR-0002", "bloqueada"), ("TAR-0003", "hecha"), ("TAR-0004", "revisada"), ("TAR-0005", "hecha"), ("TAR-0006", "devuelta")):
        Ocurrencia.objects.filter(pk=o[codigo].pk).update(estado=estado, primera_hecha_en=None if estado in ("bloqueada", "devuelta") else hora, hecha_en=None if estado in ("bloqueada", "devuelta") else hora)
    return {"u": u, "proceso": {p.nombre: p for p in Proceso.objects.all()}}


def ver(usuario, nombre, **params):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse(nombre), params)
    assert r.status_code == 200
    return r.content.decode()


def columna(html, titulo, siguiente):
    return html.split(f">{titulo}<")[1].split(f">{siguiente}<")[0]


def test_el_tablero_pone_cada_tarea_en_su_columna(mundo):
    h = ver(mundo["u"]["lectura"], "informe_tablero")
    assert "Subtarea TAR-0001" in columna(h, "Pendiente", "Bloqueada")
    assert "Subtarea TAR-0002" in columna(h, "Bloqueada", "Por revisar")
    assert "Subtarea TAR-0003" in columna(h, "Por revisar", "Hecha o revisada")
    assert "Subtarea TAR-0004" in columna(h, "Hecha o revisada", "Devuelta") and "Subtarea TAR-0005" in columna(h, "Hecha o revisada", "Devuelta")
    assert "Subtarea TAR-0006" in h.split(">Devuelta<")[1]
    assert "TAR-0007" not in h  # la diaria no es del cierre


def test_una_hecha_sin_revisor_no_queda_esperando_revision(mundo):
    h = ver(mundo["u"]["lectura"], "informe_tablero")
    assert "Subtarea TAR-0005" not in columna(h, "Por revisar", "Hecha o revisada")


def test_el_titular_cuenta_abiertas_y_atrasadas(mundo):
    h = ver(mundo["u"]["lectura"], "informe_tablero")
    # Abiertas: TAR-0001 (pendiente), TAR-0002 (bloqueada) y TAR-0006 (devuelta). Atrasadas: las dos primeras; la devuelta vence hoy.
    assert "3 tareas abiertas del cierre, 2 atrasadas" in h


def test_el_tablero_se_filtra_por_proceso_y_por_mis_tareas(mundo):
    h = ver(mundo["u"]["lectura"], "informe_tablero", proceso=mundo["proceso"]["Pagos"].pk)
    assert "Subtarea TAR-0003" in h and "Subtarea TAR-0001" not in h
    h = ver(mundo["u"]["cont"], "informe_tablero", solo_mias="1")
    assert "Subtarea TAR-0001" in h and "Subtarea TAR-0005" not in h  # TAR-0005 es de la Asistente


def test_las_tarjetas_enlazan_al_detalle_y_muestran_dia_y_atraso(mundo):
    h = ver(mundo["u"]["lectura"], "informe_tablero")
    pk = Ocurrencia.objects.get(tarea__codigo="TAR-0001").pk
    assert reverse("detalle_ocurrencia", args=[pk]) in h and "Atrasada" in h and "Día 3" in h


# ---- Cronograma -----------------------------------------------------------------------------------------


def test_el_cronograma_cruza_procesos_con_los_dias_del_cierre(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma")
    for texto in ("Día 1", "Día 8", "01-12-2026", "11-12-2026", "Compras", "Pagos", "Bancos"):
        assert texto in h, texto
    assert "08-12-2026" in h and "feriado" in h.lower()


def test_el_cronograma_sigue_el_orden_de_proceso_y_cuenta_tareas_por_celda(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma")
    assert h.index("Compras") < h.index("Pagos") < h.index("Bancos")  # el orden en que se procesan (por código)
    assert 'data-celda="Compras|3">2<' in h  # 2 tareas de Compras el día 3
    assert 'data-celda="Pagos|2">1<' in h


def test_las_celdas_se_marcan_por_estado_con_texto(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma")
    assert 'class="celda rd" data-celda="Compras|3"' in h  # con atrasadas
    assert 'class="celda ok" data-celda="Pagos|1"' in h  # todo hecho


def test_tocar_una_celda_lista_sus_tareas(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma", proceso=mundo["proceso"]["Compras"].pk, dia=3)
    assert "Subtarea TAR-0001" in h and "Subtarea TAR-0002" in h and "Subtarea TAR-0003" not in h


def test_el_cronograma_se_puede_ver_por_semana_y_por_mes(mundo):
    semana = ver(mundo["u"]["lectura"], "informe_cronograma", vista="semana", fecha="2026-12-03")
    assert "Semana del 30-11-2026 al 04-12-2026" in semana and "Semana anterior" in semana and "Semana siguiente" in semana
    assert "Compras" in semana and "Día 1" not in semana  # las columnas son lunes a viernes, no «Día N»
    mes = ver(mundo["u"]["lectura"], "informe_cronograma", vista="mes")
    assert "Mes completo" in mes and mes.count('<th class="c') >= 20  # una columna por cada día hábil del mes
    assert "Compras" in mes
    for vista in ("cierre", "semana", "mes"):
        assert f"vista={vista}" in mes  # las tres pestañas están siempre


def test_tocar_una_celda_en_la_vista_semanal_lista_las_tareas_de_ese_dia(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma", vista="semana", fecha="2026-12-03", proceso=mundo["proceso"]["Compras"].pk, dia="2026-12-03")
    assert "Subtarea TAR-0001" in h and "Subtarea TAR-0002" in h and "Subtarea TAR-0003" not in h


def test_una_vista_o_fecha_invalida_cae_en_el_cierre(mundo):
    h = ver(mundo["u"]["lectura"], "informe_cronograma", vista="inventada")
    assert "Día 1" in h
    assert ver(mundo["u"]["lectura"], "informe_cronograma", vista="semana", fecha="xx")
