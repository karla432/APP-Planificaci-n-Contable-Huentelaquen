"""Detalle de una tarea del mes: datos, historial, comentarios y las acciones que le corresponden a cada perfil."""
from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import EventoAuditoria, Ocurrencia, Periodo
from nucleo.servicios import ejecucion, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    ger, cont, jefa, bodega = cargo("Gerente AyF"), cargo("Contadora Senior"), cargo("Jefa Gestión y Control"), cargo("Bodega", externo=True)
    p = {"ger": persona("Gerente", ger), "cont": persona("Contadora", cont), "jefa": persona("Jefa", jefa)}
    u = {k: usuario_con_rol(k, r, p[k]) for k, r in (("ger", "GERENTE"), ("cont", "COLABORADOR"), ("jefa", "JEFATURA"))}
    u["lectura"] = usuario_con_rol("lectura", "LECTURA")
    anio_abierto()
    t = tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    t.minutos_estimados, t.referencia_normativa = 90, "Art. 20 N°1 LIR"
    t.save()
    tarea("TAR-0002", bodega, "CIERRE_DIA_HABIL", revisa=ger, n=3)
    tarea("TAR-0003", cont, "CIERRE_DIA_HABIL", n=3)  # sin revisor
    periodos.abrir_mes(2026, 12, usuario=None)
    return {"u": u, "o": {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}}


# ---- Acciones disponibles --------------------------------------------------------------------------------


def test_el_dueno_puede_marcar_o_bloquear_una_tarea_pendiente(mundo):
    assert ejecucion.acciones_disponibles(mundo["o"]["TAR-0001"], mundo["u"]["cont"]) == ["hecha", "bloquear"]


def test_el_revisor_puede_revisar_y_devolver_lo_hecho_por_otro(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    assert ejecucion.acciones_disponibles(o, mundo["u"]["ger"]) == ["revisar", "devolver"]
    assert ejecucion.acciones_disponibles(o, mundo["u"]["cont"]) == []  # nadie revisa lo propio
    assert ejecucion.acciones_disponibles(o, mundo["u"]["jefa"]) == []  # no es quien revisa


def test_el_que_recibe_marca_recibido_lo_de_un_externo(mundo):
    assert ejecucion.acciones_disponibles(mundo["o"]["TAR-0002"], mundo["u"]["ger"]) == ["recibida"]
    assert ejecucion.acciones_disponibles(mundo["o"]["TAR-0002"], mundo["u"]["cont"]) == []


def test_una_tarea_bloqueada_solo_ofrece_retomar_a_su_dueno(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_bloqueada(o, mundo["u"]["cont"], motivo="Falta un insumo")
    assert ejecucion.acciones_disponibles(o, mundo["u"]["cont"]) == ["retomar"]


def test_sin_perfil_o_con_el_periodo_cerrado_no_hay_acciones(mundo):
    assert ejecucion.acciones_disponibles(mundo["o"]["TAR-0001"], mundo["u"]["lectura"]) == []
    Periodo.objects.update(estado="cerrado")
    o = Ocurrencia.objects.select_related("periodo").get(pk=mundo["o"]["TAR-0001"].pk)
    assert ejecucion.acciones_disponibles(o, mundo["u"]["cont"]) == []


# ---- Comentarios e historial -----------------------------------------------------------------------------


def test_comentar_queda_en_el_historial_con_quien_y_cuando(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.comentar(o, mundo["u"]["cont"], "Ya pedí la liquidación a Lechería")
    ev = EventoAuditoria.objects.get(accion="ocurrencia.comentario", entidad_id=str(o.pk))
    assert ev.usuario == mundo["u"]["cont"] and ev.motivo == "Ya pedí la liquidación a Lechería"
    h = ejecucion.historial_de(o)
    assert [x.texto for x in h] == ["Comentó"] and h[0].comentario == "Ya pedí la liquidación a Lechería"


def test_un_comentario_exige_texto_y_perfil_que_participe(mundo):
    o = mundo["o"]["TAR-0001"]
    with pytest.raises(ErrorDeNegocio, match="comentario"):
        ejecucion.comentar(o, mundo["u"]["cont"], "  ")
    with pytest.raises(PermisoDenegado):
        ejecucion.comentar(o, mundo["u"]["lectura"], "hola")


def test_el_historial_cuenta_toda_la_vida_de_la_tarea_en_orden(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_bloqueada(o, mundo["u"]["cont"], motivo="Falta un insumo")
    ejecucion.retomar(o, mundo["u"]["cont"])
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    ejecucion.devolver(o, mundo["u"]["ger"], "Falta el respaldo")
    assert [x.texto for x in ejecucion.historial_de(o)] == ["Marcó bloqueada", "Retomó la tarea", "Marcó hecha", "Devolvió"]


# ---- Pantalla --------------------------------------------------------------------------------------------


def ver(usuario, o):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse("detalle_ocurrencia", args=[o.pk]))
    assert r.status_code == 200
    return r.content.decode()


def test_el_detalle_muestra_los_datos_la_referencia_y_las_horas_como_estimadas(mundo):
    html = ver(mundo["u"]["cont"], mundo["o"]["TAR-0001"])
    for texto in ("Subtarea TAR-0001", "Contadora Senior", "Gerente AyF", "Día 3", "03-12-2026", "Art. 20 N°1 LIR", "1,5 h", "Estimado", "Revisa"):
        assert texto in html, texto


def test_una_tarea_sin_revisor_lo_dice(mundo):
    assert "Sin revisor" in ver(mundo["u"]["cont"], mundo["o"]["TAR-0003"])


def test_el_detalle_ofrece_solo_las_acciones_del_perfil_y_las_ejecuta(mundo):
    o = mundo["o"]["TAR-0001"]
    html = ver(mundo["u"]["cont"], o)
    assert "Marcar hecha" in html and "Marcar bloqueada" in html and "Revisar" not in html.split("Historial")[0].split("Acciones")[-1]
    c = Client()
    c.force_login(mundo["u"]["cont"])
    r = c.post(reverse("ocurrencia_accion", args=[o.pk, "comentar"]), {"comentario": "Avanzando", "siguiente": reverse("detalle_ocurrencia", args=[o.pk])})
    assert r.status_code == 302 and r["Location"] == reverse("detalle_ocurrencia", args=[o.pk])
    assert "Avanzando" in ver(mundo["u"]["cont"], o)


def test_un_comentario_se_escapa_contra_xss(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.comentar(o, mundo["u"]["cont"], "<script>alert(1)</script>")
    html = ver(mundo["u"]["ger"], o)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_sin_perfil_no_ve_el_detalle(mundo):
    c = Client()
    c.force_login(usuario_con_rol("fantasma", None))
    assert c.get(reverse("detalle_ocurrencia", args=[mundo["o"]["TAR-0001"].pk])).status_code == 403
