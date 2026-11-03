"""Las semanas del cierre (de DH01 a DH10): lo que se pausa o lo que hace otro cargo, y los días hábiles que pasan del 8 (ya no se topan: DH11 a DH15 existen)."""
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
    # diciembre de 2026: las semanas del cierre van de DH01 (01-12) a DH10 (15-12); el 08 es feriado
    assert min(fechas) == date(2026, 12, 16) and date(2026, 12, 15) not in fechas and date(2026, 12, 1) not in fechas
    assert res.pausadas == 10  # 1, 2, 3, 4, 7, 9, 10, 11, 14 y 15 de diciembre


def test_una_tarea_reasignada_la_hace_otro_cargo_solo_en_la_semana_del_cierre(equipo):
    t = tarea("OP-2", equipo["cont"], "DIARIA_HABIL", revisa=equipo["jefa"])
    t.modo_cierre, t.cargo_cierre, t.cargo_revisa_cierre = "reasignar", equipo["asist"], equipo["cont"]  # la analista la hace; el contador solo revisa
    t.save()
    res = abrir()
    en_semana = Ocurrencia.objects.get(tarea=t, fecha_limite=date(2026, 12, 3))
    assert (en_semana.cargo_ejecuta, en_semana.colaborador, en_semana.cargo_revisa) == (equipo["asist"], equipo["p_asist"], equipo["cont"])
    despues = Ocurrencia.objects.get(tarea=t, fecha_limite=date(2026, 12, 16))
    assert (despues.cargo_ejecuta, despues.colaborador, despues.cargo_revisa) == (equipo["cont"], equipo["p_cont"], equipo["jefa"])
    assert res.reasignadas == 10 and res.pausadas == 0


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
    assert len(vp.pausadas) == 10 and not any(i.tarea == t and i.fecha <= date(2026, 12, 15) for i in vp.ocurrencias)


# ---- Los días hábiles pasan del 8 sin toparse (DH00 a DH15) ---------------------------------------------------------------


def test_los_dias_habiles_posteriores_al_8_ya_no_se_topan():
    # Enero de 2027 (con el 1 feriado): hábiles 4, 5, 6, 7, 8 (viernes), 11, 12, 13… El DH06 es el lunes 11 y el DH07 el martes 12.
    cal = Calendario([date(2027, 1, 1)])
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=5), 2027, 1, cal) == [date(2027, 1, 8)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=6), 2027, 1, cal) == [date(2027, 1, 11)]
    assert fechas_limite(Regla("CIERRE_DIA_HABIL", n=7), 2027, 1, cal) == [date(2027, 1, 12)]
