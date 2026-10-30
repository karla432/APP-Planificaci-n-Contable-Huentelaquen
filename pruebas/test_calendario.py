"""Días hábiles, feriados y los hitos D7/D10 (DEC-05 y P2 de Karla, 30-10-2026).

Los feriados que se usan aquí son datos de prueba: en la aplicación solo cuentan los feriados confirmados.
"""
from datetime import date

import pytest

from nucleo.servicios.calendario import Calendario, hitos_de_cierre

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


# ---- Hitos D7 y D10 -------------------------------------------------------------------------


def test_d7_y_d10_en_dias_habiles_no_se_mueven():
    cal = Calendario(FERIADOS_2026)
    # Diciembre 2026: 7 es lunes, 10 es jueves. El 08 (feriado) queda entre ambos.
    assert hitos_de_cierre(cal, 2026, 12) == (date(2026, 12, 7), date(2026, 12, 10))


def test_d7_en_sabado_pasa_al_lunes_9_como_dijo_karla():
    cal = Calendario([])
    # Noviembre 2026: 7 es sábado; 10 es martes.
    assert hitos_de_cierre(cal, 2026, 11) == (date(2026, 11, 9), date(2026, 11, 10))


def test_d7_en_domingo_pasa_al_lunes_8():
    cal = Calendario([])
    d7, _ = hitos_de_cierre(cal, 2025, 12)  # 07-12-2025 es domingo
    assert d7 == date(2025, 12, 8)


def test_d10_en_fin_de_semana_pasa_al_lunes():
    cal = Calendario([])
    # 10-01-2026 es sábado; 07-01-2026 es miércoles.
    assert hitos_de_cierre(cal, 2026, 1) == (date(2026, 1, 7), date(2026, 1, 12))


def test_d7_en_viernes_feriado_choca_con_d10_y_el_d10_pasa_al_dia_habil_siguiente():
    """P2 (aprobada por Karla): si D10 ≤ D7 corrido, el D10 pasa al día hábil siguiente al D7."""
    # Se fabrica el caso: 07-08-2026 es viernes; si es feriado, D7 pasa al lunes 10 y choca con el D10 (lunes 10).
    cal = Calendario([date(2026, 8, 7)])
    d7, d10 = hitos_de_cierre(cal, 2026, 8)
    assert d7 == date(2026, 8, 10)
    assert d10 == date(2026, 8, 11)


def test_d7_y_d10_nunca_son_el_mismo_dia():
    cal = Calendario([])
    for mes in range(1, 13):
        d7, d10 = hitos_de_cierre(cal, 2026, mes)
        assert d7 < d10
