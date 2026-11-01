"""La semana del cierre (del primer día hábil al día 8): lo que se pausa o lo que hace otro cargo, y los días hábiles que pasan del día 8."""
from datetime import date

import pytest

from nucleo.models import Ocurrencia
from nucleo.servicios import periodos
from nucleo.servicios.calendario import Calendario
from nucleo.servicios.recurrencia import Regla, fechas_limite
from pruebas.ayudas import anio_abierto, cargo, persona, tarea

pytestmark = pytest.mark.django_db


@pytest.fixture
def equipo():
    cont, asist, jefa = cargo("Contador Senior"), cargo("Asistente Contable"), cargo("Jefa de Control")
    return {"cont": cont, "asist": asist, "jefa": jefa, "p_cont": persona("Contador", cont), "p_asist": persona("Asistente", asist), "p_jefa": persona("Jefa", jefa)}


def abrir(anio=2026, mes=12):
    anio_abierto()
    return periodos.abrir_mes(anio, mes, usuario=None)


def test_una_tarea_pausada_no_se_genera_en_la_semana_del_cierre_y_sigue_despues(equipo):
    t = tarea("OP-1", equipo["cont"], "DIARIA_HABIL")
    t.modo_cierre = "pausar"
    t.save()
    res = abrir()
    fechas = list(Ocurrencia.objects.filter(tarea=t).values_list("fecha_limite", flat=True))
    # diciembre de 2026: la semana del cierre va del 01-12 al 09-12 (el 08 es feriado y el día 8 pasa al 09)
    assert min(fechas) == date(2026, 12, 10) and date(2026, 12, 9) not in fechas and date(2026, 12, 1) not in fechas
    assert res.pausadas == 6  # 1, 2, 3, 4, 7 y 9 de diciembre


def test_una_tarea_reasignada_la_hace_otro_cargo_solo_en_la_semana_del_cierre(equipo):
    t = tarea("OP-2", equipo["cont"], "DIARIA_HABIL", revisa=equipo["jefa"])
    t.modo_cierre, t.cargo_cierre, t.cargo_revisa_cierre = "reasignar", equipo["asist"], equipo["cont"]  # la analista la hace; el contador solo revisa
    t.save()
    res = abrir()
    en_semana = Ocurrencia.objects.get(tarea=t, fecha_limite=date(2026, 12, 3))
    assert (en_semana.cargo_ejecuta, en_semana.colaborador, en_semana.cargo_revisa) == (equipo["asist"], equipo["p_asist"], equipo["cont"])
    despues = Ocurrencia.objects.get(tarea=t, fecha_limite=date(2026, 12, 10))
    assert (despues.cargo_ejecuta, despues.colaborador, despues.cargo_revisa) == (equipo["cont"], equipo["p_cont"], equipo["jefa"])
    assert res.reasignadas == 6 and res.pausadas == 0


def test_sin_modo_la_tarea_se_genera_todos_los_dias_como_siempre(equipo):
    t = tarea("OP-3", equipo["cont"], "DIARIA_HABIL")
    abrir()
    assert Ocurrencia.objects.filter(tarea=t, fecha_limite=date(2026, 12, 1)).exists()


def test_reasignar_sin_cargo_alternativo_la_deja_igual(equipo):
    t = tarea("OP-4", equipo["cont"], "DIARIA_HABIL")
    t.modo_cierre = "reasignar"
    t.save()
    abrir()
    assert Ocurrencia.objects.get(tarea=t, fecha_limite=date(2026, 12, 3)).cargo_ejecuta == equipo["cont"]


def test_la_vista_previa_informa_lo_pausado_y_lo_reasignado(equipo):
    t = tarea("OP-5", equipo["cont"], "DIARIA_HABIL")
    t.modo_cierre = "pausar"
    t.save()
    anio_abierto()
    vp = periodos.vista_previa(2026, 12)
    assert len(vp.pausadas) == 6 and not any(i.tarea == t and i.fecha <= date(2026, 12, 9) for i in vp.ocurrencias)


# ---- Los días hábiles que pasan del día 8 vencen el día 8 -----------------------------------------------------------------


def test_un_dia_habil_posterior_al_dia_8_vence_el_dia_8():
    cal = Calendario([])
    # Enero de 2027 (con el 1 feriado): días hábiles 4, 5, 6, 7, 8 (viernes 8), 11, 12… El día 8 es el 5.º hábil: el 6.º y el 7.º vencerían el 11 y el 12.
    cal = Calendario([date(2027, 1, 1)])
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=5), 2027, 1, cal) == [date(2027, 1, 8)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=6), 2027, 1, cal) == [date(2027, 1, 8)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=7), 2027, 1, cal) == [date(2027, 1, 8)]


def test_si_el_dia_habil_cae_antes_del_dia_8_no_se_mueve():
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=3), 2027, 3, Calendario([])) == [date(2027, 3, 3)]
