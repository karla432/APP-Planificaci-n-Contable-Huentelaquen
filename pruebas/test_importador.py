"""Importador del Excel maestro (docs/f1: sección 11 del encargo)."""
from collections import Counter
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from django.conf import settings

from nucleo.models import Cargo, Colaborador, EventoAuditoria, Proceso, Tarea
from nucleo.servicios import importador
from nucleo.servicios.importador import convertir_regla, normalizar
from nucleo.servicios.recurrencia import Regla

EXCEL = Path(settings.BASE_DIR) / "docs" / "datos" / "Listado_Maestro_Tareas_Huentelauquen_Modificado.xlsx"


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
        ("Mensual (cierre)", "D7 · reporte a Gerencia", Regla("CIERRE_HITO", n=7)),
        ("Mensual (cierre)", "D10 · cierre contable", Regla("CIERRE_HITO", n=10)),
        ("Puntual", "Al dar de alta un activo nuevo", Regla("EVENTO")),
        ("Puntual", "Al recibir el subsidio", Regla("EVENTO")),
    ],
)
def test_convierte_las_formas_claras(periodicidad, cuando, esperada):
    c = convertir_regla(periodicidad, cuando)
    assert c.regla == esperada and c.motivo_revision == ""


def test_semanal_con_franja_la_conserva():
    c = convertir_regla("Semanal", "Martes (mañana)")
    assert c.regla == Regla("SEMANAL", dia_semana=1) and c.franja == "mañana"


def test_dia_13_va_al_habil_anterior_pero_queda_pendiente_de_confirmar():
    c = convertir_regla("Mensual", "Día 13")
    assert c.regla == Regla("DIA_FIJO", dia=13, ajuste="anterior")
    assert c.estado == "pendiente_confirmar"  # la Contadora Senior debe verificar la norma de Previred


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
    ],
)
def test_lo_ambiguo_se_marca_para_revision_y_no_se_adivina(periodicidad, cuando, palabra):
    c = convertir_regla(periodicidad, cuando)
    assert palabra in c.motivo_revision.lower()
    assert c.regla is None


# ---- Con el Excel real --------------------------------------------------------------------------


def test_lee_186_filas_del_excel():
    filas = importador.leer_excel(EXCEL)
    assert len(filas) == 186
    assert len({f.proceso for f in filas}) == 34
    assert filas[0].fila == 5  # el encabezado está en la fila 4


@pytest.mark.django_db
def test_vista_previa_no_guarda_nada_y_reporta_lo_problematico():
    vp = importador.previsualizar(EXCEL)
    assert Tarea.objects.count() == 0
    assert len(vp.altas) == 186 and not vp.cambios and not vp.bajas and not vp.duplicadas
    assert len(vp.procesos_nuevos) == 34
    revisadas = {f.subtarea for f, _ in vp.requieren_revision}
    texto = " | ".join(revisadas).lower()
    for esperado in ("reintegro de cajas", "guias de despacho", "boletas de honorarios", "facturas observadas"):
        assert esperado in texto, esperado
    assert len(vp.requieren_revision) == 6  # las 4 inconsistentes + 2 filas de «meses» sin día
    assert Counter(f.ejecuta for f in vp.externas) == {
        "Rafael": 3, "RR.HH.": 2, "Gerencia / Directorio": 1, "Bodega": 1, "Jefaturas de área": 1, "Jefatura Lechería": 1,
    }  # 9 tareas de 6 cargos externos


@pytest.mark.django_db
def test_aplicar_crea_tareas_con_codigos_estables_y_sin_personas(django_user_model):
    vp = importador.previsualizar(EXCEL)
    importador.aplicar(vp, usuario=None)
    assert Tarea.objects.count() == 186 and Proceso.objects.count() == 34
    assert list(Tarea.objects.order_by("codigo").values_list("codigo", flat=True))[:2] == ["TAR-0001", "TAR-0002"]
    assert Tarea.objects.filter(codigo="TAR-0186").exists()
    assert Colaborador.objects.count() == 0  # las personas las crea el administrador
    cuentas = Counter(Tarea.objects.values_list("cargo_ejecuta__nombre", flat=True))
    assert cuentas["Contadora Senior"] == 115
    assert cuentas["Asistente Contable"] == 33  # el cargo se llama como en el Excel y como lo definió Karla (31-10-2026)
    assert not Cargo.objects.filter(nombre="Analista Contable").exists()
    assert cuentas["Jefa Gestión y Control"] == 27
    assert not Cargo.objects.get(nombre="Contadora Senior").es_externo
    for externo in ("Rafael", "RR.HH.", "Bodega", "Jefaturas de área", "Jefatura Lechería", "Gerencia / Directorio"):
        assert Cargo.objects.get(nombre=externo).es_externo
    assert EventoAuditoria.objects.filter(accion="importacion.aplicada").count() == 1


@pytest.mark.django_db
def test_la_revisora_es_siempre_la_jefa_y_la_jefa_la_revisa_el_gerente():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    for t in Tarea.objects.select_related("cargo_ejecuta", "cargo_revisa"):
        esperado = "Gerente AyF" if t.cargo_ejecuta.nombre == "Jefa Gestión y Control" else "Jefa Gestión y Control"
        assert t.cargo_revisa.nombre == esperado, t.codigo
    # Se conserva lo que decía el Excel, para trazabilidad.
    assert Tarea.objects.filter(revisa_excel="").count() == 48


@pytest.mark.django_db
def test_conserva_las_referencias_normativas_de_las_22_observaciones():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    con_referencia = Tarea.objects.exclude(referencia_normativa="")
    assert con_referencia.count() == 22
    assert all("Propuesta §6" in t.referencia_normativa for t in con_referencia)


@pytest.mark.django_db
def test_las_filas_para_revision_quedan_marcadas_y_sin_corregir():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    marcadas = Tarea.objects.filter(requiere_revision=True)
    assert marcadas.count() == 6 and all(t.motivo_revision for t in marcadas)
    rcv = Tarea.objects.get(subtarea__icontains="facturas observadas")
    assert rcv.periodicidad_excel == "Diaria" and rcv.cuando_excel == "Viernes"  # tal cual venía


@pytest.mark.django_db
def test_reimportar_el_mismo_excel_no_duplica_ni_cambia_nada():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    vp = importador.previsualizar(EXCEL)
    assert not vp.altas and not vp.cambios and not vp.bajas
    importador.aplicar(vp, usuario=None)
    assert Tarea.objects.count() == 186


@pytest.mark.django_db
def test_reimportar_un_excel_actualizado_muestra_altas_cambios_y_bajas(tmp_path):
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    wb = openpyxl.load_workbook(EXCEL)
    ws = wb["Tareas"]
    ws.cell(row=5, column=5).value = "Asistente Contable"  # cambia el responsable de la primera tarea (cambio)
    ws.delete_rows(6)  # sale una tarea (baja)
    ws.append([None, "Proceso nuevo", "Tarea nueva", "Subtarea nueva", "Contadora Senior", None, "Diaria", "Todos los días hábiles", None, None])  # alta
    nuevo = tmp_path / "actualizado.xlsx"
    wb.save(nuevo)
    vp = importador.previsualizar(nuevo)
    assert (len(vp.altas), len(vp.cambios), len(vp.bajas)) == (1, 1, 1)
    assert vp.procesos_nuevos == ["Proceso nuevo"]
    importador.aplicar(vp, usuario=None)
    assert Tarea.objects.get(codigo="TAR-0187").subtarea == "Subtarea nueva"  # el código nuevo sigue la secuencia
    assert Tarea.objects.filter(activa=False).count() == 1  # no se borra físicamente
    assert Tarea.objects.get(codigo="TAR-0001").cargo_ejecuta.nombre == "Asistente Contable"


@pytest.mark.django_db
def test_la_fecha_de_primera_vez_solo_sirve_para_validar_la_regla():
    """Hallazgo sobre el Excel actual: 5 filas cuya fecha de 1.ª vez no calza con la regla. Se reportan, no se corrigen."""
    vp = importador.previsualizar(EXCEL)
    filas = {f.fila: aviso for f, aviso in vp.inconsistencias_fecha}
    # Fila 39: «Martes (tarde)» pero la 1.ª vez es el lunes 02-11-2026.
    # Filas 178 a 181 («Reportería día 7», D7): 1.ª vez el 08, 09, 10 y 11-12-2026, todas después del D7 (lunes 07-12).
    assert sorted(filas) == [39, 178, 179, 180, 181]
    # Las reglas siguen siendo las que dice «Cuándo»; la fecha del Excel no genera nada.
    assert Counter(f.conversion.regla.tipo for f, _ in vp.inconsistencias_fecha) == {"SEMANAL": 1, "CIERRE_HITO": 4}


@pytest.mark.django_db
def test_una_fila_bien_convertida_no_genera_aviso_de_fecha():
    vp = importador.previsualizar(EXCEL)
    avisadas = {f.fila for f, _ in vp.inconsistencias_fecha}
    lunes = [f for f in importador.leer_excel(EXCEL) if f.cuando == "Lunes"]
    assert lunes and not any(f.fila in avisadas for f in lunes)


@pytest.mark.django_db
def test_los_cargos_quedan_ordenados_como_los_definio_karla():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    nombres = list(Cargo.objects.values_list("nombre", flat=True))
    assert nombres[:4] == ["Gerente AyF", "Jefa Gestión y Control", "Contadora Senior", "Asistente Contable"]
    assert set(nombres[4:]) == {"Rafael", "RR.HH.", "Gerencia / Directorio", "Bodega", "Jefaturas de área", "Jefatura Lechería"}  # los externos van después
