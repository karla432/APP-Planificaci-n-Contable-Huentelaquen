"""Descarga y carga masiva en Excel de Tareas y Procesos."""
import io
from pathlib import Path

import openpyxl
import pytest
from django.conf import settings

from nucleo.models import Cargo, EventoAuditoria, Proceso, Tarea
from nucleo.servicios import excel_masivo, importador
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db
EXCEL = Path(settings.BASE_DIR) / "docs" / "datos" / "Planificacion_Mensual_Huentelauquen_Revisada.xlsx"


@pytest.fixture
def jefa():
    c = cargo("Jefa de Control")
    return usuario_con_rol("jefa", "JEFATURA", persona("Jefa", c))


@pytest.fixture
def base():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)


def libro(contenido: bytes):
    return openpyxl.load_workbook(io.BytesIO(contenido))


def filas(contenido: bytes):
    hoja = libro(contenido)["Planificación"]
    return [[c.value for c in r] for r in hoja.iter_rows(min_row=4)]


def editado(contenido: bytes, cambios):
    wb = libro(contenido)
    hoja = wb["Planificación"]
    cambios(hoja)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# ---- Descargar tareas ---------------------------------------------------------------------------------------------


def test_la_planilla_de_tareas_sale_en_el_orden_de_proceso_con_sus_codigos(base):
    f = filas(excel_masivo.exportar_tareas())
    assert len(f) == 195
    assert f[0][0] == "01-SEG.01.001" and f[0][1] == "Seguimiento"
    procesos = []
    for r in f:
        if r[1] not in procesos:
            procesos.append(r[1])
    assert procesos == list(Proceso.objects.values_list("nombre", flat=True))  # el orden del Excel, no el alfabético


def test_la_planilla_trae_las_hojas_y_los_encabezados_de_la_carga(base):
    wb = libro(excel_masivo.exportar_tareas())
    assert wb.sheetnames == ["Planificación", "Instrucciones"]
    assert [c.value for c in wb["Planificación"][3]] == excel_masivo.ENCABEZADOS


def test_lo_descargado_se_puede_volver_a_cargar_sin_cambios(base):
    """La prueba más importante: descargar y cargar de nuevo no debe cambiar nada (ni desactivar ni modificar tareas)."""
    contenido = excel_masivo.exportar_tareas()
    vp = importador.previsualizar(io.BytesIO(contenido), incluir_dia_9=False)
    assert (len(vp.altas), len(vp.cambios), len(vp.bajas), len(vp.duplicadas)) == (0, 0, 0, 0), [(t.codigo, d) for t, _, d in vp.cambios][:3]


def test_las_horas_definidas_por_la_gerente_se_marcan_en_verde_y_vuelven(base):
    contenido = excel_masivo.exportar_tareas()
    hoja = libro(contenido)["Planificación"]
    verdes = [r for r in range(4, hoja.max_row + 1) if hoja.cell(row=r, column=11).fill.start_color.rgb == importador.RELLENO_GERENTE]
    assert len(verdes) == Tarea.objects.filter(fuente_horas="gerente").count() == 24


def test_una_tarea_editada_en_el_mantenedor_se_escribe_desde_su_regla(base):
    t = Tarea.objects.get(secuencia=1)
    t.regla_tipo, t.regla_n, t.regla_dia_semana = "CIERRE_DIA_HABIL", 5, None
    t.save()
    fila = filas(excel_masivo.exportar_tareas())[0]
    assert (fila[6], fila[7]) == ("Mensual (cierre)", "Día hábil 5")
    vp = importador.previsualizar(io.BytesIO(excel_masivo.exportar_tareas()), incluir_dia_9=False)
    # lo escrito se entiende al volver a cargarlo: lo único que "cambia" es el texto original del Excel, que se pone al día
    assert all(set(d) <= {"periodicidad_excel", "cuando_excel"} for _, _, d in vp.cambios)


@pytest.mark.parametrize("regla,per,cua", [
    (dict(regla_tipo="DIARIA_HABIL"), "Diaria", "Todos los días hábiles"),
    (dict(regla_tipo="SEMANAL", regla_dia_semana=2, regla_franja="tarde"), "Semanal", "Miércoles (tarde)"),
    (dict(regla_tipo="DIA_FIJO", regla_dia=13, regla_ajuste="anterior"), "Mensual", "Día 13"),
    (dict(regla_tipo="FIN_DE_MES", regla_ajuste="anterior"), "Mensual", "Último día del mes"),
    (dict(regla_tipo="MESES", regla_meses="4,6,9", regla_dia=20), "Puntual", "Día 20 de abril, junio, septiembre"),
    (dict(regla_tipo="EVENTO"), "Puntual", "Al ocurrir el evento"),
])
def test_cada_periodicidad_se_escribe_de_una_forma_que_la_carga_entiende(base, regla, per, cua):
    t = Tarea.objects.get(secuencia=1)
    t.periodicidad_excel = t.cuando_excel = ""
    t.regla_dia_semana = t.regla_n = t.regla_dia = None
    t.regla_meses, t.regla_ajuste, t.regla_franja = "", "siguiente", ""
    for k, v in regla.items():
        setattr(t, k, v)
    t.save()
    assert excel_masivo.texto_de_periodicidad(t) == (per, cua)
    vuelta = importador.convertir_regla(per, cua).regla
    assert vuelta == t.regla()


def test_un_texto_que_empieza_con_igual_no_se_vuelve_formula(base):
    t = Tarea.objects.get(secuencia=1)
    t.subtarea = '=HYPERLINK("http://x","clic")'
    t.save()
    celda = libro(excel_masivo.exportar_tareas())["Planificación"]["D4"]
    assert celda.data_type == "s" and celda.value.startswith("=HYPERLINK")


# ---- Cargar tareas ------------------------------------------------------------------------------------------------


def test_cargar_muestra_primero_una_vista_previa_y_no_guarda_nada(base, jefa):
    contenido = editado(excel_masivo.exportar_tareas(), lambda h: setattr(h["E4"], "value", "Asistente Contable"))
    vp = excel_masivo.previsualizar_tareas(jefa, contenido, "x.xlsx")
    assert len(vp.cambios) == 1 and not vp.altas and not vp.bajas
    assert Tarea.objects.get(secuencia=1).cargo_ejecuta.nombre != "Asistente Contable"


def test_aplicar_guarda_el_cambio_y_deja_constancia_con_el_archivo(base, jefa):
    contenido = editado(excel_masivo.exportar_tareas(), lambda h: setattr(h["E4"], "value", "Asistente Contable"))
    r = excel_masivo.aplicar_tareas(jefa, contenido, "tareas.xlsx")
    assert r["cambios"] == 1
    assert Tarea.objects.get(secuencia=1).cargo_ejecuta.nombre == "Asistente Contable"
    e = EventoAuditoria.objects.filter(accion="importacion.aplicada").latest("id")
    assert e.despues["origen"] == "carga masiva" and e.despues["archivo"] == "tareas.xlsx" and len(e.despues["sha256"]) == 64


def test_una_fila_nueva_crea_la_tarea_con_su_codigo_pro_tar_sub(base, jefa):
    def agregar(h):
        n = h.max_row + 1
        for col, v in enumerate(["", "Seguimiento", "Seguimiento diario", "Revisar correos nuevos", "Asistente Contable", "", "Diaria", "Todos los días hábiles", None, None, 0.25, 21], start=1):
            h.cell(row=n, column=col, value=v)
    r = excel_masivo.aplicar_tareas(jefa, editado(excel_masivo.exportar_tareas(), agregar), "x.xlsx")
    assert r["altas"] == 1
    t = Tarea.objects.get(subtarea="Revisar correos nuevos")
    assert t.codigo.startswith("01-SEG.0") and t.minutos_estimados == 15 and t.cargo_ejecuta.nombre == "Asistente Contable"


def test_las_tareas_que_faltan_en_el_archivo_se_desactivan_solo_con_confirmacion(base, jefa):
    contenido = editado(excel_masivo.exportar_tareas(), lambda h: h.delete_rows(4, 3))
    vp = excel_masivo.previsualizar_tareas(jefa, contenido, "x.xlsx")
    assert len(vp.bajas) == 3
    with pytest.raises(ErrorDeNegocio, match="desactiva 3"):
        excel_masivo.aplicar_tareas(jefa, contenido, "x.xlsx")
    assert Tarea.objects.filter(activa=False).count() == 0
    assert excel_masivo.aplicar_tareas(jefa, contenido, "x.xlsx", confirma_desactivar=True)["bajas"] == 3
    assert Tarea.objects.filter(activa=False).count() == 3 and Tarea.objects.count() == 195  # no se borra nada


def test_un_cargo_mal_escrito_no_crea_un_cargo_nuevo(base, jefa):
    contenido = editado(excel_masivo.exportar_tareas(), lambda h: setattr(h["E4"], "value", "Contadro Senior"))
    with pytest.raises(ErrorDeNegocio, match="Contadro Senior"):
        excel_masivo.aplicar_tareas(jefa, contenido, "x.xlsx")
    from nucleo.models import Cargo
    assert not Cargo.objects.filter(nombre="Contadro Senior").exists()


def test_el_excel_original_con_los_nombres_antiguos_de_cargo_tambien_se_carga(base, jefa):
    vp = excel_masivo.previsualizar_tareas(jefa, EXCEL.read_bytes(), "original.xlsx")
    assert len(vp.altas) == 0 and len(vp.duplicadas) == 1  # solo falta la tarea del día 9, que no resucita en una carga masiva
    assert len(vp.bajas) == 1  # la del día 9 no está en ese Excel: se ofrece desactivar, con confirmación


def test_la_tarea_del_dia_9_no_resucita_si_se_quito_a_proposito(base, jefa):
    contenido = editado(excel_masivo.exportar_tareas(), lambda h: [h.delete_rows(r) for r in range(h.max_row, 3, -1) if h.cell(row=r, column=3).value == "Revisión del cierre con Gerente General"])
    vp = excel_masivo.previsualizar_tareas(jefa, contenido, "x.xlsx")
    assert not vp.altas and len(vp.bajas) == 1


def test_el_orden_de_los_procesos_sigue_el_del_archivo(base, jefa):
    def mover(h):
        filas_ = [[c.value for c in r] for r in h.iter_rows(min_row=4)]
        primer = filas_[0][1]
        delprimero = [f for f in filas_ if f[1] == primer]
        resto = [f for f in filas_ if f[1] != primer]
        h.delete_rows(4, h.max_row)
        for n, f in enumerate(resto + delprimero, start=4):
            for col, v in enumerate(f, start=1):
                h.cell(row=n, column=col, value=v)
    excel_masivo.aplicar_tareas(jefa, editado(excel_masivo.exportar_tareas(), mover), "x.xlsx")
    assert Proceso.objects.get(nombre="Seguimiento").orden == Proceso.objects.count()  # el primero pasó al final


# ---- Cuidado con el archivo ---------------------------------------------------------------------------------------


def test_solo_gerente_y_jefatura_cargan(base):
    c = usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior")))
    with pytest.raises(PermisoDenegado):
        excel_masivo.previsualizar_tareas(c, excel_masivo.exportar_tareas(), "x.xlsx")
    with pytest.raises(PermisoDenegado):
        excel_masivo.cargar_procesos(c, excel_masivo.exportar_procesos(), "p.xlsx")


@pytest.mark.parametrize("contenido,nombre,texto", [
    (b"no es un excel", "x.xlsx", "no parece un Excel"),
    (b"datos", "tareas.csv", "debe ser un Excel"),
    (b"", "x.xlsx", "vacío"),
    (b"x" * (5 * 1024 * 1024 + 1), "x.xlsx", "5 MB"),
])
def test_un_archivo_invalido_se_rechaza_con_un_mensaje_claro(jefa, contenido, nombre, texto):
    with pytest.raises(ErrorDeNegocio, match=texto):
        excel_masivo.previsualizar_tareas(jefa, contenido, nombre)


def test_un_excel_sin_las_columnas_de_tareas_se_rechaza(jefa):
    wb = openpyxl.Workbook()
    wb.active.append(["Proceso", "Otra cosa"])
    wb.active.append(["A", "B"])
    salida = io.BytesIO()
    wb.save(salida)
    with pytest.raises(ErrorDeNegocio, match="columna"):
        excel_masivo.previsualizar_tareas(jefa, salida.getvalue(), "x.xlsx")


def test_demasiadas_filas_se_rechazan(jefa):
    wb = openpyxl.Workbook()
    wb.active.append(["Proceso"])
    for _ in range(excel_masivo.MAX_FILAS + 1):
        wb.active.append(["a"])
    salida = io.BytesIO()
    wb.save(salida)
    with pytest.raises(ErrorDeNegocio, match="filas"):
        excel_masivo.previsualizar_tareas(jefa, salida.getvalue(), "x.xlsx")


def test_el_archivo_en_espera_solo_acepta_su_propio_codigo(jefa):
    token = excel_masivo.guardar_en_espera(b"hola")
    assert excel_masivo.leer_en_espera(token) == b"hola"
    for malo in ("../../etc/passwd", "", "x" * 32, token.upper()):
        with pytest.raises(ErrorDeNegocio):
            excel_masivo.leer_en_espera(malo)
    excel_masivo.borrar_en_espera(token)
    with pytest.raises(ErrorDeNegocio):
        excel_masivo.leer_en_espera(token)


# ---- Procesos ----------------------------------------------------------------------------------------------------


def test_la_planilla_de_procesos_trae_orden_codigo_y_tareas(base):
    hoja = libro(excel_masivo.exportar_procesos())["Procesos"]
    assert [c.value for c in hoja[1]] == ["Orden", "Código", "Sigla", "Proceso", "Tareas activas", "Activo"]
    assert [c.value for c in hoja[2]] == [1, "01-SEG", "SEG", "Seguimiento", 2, "Sí"]
    assert hoja.max_row >= 36


def test_reordenar_procesos_desde_el_excel(base, jefa):
    wb = libro(excel_masivo.exportar_procesos())
    wb["Procesos"]["A2"] = 999  # el primero pasa al final
    salida = io.BytesIO()
    wb.save(salida)
    r = excel_masivo.cargar_procesos(jefa, salida.getvalue(), "p.xlsx")
    nombres = list(Proceso.objects.values_list("nombre", flat=True))
    assert nombres[-1] == "Seguimiento" and nombres[0] == "Ventas Sala de Ventas" and r["reordenados"] >= 1
    assert Proceso.objects.get(nombre="Seguimiento").sigla == "SEG"  # la sigla es su identidad; el prefijo del código sigue al orden
    assert Proceso.objects.get(nombre="Seguimiento").codigo == "35-SEG"


def test_activar_desactivar_y_crear_procesos(base, jefa):
    wb = libro(excel_masivo.exportar_procesos())
    wb["Procesos"]["F3"] = "No"
    hoja = wb["Procesos"]
    hoja.insert_rows(2)
    for col, v in enumerate([None, None, None, "Proceso nuevo", None, "Sí"], start=1):
        hoja.cell(row=2, column=col, value=v)
    salida = io.BytesIO()
    wb.save(salida)
    r = excel_masivo.cargar_procesos(jefa, salida.getvalue(), "p.xlsx")
    assert r["creados"] == 1 and r["activo_cambiado"] == 1
    assert Proceso.objects.get(nombre="Proceso nuevo").orden == 1 and Proceso.objects.get(nombre="Proceso nuevo").codigo.startswith("01-")
    assert EventoAuditoria.objects.filter(accion="procesos.cargados").exists()


def test_los_procesos_que_no_estan_en_el_archivo_quedan_despues_como_estaban(base, jefa):
    wb = openpyxl.Workbook()
    wb.active.append(["Proceso", "Orden"])
    wb.active.append(["Compras", 1])
    salida = io.BytesIO()
    wb.save(salida)
    excel_masivo.cargar_procesos(jefa, salida.getvalue(), "p.xlsx")
    nombres = list(Proceso.objects.values_list("nombre", flat=True))
    assert nombres[0] == "Compras" and nombres[1] == "Seguimiento" and len(nombres) == 35
    assert sorted(Proceso.objects.values_list("orden", flat=True)) == list(range(1, 36))


# ---- Semana del cierre ---------------------------------------------------------------------------------------------------


def test_la_semana_del_cierre_viaja_en_la_planilla_y_se_puede_cargar(base, jefa):
    t = Tarea.objects.filter(regla_tipo="DIARIA_HABIL").first()
    t.modo_cierre, t.cargo_cierre, t.cargo_revisa_cierre = "reasignar", Cargo.objects.get(nombre="Asistente Contable"), Cargo.objects.get(nombre="Contador Senior")
    t.save()
    contenido = excel_masivo.exportar_tareas()
    fila = next(f for f in filas(contenido) if f[0] == t.codigo)
    assert fila[12:15] == ["Reasignar", "Asistente Contable", "Contador Senior"]
    vp = importador.previsualizar(io.BytesIO(contenido), incluir_dia_9=False)
    assert not vp.altas and not vp.cambios and not vp.bajas  # ida y vuelta sin cambios
    # editar: pausarla en vez de reasignarla
    fila_excel = 4 + [f[0] for f in filas(contenido)].index(t.codigo)
    nuevo = editado(contenido, lambda h: (setattr(h.cell(row=fila_excel, column=13), "value", "Pausar"), setattr(h.cell(row=fila_excel, column=14), "value", None), setattr(h.cell(row=fila_excel, column=15), "value", None)))
    assert excel_masivo.aplicar_tareas(jefa, nuevo, "x.xlsx")["cambios"] == 1
    t.refresh_from_db()
    assert (t.modo_cierre, t.cargo_cierre, t.cargo_revisa_cierre) == ("pausar", None, None)


def test_reasignar_sin_responsable_en_el_cierre_no_se_deja_aplicar(base, jefa):
    contenido = excel_masivo.exportar_tareas()
    nuevo = editado(contenido, lambda h: setattr(h.cell(row=4, column=13), "value", "Reasignar"))
    with pytest.raises(ErrorDeNegocio, match="responsable en el cierre"):
        excel_masivo.aplicar_tareas(jefa, nuevo, "x.xlsx")


# ---- Minutos de revisión -------------------------------------------------------------------------------------------------


def test_los_minutos_de_revision_viajan_en_la_planilla_y_se_pueden_cargar(base, jefa):
    contenido = excel_masivo.exportar_tareas()
    encabezados = [c.value for c in libro(contenido)["Planificación"][3]]
    col = encabezados.index("Minutos de revisión") + 1
    t = Tarea.objects.filter(activa=True).first()
    fila_excel = 4 + [f[0] for f in filas(contenido)].index(t.codigo)
    assert libro(contenido)["Planificación"].cell(row=fila_excel, column=col).value is None  # vacío = 15 min generales
    nuevo = editado(contenido, lambda h: setattr(h.cell(row=fila_excel, column=col), "value", 20))
    assert excel_masivo.aplicar_tareas(jefa, nuevo, "x.xlsx")["cambios"] == 1
    t.refresh_from_db()
    assert t.minutos_revision == 20
    again = excel_masivo.exportar_tareas()
    assert libro(again)["Planificación"].cell(row=fila_excel, column=col).value == 20
    vp = importador.previsualizar(io.BytesIO(again), incluir_dia_9=False)
    assert not vp.altas and not vp.cambios and not vp.bajas  # ida y vuelta sin cambios
    sin_valor = editado(again, lambda h: setattr(h.cell(row=fila_excel, column=col), "value", None))
    assert excel_masivo.aplicar_tareas(jefa, sin_valor, "x.xlsx")["cambios"] == 1
    t.refresh_from_db()
    assert t.minutos_revision is None


def test_una_planilla_sin_la_columna_no_borra_los_minutos_de_revision(base, jefa):
    t = Tarea.objects.filter(activa=True).first()
    t.minutos_revision = 25
    t.save()
    contenido = excel_masivo.exportar_tareas()

    def sin_columna(h):
        col = [c.value for c in h[3]].index("Minutos de revisión") + 1
        h.delete_cols(col)

    vp = importador.previsualizar(io.BytesIO(editado(contenido, sin_columna)), incluir_dia_9=False)
    assert not vp.cambios  # una planilla antigua (sin la columna) no toca lo que ya hay
    t.refresh_from_db()
    assert t.minutos_revision == 25
