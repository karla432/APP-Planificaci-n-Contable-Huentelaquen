"""Días hábiles, feriados y las fechas de entrega del cierre: días 8, 9 y 10 del mes (Karla, 01-11-2026).

Los feriados que se usan aquí son datos de prueba: en la aplicación solo cuentan los feriados confirmados.
"""
from datetime import date

import pytest

from nucleo.servicios.calendario import JORNADA_HORAS, Calendario, hitos_de_entrega, ventana_del_cierre

# 08-12-2026 (martes) lo da el encargo; los demás son sintéticos para forzar cada caso.
FERIADOS_2026 = [date(2026, 12, 8), date(2026, 12, 25)]


def test_sabado_y_domingo_nunca_son_habiles():
    cal = Calendario([])
    assert not cal.es_habil(date(2026, 11, 7))  # sábado
    assert not cal.es_habil(date(2026, 11, 8))  # domingo
    assert cal.es_habil(date(2026, 11, 9))  # lunes


def test_un_feriado_entre_semana_no_es_habil():
    cal = Calendario(FERIADOS_2026)
    assert not cal.es_habil(date(2026, 12, 8))  # martes feriado
    assert cal.es_habil(date(2026, 12, 9))


def test_siguiente_habil_salta_fin_de_semana_y_feriado():
    cal = Calendario([date(2026, 11, 9)])  # lunes feriado
    assert cal.siguiente_habil(date(2026, 11, 7)) == date(2026, 11, 10)  # sáb → mar
    assert cal.siguiente_habil(date(2026, 11, 10)) == date(2026, 11, 10)  # ya es hábil


def test_anterior_habil_salta_fin_de_semana():
    cal = Calendario([])
    assert cal.anterior_habil(date(2026, 12, 13)) == date(2026, 12, 11)  # domingo → viernes (P4)


def test_dia_habil_n_del_mes_considera_feriados():
    cal = Calendario(FERIADOS_2026)
    # Diciembre 2026: 1 mar, 2 mié, 3 jue, 4 vie, 7 lun, (8 feriado), 9 mié, 10 jue
    assert cal.dia_habil_n(2026, 12, 1) == date(2026, 12, 1)
    assert cal.dia_habil_n(2026, 12, 4) == date(2026, 12, 4)
    assert cal.dia_habil_n(2026, 12, 5) == date(2026, 12, 7)
    assert cal.dia_habil_n(2026, 12, 6) == date(2026, 12, 9)
    assert cal.dia_habil_n(2026, 12, 7) == date(2026, 12, 10)


def test_dia_habil_n_fuera_del_mes_es_error():
    cal = Calendario([])
    with pytest.raises(ValueError):
        cal.dia_habil_n(2026, 12, 40)


def test_dias_habiles_restantes_hasta_el_d10_descuentan_el_feriado():
    """Corrige la maqueta: el 04-12-2026 faltan 3 días hábiles para el D10 (7, 9 y 10), no 4."""
    cal = Calendario(FERIADOS_2026)
    assert cal.dias_habiles_entre(date(2026, 12, 4), date(2026, 12, 10)) == 3
    assert cal.dias_habiles_entre(date(2026, 12, 4), date(2026, 12, 7)) == 1


def test_dias_habiles_entre_misma_fecha_es_cero():
    cal = Calendario([])
    assert cal.dias_habiles_entre(date(2026, 12, 4), date(2026, 12, 4)) == 0


# ---- Los días 8, 9 y 10 del cierre (Karla, 01-11-2026) ---------------------------------------


def entregas(cal, anio, mes, minimo=1):
    h = hitos_de_entrega(cal, anio, mes, minimo)
    return h[8], h[9], h[10]


def test_si_los_dias_8_9_y_10_son_habiles_no_se_mueven():
    # Marzo de 2027: lunes 8, martes 9 y miércoles 10.
    assert entregas(Calendario([]), 2027, 3) == (date(2027, 3, 8), date(2027, 3, 9), date(2027, 3, 10))


def test_noviembre_2026_el_8_es_domingo_y_todo_se_corre_al_habil_siguiente():
    # 08-11 domingo → lunes 09 (reportes listos en la tarde); el 9 es lunes pero ya está ocupado por el paso anterior → martes 10; el 10 → miércoles 11.
    assert entregas(Calendario([]), 2026, 11) == (date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11))


def test_diciembre_2026_el_8_es_feriado():
    assert entregas(Calendario(FERIADOS_2026), 2026, 12) == (date(2026, 12, 9), date(2026, 12, 10), date(2026, 12, 11))


def test_el_9_y_el_10_en_fin_de_semana_pasan_al_lunes_y_al_martes():
    # Enero 2027: el 8 es viernes, el 9 sábado y el 10 domingo.
    assert entregas(Calendario([]), 2027, 1) == (date(2027, 1, 8), date(2027, 1, 11), date(2027, 1, 12))


def test_el_minimo_de_dias_entre_pasos_es_un_parametro():
    assert entregas(Calendario([]), 2026, 11, minimo=0) == (date(2026, 11, 9), date(2026, 11, 9), date(2026, 11, 10))
    assert entregas(Calendario([]), 2027, 3, minimo=2) == (date(2027, 3, 8), date(2027, 3, 10), date(2027, 3, 12))


def test_los_tres_pasos_nunca_caen_el_mismo_dia_ni_en_dia_inhabil():
    cal = Calendario(FERIADOS_2026)
    for anio in (2026, 2027, 2028):
        for mes in range(1, 13):
            d8, d9, d10 = entregas(cal, anio, mes)
            assert d8 < d9 < d10 and all(cal.es_habil(d) for d in (d8, d9, d10))


def test_la_semana_del_cierre_va_del_primer_habil_al_dia_8():
    assert ventana_del_cierre(Calendario([]), 2026, 11) == (date(2026, 11, 2), date(2026, 11, 9))
    assert ventana_del_cierre(Calendario(FERIADOS_2026), 2026, 12) == (date(2026, 12, 1), date(2026, 12, 9))


def test_la_jornada_es_de_9_horas_de_lunes_a_jueves_y_5_el_viernes():
    assert [JORNADA_HORAS[d] for d in range(5)] == [9, 9, 9, 9, 5] and sum(JORNADA_HORAS.values()) == 41


def test_sumar_dias_habiles_salta_fines_de_semana_y_feriados():
    cal = Calendario(FERIADOS_2026)
    assert cal.sumar_dias_habiles(date(2026, 12, 7), 1) == date(2026, 12, 9)  # el martes 08 es feriado
    assert cal.sumar_dias_habiles(date(2026, 12, 4), 1) == date(2026, 12, 7)  # viernes → lunes
    assert cal.sumar_dias_habiles(date(2026, 12, 4), 0) == date(2026, 12, 4)
