"""Motor de recurrencia: de una regla y un período a las fechas límite (docs/f1/02_modelo_datos_recurrencia.md)."""
from datetime import date

import pytest

from nucleo.servicios.calendario import Calendario
from nucleo.servicios.recurrencia import Regla, ReglaIncompleta, ReglaInvalida, fechas_limite

SIN_FERIADOS = Calendario([])
DIC_2026 = Calendario([date(2026, 12, 8), date(2026, 12, 25)])


def test_diaria_habil_noviembre_2026_son_21_dias():
    # Noviembre 2026 empieza en domingo: 2–6, 9–13, 16–20, 23–27 y 30.
    fechas = fechas_limite(Regla("DIARIA_HABIL"), 2026, 11, SIN_FERIADOS)
    assert len(fechas) == 21
    assert fechas[0] == date(2026, 11, 2) and fechas[-1] == date(2026, 11, 30)


def test_inicio_de_medicion_descarta_lo_anterior_p7():
    fechas = fechas_limite(Regla("DIARIA_HABIL"), 2026, 11, SIN_FERIADOS, inicio_medicion=date(2026, 11, 5))
    assert fechas[0] == date(2026, 11, 5)
    assert len(fechas) == 18


def test_diaria_no_genera_en_feriados_ni_fines_de_semana():
    fechas = fechas_limite(Regla("DIARIA_HABIL"), 2026, 12, DIC_2026)
    assert date(2026, 12, 8) not in fechas and date(2026, 12, 5) not in fechas


def test_semanal_lunes_noviembre_2026():
    fechas = fechas_limite(Regla("SEMANAL", dia_semana=0), 2026, 11, SIN_FERIADOS)
    assert fechas == [date(2026, 11, d) for d in (2, 9, 16, 23, 30)]


def test_semanal_en_feriado_pasa_al_siguiente_habil():
    cal = Calendario([date(2026, 11, 9)])  # lunes feriado
    fechas = fechas_limite(Regla("SEMANAL", dia_semana=0), 2026, 11, cal)
    assert date(2026, 11, 10) in fechas and date(2026, 11, 9) not in fechas


def test_semanal_viernes_feriado_pasa_al_lunes():
    cal = Calendario([date(2026, 11, 13)])
    fechas = fechas_limite(Regla("SEMANAL", dia_semana=4), 2026, 11, cal)
    assert fechas == [date(2026, 11, 6), date(2026, 11, 16), date(2026, 11, 20), date(2026, 11, 27)]


@pytest.mark.parametrize("n,esperada", [(1, date(2026, 12, 1)), (2, date(2026, 12, 2)), (3, date(2026, 12, 3)), (4, date(2026, 12, 4))])
def test_cierre_dia_habil_n(n, esperada):
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=n), 2026, 12, DIC_2026) == [esperada]


def test_cierre_hito_dias_habiles_8_9_y_10_diciembre_2026():
    # DH08, DH09 y DH10 son días hábiles (03-11-2026). Con el 08 y el 25 de diciembre feriados: viernes 11, lunes 14 y martes 15.
    assert fechas_limite(Regla("CIERRE_HITO", n=8), 2026, 12, DIC_2026) == [date(2026, 12, 11)]
    assert fechas_limite(Regla("CIERRE_HITO", n=9), 2026, 12, DIC_2026) == [date(2026, 12, 14)]
    assert fechas_limite(Regla("CIERRE_HITO", n=10), 2026, 12, DIC_2026) == [date(2026, 12, 15)]


def test_cierre_hito_noviembre_2026_es_el_11_12_y_13():
    assert [fechas_limite(Regla("CIERRE_HITO", n=n), 2026, 11, SIN_FERIADOS)[0] for n in (8, 9, 10)] == [date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13)]


def test_cierre_dia_habil_acepta_del_dh00_al_dh15_sin_toparse_en_el_8():
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=0), 2026, 11, SIN_FERIADOS) == [date(2026, 10, 30)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=13), 2026, 11, SIN_FERIADOS) == [date(2026, 11, 18)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=15), 2026, 11, SIN_FERIADOS) == [date(2026, 11, 20)]


def test_cierre_hito_solo_acepta_8_9_o_10():
    for n in (7, 11):
        with pytest.raises(ReglaInvalida):
            fechas_limite(Regla("CIERRE_HITO", n=n), 2026, 12, DIC_2026)


def test_dia_13_en_domingo_va_al_viernes_anterior_p4():
    regla = Regla("DIA_FIJO", dia=13, ajuste="anterior")
    assert fechas_limite(regla, 2026, 12, DIC_2026) == [date(2026, 12, 11)]


def test_dia_13_en_dia_habil_no_se_mueve():
    regla = Regla("DIA_FIJO", dia=13, ajuste="anterior")
    assert fechas_limite(regla, 2026, 11, SIN_FERIADOS) == [date(2026, 11, 13)]


def test_dia_fijo_con_ajuste_siguiente():
    regla = Regla("DIA_FIJO", dia=13, ajuste="siguiente")
    assert fechas_limite(regla, 2026, 12, DIC_2026) == [date(2026, 12, 14)]


def test_meses_especificos_solo_genera_en_esos_meses():
    regla = Regla("MESES", meses=(4, 6, 9, 11), dia=20, ajuste="siguiente")
    assert fechas_limite(regla, 2026, 11, SIN_FERIADOS) == [date(2026, 11, 20)]
    assert fechas_limite(regla, 2026, 12, SIN_FERIADOS) == []


def test_meses_especificos_sin_dia_es_regla_incompleta():
    regla = Regla("MESES", meses=(4, 6, 9, 11))
    with pytest.raises(ReglaIncompleta):
        fechas_limite(regla, 2026, 11, SIN_FERIADOS)


def test_meses_especificos_sin_dia_no_falla_en_un_mes_que_no_toca():
    # Si el mes no está en la lista no hay nada que calcular, así que no hay nada incompleto que reportar.
    regla = Regla("MESES", meses=(4, 6, 9, 11))
    assert fechas_limite(regla, 2026, 12, SIN_FERIADOS) == []


def test_evento_no_genera_fechas():
    assert fechas_limite(Regla("EVENTO"), 2026, 11, SIN_FERIADOS) == []


def test_semanal_sin_dia_de_la_semana_es_regla_incompleta():
    with pytest.raises(ReglaIncompleta):
        fechas_limite(Regla("SEMANAL"), 2026, 11, SIN_FERIADOS)


def test_tipo_desconocido_es_regla_invalida():
    with pytest.raises(ReglaInvalida):
        fechas_limite(Regla("QUINCENAL"), 2026, 11, SIN_FERIADOS)


def test_ajuste_desconocido_es_regla_invalida():
    with pytest.raises(ReglaInvalida):
        fechas_limite(Regla("DIA_FIJO", dia=13, ajuste="cercano"), 2026, 11, SIN_FERIADOS)


def test_inicio_de_medicion_tambien_filtra_el_cierre():
    regla = Regla("CIERRE_DIA_HABIL", n=1)
    assert fechas_limite(regla, 2026, 12, DIC_2026, inicio_medicion=date(2026, 12, 2)) == []


def test_fin_de_mes_en_dia_habil_no_se_mueve():
    assert fechas_limite(Regla("FIN_DE_MES", ajuste="anterior"), 2026, 11, SIN_FERIADOS) == [date(2026, 11, 30)]  # lunes


def test_fin_de_mes_en_dia_inhabil_va_al_habil_anterior():
    assert fechas_limite(Regla("FIN_DE_MES", ajuste="anterior"), 2026, 10, SIN_FERIADOS) == [date(2026, 10, 30)]  # el 31 es sábado
    assert fechas_limite(Regla("FIN_DE_MES", ajuste="siguiente"), 2026, 10, SIN_FERIADOS) == [date(2026, 11, 2)]
