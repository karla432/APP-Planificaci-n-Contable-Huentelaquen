"""Planificación 2.0 (Karla, 03-11-2026): el Excel de tres hojas se carga en la app y la matriz reproduce su tabla de carga."""
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from nucleo.models import Cargo, CambioDeCodigo, Proceso, Tarea
from nucleo.servicios import importador, matriz, plan2
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
DATOS = Path(settings.BASE_DIR) / "docs" / "datos"
EXCEL_ANTIGUO = DATOS / "Planificacion_Mensual_Huentelauquen_Revisada.xlsx"
PLAN2 = DATOS / "Planificacion_2.0_contabilidad.xlsx"


@pytest.fixture
def base():
    importador.aplicar(importador.previsualizar(EXCEL_ANTIGUO), usuario=None)


@pytest.fixture
def cargado(base):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    importador.aplicar(vp, usuario=None)
    return vp


# ---- La vista previa ---------------------------------------------------------------------------------------------------------


def test_el_archivo_se_reconoce_y_trae_las_206_tareas_de_las_hojas_diario_y_mensual(base):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert vp.total_filas == 206 and not vp.duplicadas and vp.cargos_nuevos == []
    assert len(vp.altas) == 19 and len(vp.cambios) == 187 and len(vp.bajas) == 8


def test_los_procesos_renombrados_y_nuevos_se_informan_con_su_numero(base):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert vp.renombres_procesos == {"Reportería día 7": "Preparación Reporteria", "Revisión día 9": "Entrega Reporteria Gcia", "Cierre día 10": "Entrega Reporteria Directorio"}
    assert vp.procesos_plan["Control del cierre"] == (0, "CTL") and vp.procesos_plan["Cierre contable general"] == (36, "CCG")
    assert vp.orden_desde == 0 and vp.orden_procesos[0] == "Control del cierre"


def test_las_tareas_con_codigo_de_otro_proceso_se_recodifican_y_no_se_duplican(base):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert {(t.codigo, f.proceso) for t, f in vp.movidas} == {("08-COM.01.002", "Cierre Compras"), ("10-HON.02.001", "Cierre Honorarios"), ("33-RPT.03.002", "Entrega Reporteria Gcia")}


def test_las_ocho_tareas_que_el_plan_ya_no_trae_se_desactivan_y_se_listan(base):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert sorted(t.codigo for t in vp.bajas) == ["21-REM.04.002", "21-REM.04.003", "27-CON.02.001", "30-CYP.02.006", "31-ACU.03.001", "35-CDF.01.001", "35-CDF.01.002", "35-CDF.01.003"]


def test_previsualizar_no_guarda_nada(base):
    antes = (Tarea.objects.count(), Proceso.objects.count())
    importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert (Tarea.objects.count(), Proceso.objects.count()) == antes and not Proceso.objects.filter(nombre="Control del cierre").exists()


# ---- Al aplicar ------------------------------------------------------------------------------------------------------------------


def test_al_aplicar_el_control_del_cierre_es_el_proceso_00_y_el_resto_conserva_su_numero(cargado):
    procesos = {p.codigo: p.nombre for p in Proceso.objects.all()}
    assert procesos["00-CTL"] == "Control del cierre" and procesos["01-SEG"] == "Seguimiento" and procesos["33-RPT"] == "Preparación Reporteria"
    assert procesos["34-RGG"] == "Entrega Reporteria Gcia" and procesos["35-CDF"] == "Entrega Reporteria Directorio" and procesos["36-CCG"] == "Cierre contable general"
    assert len(procesos) == 37 and Proceso.objects.get(sigla="CTL").orden == 0


def test_las_tareas_recodificadas_quedan_con_el_codigo_de_su_proceso_y_con_historial(cargado):
    t = Tarea.objects.get(subtarea__startswith="Revisar Ultimo Dia del Mes")
    assert t.codigo.startswith("17-CCO.") and t.proceso.nombre == "Cierre Compras"
    h = Tarea.objects.get(proceso__nombre="Cierre Honorarios", tarea_principal__startswith="Cuadratura libro de honorarios")
    assert h.codigo.startswith("11-CHO.")
    g = Tarea.objects.get(subtarea__startswith="Entregar el reporte financiero a la Gerencia")
    assert g.codigo.startswith("34-RGG.") and g.proceso.nombre == "Entrega Reporteria Gcia"
    assert CambioDeCodigo.objects.filter(codigo_anterior="08-COM.01.002", codigo_nuevo=t.codigo).exists()


def test_las_predecesoras_del_archivo_pasan_a_ser_vinculos_entre_tareas(cargado):
    assert Tarea.objects.filter(activa=True).count() == 206 and Tarea.objects.filter(predecesoras__isnull=False).distinct().count() == 133
    t = Tarea.objects.get(subtarea__startswith="Cotejar el RCV contra Odoo", proceso__nombre="Cierre Compras")
    assert {p.subtarea[:20] for p in t.predecesoras.all()} and all(p.activa for p in t.predecesoras.all())
    assert sum(t.predecesoras.count() for t in Tarea.objects.all()) == 224


def test_cada_tarea_guarda_lo_nuevo_del_plan(cargado):
    t = Tarea.objects.get(codigo="17-CCO.02.001")
    assert t.dh_inicio == 1 and t.regla_n == 2 and t.horas_dh == {"1": 0.8, "2": 1.2} and t.tipo_control == "Ejecución"
    assert "Reasignada" in t.cambio_plan and t.justificacion
    p = Tarea.objects.get(subtarea__startswith="Arqueo de Caja y excepciones")
    assert (p.modo_cierre, p.al_terminar_cierre) == ("pausar", "al_dia")
    assert Tarea.objects.filter(modo_cierre="fuera").count() == 9 and Tarea.objects.filter(modo_cierre="pausar").count() == 28


def test_las_diarias_de_lunes_a_jueves_guardan_las_horas_de_cada_dia(cargado):
    t = Tarea.objects.get(subtarea__startswith="Registrar pagos de clientes (Retail y Horeca)")
    assert t.regla_tipo == "DIARIA_HABIL" and t.horas_semana == {"0": 2.0, "1": 1.0, "2": 1.0, "3": 1.0}


def test_cargar_dos_veces_el_mismo_archivo_ya_no_cambia_nada(cargado):
    vp = importador.previsualizar(PLAN2, incluir_dia_9=False)
    assert not vp.altas and not vp.cambios and not vp.bajas and not vp.movidas


def test_lo_ya_definido_por_la_gerente_no_se_pisa_con_horas_originales(base):
    t = Tarea.objects.filter(fuente_horas="gerente").first()
    assert t is not None
    importador.aplicar(importador.previsualizar(PLAN2, incluir_dia_9=False), usuario=None)
    assert Tarea.objects.filter(fuente_horas="gerente").count() >= 1  # «Original» en el archivo no cambia la fuente de las horas


# ---- La matriz reproduce la tabla de carga del archivo ----------------------------------------------------------------------


def test_la_matriz_de_noviembre_2026_coincide_con_la_tabla_de_carga_del_archivo_dia_por_dia(base, monkeypatch):
    """Sin el ajuste de 9 a 10 minutos (decisión posterior de Karla), la matriz es idéntica a la tabla de su archivo."""
    monkeypatch.setattr(plan2, "MINUTOS_AJUSTADOS", {})
    importador.aplicar(importador.previsualizar(PLAN2, incluir_dia_9=False), usuario=None)
    anio_abierto(feriados=())
    wb = openpyxl.load_workbook(PLAN2, data_only=True)
    suya = {}
    for r in wb["Mensual"].iter_rows(min_row=185, max_row=210, values_only=True):
        if "Total (h)" in r:
            i = r.index("Total (h)")
            suya[r[i + 1]] = [float(v or 0) for v in r[i + 2:i + 13]]
        if "Cierre (h)" in r and r[r.index("Cierre (h)") + 1] == "Gerente AyF":
            i = r.index("Cierre (h)")
            suya["Gerente AyF"] = [float(v or 0) for v in r[i + 2:i + 13]]
    m = matriz.construir(2026, 11)
    assert [d.day for d in m.dias] == [30, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13]  # DH00 a DH10
    for fila in m.filas:
        if fila.cargo.nombre in suya:
            assert [round(fila.horas[d], 2) for d in m.dias] == pytest.approx(suya[fila.cargo.nombre], abs=0.06), fila.cargo.nombre
    assert {f.cargo.nombre: round(f.total_mes, 2) for f in m.filas if f.cargo.nombre in suya}["Gerente AyF"] == 43.15


# ---- Piezas sueltas ---------------------------------------------------------------------------------------------------------------


def test_un_cierre_de_varios_dias_reparte_sus_horas_y_una_diaria_rinde_distinto_cada_dia():
    anio_abierto(feriados=())
    jefa = cargo("Jefa de Control")
    t = tarea("T1", jefa, "CIERRE_DIA_HABIL", n=3)
    t.minutos_estimados, t.dh_inicio, t.horas_dh = 120, 2, {"2": 0.8, "3": 1.2}
    t.save()
    d = tarea("T2", jefa, "DIARIA_HABIL")
    d.minutos_estimados, d.horas_semana = 60, {"0": 2.0, "1": 1.0}  # lunes 2 h, martes 1 h, el resto de los días no se hace
    d.save()
    m = matriz.construir(2026, 11)
    j = next(f for f in m.filas if f.cargo == jefa)
    assert j.horas[date(2026, 11, 3)] == pytest.approx(0.8 + 1.0) and j.horas[date(2026, 11, 4)] == pytest.approx(1.2)  # martes 3 (DH02) y miércoles 4 (DH03)
    assert j.horas[date(2026, 11, 2)] == pytest.approx(2.0) and j.horas[date(2026, 11, 5)] == 0  # lunes 2 h; el jueves no se hace


def test_el_techo_de_planificacion_baja_en_los_dias_de_revision():
    anio_abierto(feriados=())
    cargo("Jefa de Control")
    m = matriz.construir(2026, 11)
    assert [m.techo(d) for d in m.dias] == [0.9] * 7 + [0.8, 0.75, 0.85, 0.95]  # DH00 a DH06 90 %, DH07 80 %, DH08 75 %, DH09 85 %, DH10 95 %


def test_el_dh00_lleva_la_operacion_normal_del_ultimo_habil_del_mes_anterior():
    anio_abierto(feriados=())
    jefa = cargo("Jefa de Control")
    s = tarea("T3", jefa, "SEMANAL", dia_semana=4)
    s.minutos_estimados = 90
    s.save()
    j = next(f for f in matriz.construir(2026, 11).filas if f.cargo == jefa)
    assert j.horas[date(2026, 10, 30)] == pytest.approx(1.5)  # el viernes 30-10 es el DH00


# ---- Desde la pantalla --------------------------------------------------------------------------------------------------------------


def test_la_pantalla_de_carga_reconoce_la_planificacion_2_0_la_muestra_y_la_aplica(base):
    jefa = usuario_con_rol("jefa", "JEFATURA", persona("Jefa", cargo("Jefa de Control")))
    c = Client()
    c.force_login(jefa)
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": SimpleUploadedFile("plan.xlsx", PLAN2.read_bytes())})
    html = r.content.decode()
    assert r.status_code == 200 and "Control del cierre" in html and "Cierre contable general" in html
    assert not Proceso.objects.filter(nombre="Control del cierre").exists()  # solo se mostró
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "aplicar", "confirmo": "on"}, follow=True)
    assert r.status_code == 200 and Proceso.objects.filter(nombre="Control del cierre", orden=0).exists() and Tarea.objects.filter(activa=True).count() == 206


@pytest.mark.parametrize("nombre,args,params", [
    ("informe_matriz", [], {"mes": "2026-11"}), ("informe_matriz_exportar", [], {"mes": "2026-11"}), ("mant_tareas", [], {}), ("mant_procesos", [], {}),
    ("planificacion", [], {}), ("planificacion_exportar", [], {}), ("mant_tareas_exportar", [], {}), ("mant_procesos_exportar", [], {}), ("informe_carga", [], {}),
    ("informe_cronograma", [], {}), ("informe_panel", [], {}), ("abrir_mes", [], {}),
])
def test_las_pantallas_principales_funcionan_con_los_datos_de_la_planificacion_2_0(cargado, nombre, args, params):
    anio_abierto(feriados=())
    gerente = usuario_con_rol("ger", "GERENTE", persona("Gerente", Cargo.objects.get(nombre="Gerente AyF")))
    c = Client()
    c.force_login(gerente)
    r = c.get(reverse(nombre, args=args), params)
    assert r.status_code == 200, nombre


def test_la_tarea_nueva_y_la_edicion_conservan_lo_que_trae_el_plan(cargado):
    """Editar una tarea desde el Mantenedor no debe borrar sus horas por día, predecesoras ni su justificación."""
    from nucleo.servicios import mantenedor
    jefa = usuario_con_rol("jefa2", "JEFATURA", persona("Jefa", Cargo.objects.get(nombre="Jefa de Control")))
    t = Tarea.objects.get(codigo="17-CCO.02.001")
    d = mantenedor.DatosTarea(proceso_id=t.proceso_id, tarea_principal=t.tarea_principal, subtarea=t.subtarea, cargo_ejecuta_id=t.cargo_ejecuta_id, tipo=t.regla_tipo, n=t.regla_n,
                              cargo_revisa_id=t.cargo_revisa_id, minutos=t.minutos_estimados, observaciones="editada", dh_inicio=t.dh_inicio)
    mantenedor.editar_tarea(jefa, t, d)
    t.refresh_from_db()
    assert t.observaciones == "editada" and t.horas_dh == {"1": 0.8, "2": 1.2} and t.justificacion and t.predecesoras.count() > 0 and t.dh_inicio == 1


# ---- Control del plan vigente ----------------------------------------------------------------------------------------------------------------


def test_el_plan_de_karla_no_tiene_dependencias_incumplidas_y_sus_hitos_cumplen(cargado):
    """Sus alertas y su tabla de hitos dicen «CUMPLE»: la app lo comprueba con las predecesoras y el calendario del mes."""
    anio_abierto(feriados=())
    m = matriz.construir(2026, 11)
    assert matriz.dependencias_incumplidas(m) == []
    hitos = matriz.hitos_del_plan(m)
    assert len(hitos) >= 6 and all(h["cumple"] for h in hitos)
    assert [h["dh"] for h in hitos][:2] == ["DH03", "DH04"] and hitos[-1]["dh"] == "DH10"


def test_una_dependencia_al_reves_se_detecta_y_el_hito_deja_de_cumplir():
    anio_abierto(feriados=())
    jefa = cargo("Jefa de Control")
    previa, hito = tarea("A", jefa, "CIERRE_DIA_HABIL", n=5), tarea("B", jefa, "CIERRE_DIA_HABIL", n=3)
    hito.tipo_control = "Hito DH03"
    hito.save()
    hito.predecesoras.add(previa)
    m = matriz.construir(2026, 11)
    assert matriz.dependencias_incumplidas(m) == ["B vence el DH03 pero su predecesora A vence el DH05."]
    assert matriz.hitos_del_plan(m)[0]["cumple"] is False and matriz.hitos_del_plan(m)[0]["tarde"] == 1
    assert any("antes que alguna de sus predecesoras" in linea for linea in matriz.diagnostico_del_plan(m))


def test_el_diagnostico_del_plan_de_karla_es_legible(cargado):
    anio_abierto(feriados=())
    lineas = matriz.diagnostico_del_plan(matriz.construir(2026, 11))
    assert any("Entre DH01 y DH08" in linea for linea in lineas) and any("Más exigido" in linea for linea in lineas) and any("predecesoras" in linea for linea in lineas)


def test_las_tareas_que_el_archivo_trae_de_9_minutos_quedan_en_10(cargado):
    """Karla (03-11-2026, pregunta 4): «las que decían 9 minutos» pasan a 10; el resto queda como en el archivo."""
    t = Tarea.objects.get(codigo="19-CTR.01.001") if Tarea.objects.filter(codigo="19-CTR.01.001").exists() else Tarea.objects.get(subtarea__startswith="Obtener la cartola real de Transbank")
    assert t.minutos_estimados == 10
    assert not Tarea.objects.filter(activa=True, minutos_estimados=9).exists()
    assert Tarea.objects.filter(activa=True, minutos_estimados=10).count() >= 10
    otra = Tarea.objects.get(subtarea__startswith="Cotejar el RCV contra Odoo", proceso__nombre="Cierre Compras")
    assert otra.minutos_estimados == 60  # lo demás no se toca


def test_la_cuota_de_contribuciones_vence_el_15_de_abril_junio_septiembre_y_noviembre(cargado):
    """Karla (03-11-2026, pregunta 6): día 15; si cae en día inhábil, el hábil siguiente (así noviembre no cae en el DH10 del Contador)."""
    t = Tarea.objects.get(subtarea__startswith="Pagar la cuota de contribucion")
    assert (t.regla_tipo, t.regla_dia, t.regla_meses, t.regla_ajuste, t.requiere_revision) == ("MESES", 15, "4,6,9,11", "siguiente", False)
    from nucleo.servicios.calendario import Calendario
    from nucleo.servicios.recurrencia import fechas_limite
    assert fechas_limite(t.regla(), 2026, 11, Calendario([])) == [date(2026, 11, 16)]  # el 15-11-2026 es domingo: pasa al lunes, ya fuera de las semanas del cierre
    assert fechas_limite(t.regla(), 2026, 12, Calendario([])) == []
    assert not importador.previsualizar(PLAN2, incluir_dia_9=False).requieren_revision
