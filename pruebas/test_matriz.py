"""Matriz del cierre y propuesta de equilibrio (Karla, 01-11-2026): jornada 9/5 h, tope del Gerente, semana del cierre y reparto del equipo."""
from datetime import date

import pytest

from nucleo.models import Cargo, Tarea
from nucleo.servicios import matriz
from pruebas.ayudas import anio_abierto, cargo, tarea

pytestmark = pytest.mark.django_db
# Diciembre de 2026 (08 y 25 feriados): semana del cierre = 1, 2, 3, 4, 7 y 9 de diciembre; el día 9 es el 10 y el día 10 el 11.
LUN, MAR, MIE, JUE, VIE = date(2026, 12, 7), date(2026, 12, 1), date(2026, 12, 2), date(2026, 12, 3), date(2026, 12, 4)


@pytest.fixture
def equipo():
    anio_abierto()
    nombres = (("Gerente AyF", 1), ("Jefa de Control", 2), ("Contador Senior", 3), ("Asistente Contable", 4))
    c = {n: cargo(n) for n, _ in nombres}
    for n, orden in nombres:
        Cargo.objects.filter(nombre=n).update(orden=orden)
    Cargo.objects.filter(nombre="Gerente AyF").update(horas_mes_max=80)
    return c


def hacer(codigo, cargo_, tipo, horas, revisa=None, proceso="Proceso A", **regla):
    t = tarea(codigo, cargo_, tipo, revisa=revisa, proceso_nombre=proceso, **regla)
    t.minutos_estimados = round(horas * 60)
    t.save()
    return t


def fila(m, nombre):
    return next(f for f in m.filas if f.cargo.nombre == nombre)


# ---- La matriz ---------------------------------------------------------------------------------------------------------------


def test_la_jornada_es_9_horas_de_lunes_a_jueves_y_5_el_viernes_y_el_feriado_no_cuenta(equipo):
    m = matriz.construir(2026, 12)
    j = fila(m, "Jefa de Control")
    assert j.capacidad[MAR] == 9 and j.capacidad[JUE] == 9 and j.capacidad[VIE] == 5 and j.capacidad[date(2026, 12, 11)] == 5
    assert date(2026, 12, 8) not in j.capacidad  # el feriado no es un día de la matriz
    assert [f.cargo.nombre for f in m.filas] == ["Gerente AyF", "Jefa de Control", "Contador Senior", "Asistente Contable"]  # en el orden de los cargos


def test_la_matriz_suma_las_horas_de_cada_persona_por_dia_y_la_revision_al_25_por_ciento(equipo):
    hacer("T1", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 4, revisa=equipo["Gerente AyF"], n=3)  # jueves 03-12
    hacer("T2", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 2, n=3)
    m = matriz.construir(2026, 12)
    assert fila(m, "Jefa de Control").horas[JUE] == pytest.approx(6.0)
    assert fila(m, "Gerente AyF").horas[JUE] == pytest.approx(1.0)  # revisa el 25 % de 4 h
    assert [i.tipo for i in fila(m, "Gerente AyF").items[JUE]] == ["revisión"]


def test_un_dia_con_mas_horas_que_la_jornada_es_una_alerta(equipo):
    hacer("T1", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 7, n=4)  # viernes: caben 5 h
    hacer("T2", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 3, n=4)
    m = matriz.construir(2026, 12)
    j = fila(m, "Jefa de Control")
    assert j.exceso(VIE) == pytest.approx(5.0) and j.sobrecargados() == [VIE]
    assert any("Jefa de Control" in a and "04-12" in a and "caben 5 h" in a for a in m.alertas())


def test_las_tareas_sin_horas_se_avisan_y_no_se_inventan(equipo):
    tarea("T9", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", n=2)
    m = matriz.construir(2026, 12)
    assert len(m.sin_horas) == 1 and fila(m, "Jefa de Control").horas[MIE] == 0 and any("sin horas" in a or "no tienen horas" in a for a in m.alertas())


def test_el_gerente_no_puede_pasar_de_80_horas_al_mes(equipo):
    hacer("T1", equipo["Gerente AyF"], "DIARIA_HABIL", 4.5)  # 4,5 h × 21 días = 94,5 h
    m = matriz.construir(2026, 12)
    g = fila(m, "Gerente AyF")
    assert g.tope_mes == 80 and g.pasa_el_tope and any("sobre su tope de 80 h" in a for a in m.alertas())


def test_lo_pausado_y_lo_reasignado_en_la_semana_del_cierre_cambia_la_matriz(equipo):
    t = hacer("T1", equipo["Contador Senior"], "DIARIA_HABIL", 2)
    t.modo_cierre, t.cargo_cierre, t.cargo_revisa_cierre = "reasignar", equipo["Asistente Contable"], equipo["Contador Senior"]
    t.save()
    m = matriz.construir(2026, 12)
    assert fila(m, "Contador Senior").horas[JUE] == pytest.approx(0.5)  # solo revisa (25 % de 2 h)
    assert fila(m, "Asistente Contable").horas[JUE] == pytest.approx(2.0)
    t.modo_cierre = "pausar"
    t.save()
    m = matriz.construir(2026, 12)
    assert fila(m, "Contador Senior").horas[JUE] == 0 and fila(m, "Asistente Contable").horas[JUE] == 0
    assert fila(m, "Contador Senior").horas[date(2026, 12, 10)] == pytest.approx(2.0)  # el día 10 se retoma


def test_ocupacion_y_equilibrio_de_la_semana_del_cierre(equipo):
    hacer("T1", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=1)
    m = matriz.construir(2026, 12)
    j = fila(m, "Jefa de Control")
    assert j.horas_semana_cierre == 5 and j.capacidad_semana_cierre == 9 + 9 + 9 + 5 + 9 + 9 and m.desequilibrio_pct == j.ocupacion_pct > 0


# ---- La propuesta --------------------------------------------------------------------------------------------------------------


def test_la_propuesta_no_cambia_la_planificacion_guardada(equipo):
    hacer("T1", equipo["Contador Senior"], "DIARIA_HABIL", 2, proceso="Compras")
    antes = list(Tarea.objects.values_list("pk", "cargo_ejecuta_id", "modo_cierre", "regla_n"))
    matriz.proponer(2026, 12)
    assert list(Tarea.objects.values_list("pk", "cargo_ejecuta_id", "modo_cierre", "regla_n")) == antes


def test_la_analista_cubre_compras_y_pagos_y_el_contador_solo_revisa(equipo):
    c = hacer("T1", equipo["Contador Senior"], "DIARIA_HABIL", 2, revisa=equipo["Jefa de Control"], proceso="Compras")
    p = hacer("T2", equipo["Jefa de Control"], "SEMANAL", 1, proceso="Pagos Banco Estado", dia_semana=1)
    prop = matriz.proponer(2026, 12)
    for t in (c, p):
        plan = prop.planes[t.pk]
        assert (plan.modo_cierre, plan.cargo_cierre_id, plan.revisa_cierre_id) == ("reasignar", equipo["Asistente Contable"].pk, equipo["Contador Senior"].pk)
    assert fila(prop.despues, "Contador Senior").horas[JUE] == pytest.approx(0.5)  # solo revisa
    assert fila(prop.despues, "Asistente Contable").horas[JUE] == pytest.approx(2.0)


def test_lo_demas_de_operacion_de_los_tres_enfocados_se_pausa_y_lo_de_la_analista_sigue(equipo):
    otro = hacer("T1", equipo["Jefa de Control"], "SEMANAL", 3, proceso="Seguimiento", dia_semana=3)
    jefe = hacer("T2", equipo["Contador Senior"], "DIARIA_HABIL", 1, proceso="Seguimiento")
    suya = hacer("T3", equipo["Asistente Contable"], "DIARIA_HABIL", 1, proceso="Ventas")
    prop = matriz.proponer(2026, 12)
    assert prop.planes[otro.pk].modo_cierre == "pausar" and prop.planes[jefe.pk].modo_cierre == "pausar"
    assert prop.planes[suya.pk].modo_cierre == "igual"  # la analista da continuidad a su propio trabajo


def test_lo_que_karla_ya_definio_a_mano_no_se_pisa(equipo):
    t = hacer("T1", equipo["Contador Senior"], "DIARIA_HABIL", 2, proceso="Compras")
    t.modo_cierre = "pausar"
    t.save()
    assert matriz.proponer(2026, 12).planes[t.pk].modo_cierre == "pausar"


def test_una_tarea_del_cierre_con_demasiada_carga_se_mueve_a_un_dia_con_espacio(equipo):
    for i in range(3):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=1)  # 15 h el día 1 (caben 9)
    prop = matriz.proponer(2026, 12)
    j = fila(prop.despues, "Jefa de Control")
    assert prop.antes.exceso_total > 0 and prop.despues.exceso_total == pytest.approx(0)
    assert j.horas[MAR] <= 9 + 1e-9 and sum(j.horas.values()) == pytest.approx(15)
    assert any(c.campo == "Día hábil del cierre" for c in prop.cambios) and not prop.sin_solucion


def test_una_tarea_nunca_se_mueve_antes_de_su_dia_ni_pasa_del_dia_8(equipo):
    for i in range(4):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=3)  # 20 h el día hábil 3
    prop = matriz.proponer(2026, 12)
    for t in Tarea.objects.all():
        n = prop.planes[t.pk].regla_n
        assert 3 <= n <= 6  # el día hábil 6 es el 09-12, el día 8 (reportes listos)


def test_se_reasigna_solo_a_quien_ya_trabaja_en_el_proceso_y_nunca_a_quien_la_revisa(equipo):
    for i in range(3):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, revisa=equipo["Gerente AyF"], n=1, proceso="Costeo")
    hacer("K", equipo["Contador Senior"], "CIERRE_DIA_HABIL", 1, n=5, proceso="Costeo")  # el Contador ya trabaja en Costeo
    hacer("L", equipo["Asistente Contable"], "CIERRE_DIA_HABIL", 1, n=5, proceso="Otro")
    prop = matriz.proponer(2026, 12)
    for t in Tarea.objects.filter(codigo__startswith="C"):
        plan = prop.planes[t.pk]
        assert plan.ejecuta_id in (equipo["Jefa de Control"].pk, equipo["Contador Senior"].pk)  # nunca la Asistente, que no trabaja en Costeo
        assert plan.ejecuta_id != plan.revisa_id  # y nunca el que revisa


def test_lo_que_no_cabe_se_informa_y_no_se_esconde(equipo):
    hacer("G", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 30, n=1)  # una sola tarea de 30 h: no cabe en ningún día
    prop = matriz.proponer(2026, 12)
    assert prop.sin_solucion and prop.sin_solucion[0][0].nombre == "Jefa de Control" and prop.despues.exceso_total > 0
    assert any("Jefa de Control" in a for a in prop.despues.alertas())


def test_la_propuesta_no_empeora_nada(equipo):
    hacer("A", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 8, n=1)
    hacer("B", equipo["Contador Senior"], "CIERRE_DIA_HABIL", 8, n=1)
    prop = matriz.proponer(2026, 12)
    assert prop.despues.exceso_total <= prop.antes.exceso_total + 1e-9
