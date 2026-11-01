"""Feriados (propuesta de librería + confirmación de Karla) y parámetros."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from nucleo.models import Anio, EventoAuditoria, Feriado
from nucleo.servicios import feriados, parametros
from nucleo.servicios.errores import ErrorDeNegocio

pytestmark = pytest.mark.django_db


def test_la_propuesta_de_la_libreria_queda_sin_confirmar():
    creados = feriados.cargar_propuesta(2026)
    assert creados > 0
    assert Feriado.objects.filter(fecha=date(2026, 12, 8)).exists()
    assert not Feriado.objects.filter(fecha__year=2026, confirmado=True).exists()  # (2027 y 2028 vienen ya confirmados de fábrica)


def test_cargar_la_propuesta_dos_veces_no_duplica_ni_pisa_lo_confirmado():
    feriados.cargar_propuesta(2026)
    f = Feriado.objects.get(fecha=date(2026, 12, 8))
    f.nombre, f.confirmado = "Ajustado a mano", True
    f.save()
    assert feriados.cargar_propuesta(2026) == 0
    assert Feriado.objects.get(fecha=date(2026, 12, 8)).nombre == "Ajustado a mano"


def test_el_calendario_solo_usa_feriados_confirmados():
    feriados.cargar_propuesta(2026)
    assert not feriados.calendario_confirmado().es_feriado(date(2026, 12, 8))
    Feriado.objects.filter(fecha=date(2026, 12, 8)).update(confirmado=True)
    assert feriados.calendario_confirmado().es_feriado(date(2026, 12, 8))


def test_no_se_abre_un_anio_con_feriados_sin_confirmar():
    feriados.cargar_propuesta(2026)
    with pytest.raises(ErrorDeNegocio, match="sin confirmar"):
        feriados.abrir_anio(2026, usuario=None)


def test_no_se_abre_un_anio_sin_feriados_cargados():
    with pytest.raises(ErrorDeNegocio, match="feriados"):
        feriados.abrir_anio(2026, usuario=None)


def test_confirmar_y_abrir_deja_registro_de_quien_y_cuando():
    karla = get_user_model().objects.create_user("karla", password="x" * 12)
    feriados.cargar_propuesta(2026)
    feriados.confirmar_anio(2026, karla)
    f = Feriado.objects.get(fecha=date(2026, 12, 8))
    assert f.confirmado and f.confirmado_por == karla and f.confirmado_en is not None
    feriados.abrir_anio(2026, karla)
    assert Anio.objects.get(anio=2026).estado == "abierto"
    assert set(EventoAuditoria.objects.values_list("accion", flat=True)) >= {"feriados.confirmados", "anio.abierto"}


def test_un_feriado_decretado_a_ultima_hora_se_agrega_a_mano():
    karla = get_user_model().objects.create_user("karla", password="x" * 12)
    feriados.agregar_o_editar(date(2026, 11, 3), "Feriado decretado (prueba)", "decretado", karla)
    f = Feriado.objects.get(fecha=date(2026, 11, 3))
    assert f.origen == "manual" and f.tipo == "decretado" and not f.confirmado  # también hay que confirmarlo


# ---- Parámetros -------------------------------------------------------------------------------


def test_los_valores_iniciales_son_los_de_legion_y_quedan_pendientes():
    assert parametros.entero("meta_cumplimiento") == 95
    assert parametros.entero("umbral_ambar") == 90
    assert parametros.entero("plazo_revision_dias_habiles") == 1
    assert parametros.entero("minimo_muestra_semaforo") == 10
    assert parametros.entero("min_dias_habiles_d7_d10") == 1
    assert parametros.estado("umbral_ambar") == "pendiente_confirmar"
    assert parametros.estado("meta_cumplimiento") == "confirmado"  # la meta del 95 % la fijó Karla


def test_un_valor_guardado_manda_sobre_el_inicial():
    parametros.guardar("umbral_ambar", "92", usuario=None, confirmado=True)
    assert parametros.entero("umbral_ambar") == 92 and parametros.estado("umbral_ambar") == "confirmado"
    assert EventoAuditoria.objects.filter(accion="parametro.editado").exists()


def test_un_parametro_desconocido_es_error():
    with pytest.raises(ErrorDeNegocio):
        parametros.guardar("inventado", "1", usuario=None)
