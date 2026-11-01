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


def test_una_tarea_del_cierre_con_demasiada_carga_se_reparte_ocupando_los_dias_desde_el_1(equipo):
    for i in range(3):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=1)  # 15 h el día 1 (caben 9)
    prop = matriz.proponer(2026, 12)
    j = fila(prop.despues, "Jefa de Control")
    assert prop.antes.exceso_total > 0 and prop.despues.exceso_total == pytest.approx(0)
    assert [prop.planes[t.pk].regla_n for t in Tarea.objects.order_by("codigo")] == [1, 2, 3]  # una por día, desde el día 1 y en el orden de la lista
    assert all(h <= 9 + 1e-9 for h in j.horas.values()) and sum(j.horas.values()) == pytest.approx(15) and not prop.sin_solucion


def test_las_tareas_se_ocupan_de_menor_a_mayor_desde_el_dia_1_aunque_el_excel_las_ponga_mas_tarde(equipo):
    for i in range(4):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=3, proceso=f"Proceso {i}")  # el Excel las deja todas el día hábil 3
    prop = matriz.proponer(2026, 12)
    dias = [prop.planes[t.pk].regla_n for t in Tarea.objects.order_by("proceso__orden")]
    assert dias == [1, 2, 3, 4]  # siguiendo el orden de los procesos: de menor a mayor
    assert max(dias) <= 5  # el último día de proceso de diciembre de 2026 es el 07-12 (día hábil 5); el día 8 se entrega el 09-12


def test_el_analisis_de_cuentas_va_el_ultimo_dia_de_proceso_repartido_entre_contador_jefa_y_asistente(equipo):
    for i in range(6):
        hacer(f"A{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 2, n=5, proceso="Análisis de cuentas")  # 12 h que hoy hace solo la Jefa
    prop = matriz.proponer(2026, 12)
    planes = [prop.planes[t.pk] for t in Tarea.objects.all()]
    assert {p.regla_n for p in planes} == {5}  # el último día de proceso: lunes 07-12 (día hábil 5)
    assert {p.ejecuta_id for p in planes} <= {equipo["Jefa de Control"].pk, equipo["Contador Senior"].pk, equipo["Asistente Contable"].pk} and len({p.ejecuta_id for p in planes}) == 3
    assert prop.despues.exceso_total == pytest.approx(0) and any("en paralelo" in c.motivo for c in prop.cambios)


def test_el_costo_en_destino_es_lo_ultimo_que_se_procesa_y_el_primero_de_la_lista_queda_mas_temprano(equipo):
    for i in range(3):
        t = hacer(f"G{i}", equipo["Gerente AyF"], "CIERRE_DIA_HABIL", 5, n=3, proceso="Costeo y producción")
        t.tarea_principal = "Costo en destino de áreas de trabajo"
        t.save()
    prop = matriz.proponer(2026, 12)
    dias = [prop.planes[t.pk].regla_n for t in Tarea.objects.order_by("secuencia", "codigo")]
    assert dias == sorted(dias) and dias[-1] == 5  # termina el último día de proceso
    assert all(h <= 9 + 1e-9 for h in fila(prop.despues, "Gerente AyF").horas.values())


def test_el_paquete_de_reportes_lo_prepara_el_gerente_el_dia_8_en_maximo_3_horas(equipo):
    for i, h in enumerate((1.5, 1.5, 1.0)):  # 4 h hoy
        hacer(f"R{i}", equipo["Gerente AyF"], "CIERRE_HITO", h, n=8, proceso="Reportería día 7")
    prop = matriz.proponer(2026, 12)
    minutos = [prop.planes[t.pk].minutos for t in Tarea.objects.all()]
    assert sum(minutos) == 180 and all(prop.planes[t.pk].regla_tipo == "CIERRE_HITO" and prop.planes[t.pk].regla_n == 8 for t in Tarea.objects.all())
    assert fila(prop.despues, "Gerente AyF").horas[date(2026, 12, 9)] == pytest.approx(3.0)  # el día 8 (09-12)
    assert any(c.campo == "Horas por ejecución" for c in prop.cambios)


def test_si_el_paquete_ya_dura_3_horas_o_menos_no_se_toca(equipo):
    hacer("R0", equipo["Gerente AyF"], "CIERRE_HITO", 2, n=8, proceso="Reportería día 7")
    assert matriz.proponer(2026, 12).planes[Tarea.objects.get().pk].minutos is None


def test_la_revision_del_9_y_el_cierre_del_10_no_se_mueven(equipo):
    hacer("V", equipo["Gerente AyF"], "CIERRE_HITO", 1, n=9, proceso="Revisión día 9")
    hacer("Z", equipo["Contador Senior"], "CIERRE_HITO", 3, n=10, proceso="Cierre día 10")
    prop = matriz.proponer(2026, 12)
    assert [(p.regla_tipo, p.regla_n) for p in (prop.planes[t.pk] for t in Tarea.objects.order_by("codigo"))] == [("CIERRE_HITO", 9), ("CIERRE_HITO", 10)]


def test_lo_que_va_el_9_o_el_10_no_se_mueve_aunque_sea_de_un_proceso_normal(equipo):
    hacer("C", equipo["Jefa de Control"], "CIERRE_HITO", 1.5, n=9, proceso="Costeo y producción")
    plan = matriz.proponer(2026, 12).planes[Tarea.objects.get().pk]
    assert (plan.regla_tipo, plan.regla_n) == ("CIERRE_HITO", 9)


def test_los_dias_8_9_y_10_que_eran_tareas_de_proceso_se_adelantan_a_la_semana_del_cierre(equipo):
    hacer("C", equipo["Jefa de Control"], "CIERRE_HITO", 2, n=8, proceso="Créditos y leasing")  # un reporte que hoy espera al día 8
    prop = matriz.proponer(2026, 12)
    plan = prop.planes[Tarea.objects.get().pk]
    assert (plan.regla_tipo, plan.regla_n) == ("CIERRE_DIA_HABIL", 1)  # se hace desde el primer día y deja libre el día 8 para el paquete


def test_la_propuesta_sube_las_tareas_del_cierre_que_caben_en_la_jornada(equipo):
    for i in range(4):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 5, n=3, proceso=f"Proceso {i}")
    prop = matriz.proponer(2026, 12)
    assert prop.antes.cumplimiento_esperado_pct < prop.despues.cumplimiento_esperado_pct == 100.0


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


def test_la_propuesta_acerca_la_ocupacion_entre_los_cargos(equipo):
    for i in range(5):
        hacer(f"J{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 4, n=3, proceso="Costeo")  # 20 h de la Jefa (el día hábil 3 caben 9)
    hacer("A", equipo["Asistente Contable"], "CIERRE_DIA_HABIL", 1, n=5, proceso="Costeo")  # la Asistente ya trabaja en Costeo y está libre
    prop = matriz.proponer(2026, 12)
    assert prop.despues.desequilibrio_pct < prop.antes.desequilibrio_pct
    assert fila(prop.despues, "Asistente Contable").horas_semana_cierre > fila(prop.antes, "Asistente Contable").horas_semana_cierre
    assert prop.despues.exceso_total <= prop.antes.exceso_total + 1e-9


def test_el_tope_de_80_horas_del_gerente_no_se_rompe_al_repartir(equipo):
    hacer("G0", equipo["Gerente AyF"], "CIERRE_DIA_HABIL", 2, n=1, proceso="Costeo")
    for i in range(6):
        hacer(f"J{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 12, n=3, proceso="Costeo")  # mucha carga que podría irse al Gerente
    prop = matriz.proponer(2026, 12)
    assert fila(prop.despues, "Gerente AyF").total_mes <= 80 + 1e-9


def test_el_diagnostico_dice_si_cabe_cuanto_falta_y_donde_se_van_las_horas(equipo):
    for i in range(20):
        hacer(f"C{i}", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 9, n=1, proceso="Costeo y producción")  # 180 h para una sola persona
    hacer("O", equipo["Contador Senior"], "DIARIA_HABIL", 9, proceso="Compras")  # la Asistente cubrirá esto
    diag = " ".join(matriz.diagnostico(matriz.proponer(2026, 12)))
    assert "Faltan" in diag and "no cabe" in diag and "95 %" in diag and "Asistente Contable" in diag and "Costeo y producción" in diag and "más exigido" in diag


def test_si_todo_cabe_el_diagnostico_lo_dice(equipo):
    hacer("C0", equipo["Jefa de Control"], "CIERRE_DIA_HABIL", 2, n=1)
    assert "En total el trabajo cabe" in " ".join(matriz.diagnostico(matriz.proponer(2026, 12)))
