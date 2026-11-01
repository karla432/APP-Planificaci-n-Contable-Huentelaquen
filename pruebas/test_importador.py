"""Importador de la planificación mensual (Excel revisado por Karla el 31-10-2026): 195 tareas en el orden en que se procesan."""
from collections import Counter
from pathlib import Path

import openpyxl
import pytest
from django.conf import settings

from nucleo.models import Cargo, Colaborador, EventoAuditoria, Proceso, Tarea
from nucleo.servicios import importador
from nucleo.servicios.importador import convertir_regla, normalizar
from nucleo.servicios.recurrencia import Regla

EXCEL = Path(settings.BASE_DIR) / "docs" / "datos" / "Planificacion_Mensual_Huentelauquen_Revisada.xlsx"
EXTERNOS = {"Vendedor Stgo": 4, "RR.HH.": 2, "Jefe Bodega": 1, "Gerencia": 1, "Gerencia / Directorio": 1, "Bodega": 1, "Jefaturas de área": 1, "Jefatura Lechería": 1}


# ---- Conversión de «Periodicidad» + «Cuándo» en regla ----------------------------------------


def test_normalizar_junta_espacios_y_saltos_de_linea():
    assert normalizar("  Cargar \n  el   reintegro \t") == "Cargar el reintegro"
    assert normalizar(None) == ""


@pytest.mark.parametrize(
    "periodicidad,cuando,esperada",
    [
        ("Diaria", "Todos los días hábiles", Regla("DIARIA_HABIL")),
        ("Semanal", "Lunes", Regla("SEMANAL", dia_semana=0)),
        ("Semanal", "Miércoles", Regla("SEMANAL", dia_semana=2)),
        ("Semanal", "Viernes", Regla("SEMANAL", dia_semana=4)),
        ("Mensual (cierre)", "Día hábil 3", Regla("CIERRE_DIA_HABIL", n=3)),
        ("Mensual (cierre)", "Día hábil 7", Regla("CIERRE_DIA_HABIL", n=7)),
        ("Mensual (cierre)", "Día hábil 8", Regla("CIERRE_HITO", n=8)),  # los días 8, 9 y 10 son días del mes
        ("Mensual (cierre)", "D10 · cierre contable", Regla("CIERRE_HITO", n=10)),
        ("Puntual", "Al dar de alta un activo nuevo", Regla("EVENTO")),
        ("Puntual", "Al recibir el subsidio", Regla("EVENTO")),
    ],
)
def test_convierte_las_formas_claras(periodicidad, cuando, esperada):
    c = convertir_regla(periodicidad, cuando)
    assert c.regla == esperada and c.motivo_revision == ""


def test_el_d7_pasa_al_dia_8_del_mes_con_reportes_listos_en_la_tarde():
    """Karla (01-11-2026): reportes listos el día 8 (tarde), Gerente General el 9 y Directorio el 10; son días del mes, no días hábiles."""
    c = convertir_regla("Mensual (cierre)", "D7 · reporte a Gerencia")
    assert c.regla == Regla("CIERRE_HITO", n=8) and c.motivo_revision == ""
    assert "día 8" in c.nota


def test_semanal_con_franja_la_conserva():
    c = convertir_regla("Semanal", "Martes (mañana)")
    assert c.regla == Regla("SEMANAL", dia_semana=1) and c.franja == "mañana"


@pytest.mark.parametrize("cuando,dia", [("Día 13", 13), ("Día 15", 15)])
def test_dia_fijo_va_al_habil_anterior_pero_queda_pendiente_de_confirmar(cuando, dia):
    for per in ("Mensual", "Mensual (cierre)"):
        c = convertir_regla(per, cuando)
        assert c.regla == Regla("DIA_FIJO", dia=dia, ajuste="anterior") and c.estado == "pendiente_confirmar"


def test_ultimo_dia_del_mes():
    c = convertir_regla("Mensual (cierre)", "Ultimo dia del Mes")
    assert c.regla == Regla("FIN_DE_MES", ajuste="anterior") and c.estado == "pendiente_confirmar"


@pytest.mark.parametrize("cuando,meses", [("Cuotas de abril, junio, septiembre y noviembre", (4, 6, 9, 11)), ("Enero y julio", (1, 7))])
def test_meses_especificos_sin_dia_quedan_para_revision(cuando, meses):
    c = convertir_regla("Puntual", cuando)
    assert c.regla.tipo == "MESES" and c.regla.meses == meses
    assert "día" in c.motivo_revision.lower()


@pytest.mark.parametrize(
    "periodicidad,cuando,palabra",
    [
        (None, None, "periodicidad"),
        ("Semanal", None, "día"),
        ("Diaria", "Viernes", "contradic"),
        ("Mensual (cierre)", "Cuando se pueda", "reconoc"),
        ("Mensual (cierre)", "Día hábil 11", "reconoc"),
    ],
)
def test_lo_ambiguo_se_marca_para_revision_y_no_se_adivina(periodicidad, cuando, palabra):
    c = convertir_regla(periodicidad, cuando)
    assert palabra in c.motivo_revision.lower() and c.regla is None


# ---- Con el Excel real --------------------------------------------------------------------------


def test_lee_las_195_filas_en_el_orden_del_excel():
    filas = importador.leer_excel(EXCEL)
    assert len(filas) == 195 and len({f.proceso for f in filas}) == 34
    assert filas[0].fila == 5 and filas[0].proceso == "Seguimiento"
    assert filas[0].horas == 0.5 and filas[0].ejecuciones == pytest.approx(4.33)


@pytest.mark.django_db
def test_vista_previa_no_guarda_nada_y_reporta_lo_dudoso():
    vp = importador.previsualizar(EXCEL)
    assert Tarea.objects.count() == 0
    assert len(vp.altas) == 195 and not vp.cambios and not vp.bajas and len(vp.procesos_nuevos) == 35  # 194 del Excel + la revisión del día 9
    # El Excel trae una tarea repetida: la fila 61 repite la 51 (0,75 h contra 0,5 h). Se importa una vez y se reporta.
    assert [(f.fila, f.subtarea) for f in vp.duplicadas] == [(61, "Registrar Regularizacion Rechazo Pago a Proveedores")]
    texto = " | ".join(f.subtarea for f, _ in vp.requieren_revision).lower()
    for esperado in ("boletas de honorarios", "contribuciones", "patente municipal"):
        assert esperado in texto, esperado
    assert Counter(f.ejecuta for f in vp.externas) == EXTERNOS  # 12 tareas de 8 cargos externos
    assert vp.inconsistencias_fecha == []  # el Excel nuevo ya no trae «Fecha 1.ª vez»


@pytest.mark.django_db
def test_aplicar_crea_tareas_en_orden_con_codigos_horas_y_sin_personas():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    assert Tarea.objects.count() == 195 and Proceso.objects.count() == 35
    primeras = list(Tarea.objects.order_by("secuencia").values_list("codigo", "secuencia", flat=False)[:2])
    assert primeras == [("01-SEG.01.001", 1), ("01-SEG.02.001", 2)] and Tarea.objects.order_by("secuencia").last().secuencia == 195
    assert Colaborador.objects.count() == 0  # las personas las crea el administrador
    cuentas = Counter(Tarea.objects.values_list("cargo_ejecuta__nombre", flat=True))
    assert (cuentas["Jefa de Control"], cuentas["Contador Senior"], cuentas["Asistente Contable"], cuentas["Gerente AyF"]) == (80, 54, 29, 20)
    assert not Cargo.objects.get(nombre="Contador Senior").es_externo
    for nombre in EXTERNOS:
        assert Cargo.objects.get(nombre=nombre).es_externo
    assert EventoAuditoria.objects.filter(accion="importacion.aplicada").count() == 1


@pytest.mark.django_db
def test_los_cargos_quedan_en_el_orden_de_karla_y_despues_los_externos():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    nombres = list(Cargo.objects.values_list("nombre", flat=True))
    assert nombres[:4] == ["Gerente AyF", "Jefa de Control", "Contador Senior", "Asistente Contable"]
    assert set(nombres[4:]) == set(EXTERNOS)


@pytest.mark.django_db
def test_quien_revisa_sale_del_excel_y_las_tareas_sin_revisor_no_se_inventan():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    cuentas = Counter(t.cargo_revisa.nombre if t.cargo_revisa else None for t in Tarea.objects.select_related("cargo_revisa"))
    # 62 las revisa el Gerente AyF; 128 no tienen revisor (127 del Excel + la revisión del día 9); 5 son de externos sin quien reciba en el Excel (se propone a la Jefa).
    assert cuentas == {"Gerente AyF": 62, None: 128, "Jefa de Control": 5}
    assert not Tarea.objects.filter(cargo_ejecuta__nombre="Jefa de Control").exclude(cargo_revisa=None).exists()


@pytest.mark.django_db
def test_el_cierre_son_los_dias_habiles_1_a_7_y_los_dias_8_9_y_10_del_mes():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    habiles = Counter(t.regla_n for t in Tarea.objects.filter(regla_tipo="CIERRE_DIA_HABIL"))
    assert max(habiles) == 7 and habiles[7] == 1
    hitos = Counter(t.regla_n for t in Tarea.objects.filter(regla_tipo="CIERRE_HITO"))
    assert hitos[8] == 19  # 18 que decían D7 + 1 que ya decía «Día hábil 8»
    assert hitos[10] == 9 and hitos[9] == 2 and set(hitos) == {8, 9, 10}  # el 9: una del Excel + la revisión con el Gerente General
    assert Tarea.objects.filter(cuando_excel__startswith="D7").count() == 18  # lo que decía el Excel queda guardado


@pytest.mark.django_db
def test_las_horas_estimadas_marcan_quien_las_definio():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    sin_tiempo = Tarea.objects.filter(minutos_estimados__isnull=True)
    assert [t.tarea_principal for t in sin_tiempo] == ["Revisión del cierre con Gerente General"]  # la del día 9 aún no tiene tiempo
    assert Counter(Tarea.objects.values_list("fuente_horas", flat=True)) == {"estimacion": 171, "gerente": 24}
    t = Tarea.objects.get(secuencia=1)
    assert t.minutos_estimados == 30 and float(t.ejecuciones_mes) == pytest.approx(4.33)


@pytest.mark.django_db
def test_conserva_las_referencias_normativas_y_marca_para_revision_sin_corregir():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    assert Tarea.objects.exclude(referencia_normativa="").count() == 22
    marcadas = Tarea.objects.filter(requiere_revision=True)
    assert marcadas.count() >= 3 and all(t.motivo_revision for t in marcadas)
    h = Tarea.objects.get(subtarea__icontains="boletas de honorarios del mes")
    assert h.periodicidad_excel == "Semanal" and h.cuando_excel == ""  # tal cual venía


@pytest.mark.django_db
def test_reimportar_el_mismo_excel_no_duplica_ni_cambia_nada():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    vp = importador.previsualizar(EXCEL)
    assert not vp.altas and not vp.cambios and not vp.bajas
    importador.aplicar(vp, usuario=None)
    assert Tarea.objects.count() == 195


@pytest.mark.django_db
def test_reimportar_un_excel_actualizado_muestra_altas_cambios_y_bajas(tmp_path):
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    wb = openpyxl.load_workbook(EXCEL, data_only=True)  # solo valores: al guardar se pierden los resultados de las fórmulas
    ws = wb["Planificación"]
    ws.cell(row=5, column=4).value = "Asistente Contable"  # cambia el responsable de la primera tarea (cambio)
    ws.delete_rows(6)  # sale una tarea (baja)
    ws.append(["Proceso nuevo", "Tarea nueva", "Subtarea nueva", "Contador Senior", None, "Diaria", "Todos los días hábiles", None, None, 0.5, 21])  # alta
    nuevo = tmp_path / "actualizado.xlsx"
    wb.save(nuevo)
    vp = importador.previsualizar(nuevo)
    assert (len(vp.altas), len(vp.cambios), len(vp.bajas)) == (1, 1, 1) and vp.procesos_nuevos == ["Proceso nuevo"]
    importador.aplicar(vp, usuario=None)
    t_nueva = Tarea.objects.get(subtarea="Subtarea nueva")
    assert t_nueva.codigo.startswith("36-") and t_nueva.codigo.endswith(".01.001")  # proceso nuevo: sigue al último (35)
    assert Tarea.objects.filter(activa=False).count() == 1  # no se borra físicamente
    assert Tarea.objects.get(secuencia=1).cargo_ejecuta.nombre == "Asistente Contable"


@pytest.mark.django_db
def test_la_revision_del_dia_9_con_el_gerente_general_se_crea_y_no_se_duplica():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    t = Tarea.objects.get(tarea_principal="Revisión del cierre con Gerente General")
    assert (t.regla_tipo, t.regla_n, t.cargo_ejecuta.nombre, t.proceso.nombre) == ("CIERRE_HITO", 9, "Gerente AyF", "Revisión día 9")
    assert t.cargo_revisa is None and not t.requiere_revision
    # va antes del cierre del día 10 en el orden de proceso
    assert t.secuencia < Tarea.objects.filter(proceso__nombre="Cierre día 10").order_by("secuencia").first().secuencia
    assert Tarea.objects.filter(tarea_principal=t.tarea_principal).count() == 1


@pytest.mark.django_db
def test_los_cargos_del_excel_se_llaman_como_los_definio_karla():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    nombres = set(Cargo.objects.values_list("nombre", flat=True))
    assert {"Contador Senior", "Jefa de Control"} <= nombres
    assert not nombres & {"Contadora Senior", "Jefa Gestión y Control"}


@pytest.mark.django_db
def test_los_procesos_quedan_en_el_orden_del_excel_y_no_en_orden_alfabetico():
    filas = importador.leer_excel(EXCEL)
    esperado = []
    for f in importador._con_tarea_del_dia_9(filas):
        if f.proceso not in esperado:
            esperado.append(f.proceso)
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    assert list(Proceso.objects.values_list("nombre", flat=True)) == esperado
    assert esperado != sorted(esperado)  # el Excel no está ordenado por el alfabeto
    assert list(Proceso.objects.values_list("codigo", flat=True))[:3] == ["01-SEG", "02-VEN", "03-VST"]
    assert Proceso.objects.get(nombre="Revisión día 9").orden == esperado.index("Revisión día 9") + 1


@pytest.mark.django_db
def test_todos_los_codigos_tienen_la_forma_pro_tar_sub_y_son_unicos():
    import re
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    codigos = list(Tarea.objects.values_list("codigo", flat=True))
    assert all(re.fullmatch(r"\d{2}-[A-Z]{3}\.\d{2}\.\d{3}", c) for c in codigos) and len(set(codigos)) == len(codigos) == 195
    for t in Tarea.objects.select_related("proceso"):
        assert t.codigo.startswith(t.proceso.codigo + ".")
