"""Pantallas de descarga y carga masiva (Tareas y Procesos)."""
import io
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from nucleo.models import EventoAuditoria, Proceso, Tarea
from nucleo.servicios import excel_masivo, importador
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db
EXCEL = Path(settings.BASE_DIR) / "docs" / "datos" / "Planificacion_Mensual_Huentelauquen_Revisada.xlsx"


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))


@pytest.fixture
def mundo():
    importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
    jefa_c = cargo("Jefa de Control")
    u = {"jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", jefa_c)), "ger": usuario_con_rol("ger", "GERENTE", persona("Ger", cargo("Gerente AyF"))),
         "cont": usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior"))), "admin": usuario_con_rol("admin", "ADMIN_SISTEMA")}
    return u


def cli(u):
    c = Client()
    c.force_login(u)
    return c


def archivo(contenido: bytes, nombre="tareas.xlsx"):
    return SimpleUploadedFile(nombre, contenido, content_type=excel_masivo.__dict__.get("XLSX", "application/octet-stream"))


def con_cambio(cambio):
    wb = openpyxl.load_workbook(io.BytesIO(excel_masivo.exportar_tareas()))
    cambio(wb["Planificación"])
    s = io.BytesIO()
    wb.save(s)
    return s.getvalue()


# ---- Descargas ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["mant_tareas_exportar", "mant_procesos_exportar"])
def test_la_descarga_es_un_excel_con_la_fecha_en_el_nombre(mundo, nombre):
    r = cli(mundo["jefa"]).get(reverse(nombre))
    assert r.status_code == 200 and "spreadsheetml" in r["Content-Type"]
    assert "20261204.xlsx" in r["Content-Disposition"] and r["Content-Disposition"].startswith("attachment")
    assert openpyxl.load_workbook(io.BytesIO(r.content)).sheetnames


def test_descargar_tareas_queda_en_la_bitacora(mundo):
    cli(mundo["ger"]).get(reverse("mant_tareas_exportar"))
    assert EventoAuditoria.objects.filter(accion="tareas.descargadas").count() == 1


@pytest.mark.parametrize("nombre", ["mant_tareas_exportar", "mant_procesos_exportar", "mant_tareas_cargar"])
def test_solo_gerente_y_jefatura_descargan_y_cargan(mundo, nombre):
    assert cli(mundo["cont"]).get(reverse(nombre)).status_code == 403
    assert cli(mundo["admin"]).get(reverse(nombre)).status_code == 403
    assert Client().get(reverse(nombre)).status_code == 302  # sin sesión: a ingresar
    assert cli(mundo["ger"]).get(reverse(nombre)).status_code == 200


def test_las_pantallas_de_tareas_y_procesos_ofrecen_descargar_y_cargar(mundo):
    html = cli(mundo["jefa"]).get(reverse("mant_tareas")).content.decode()
    assert "Descargar Excel" in html and "Cargar Excel" in html
    html = cli(mundo["jefa"]).get(reverse("mant_procesos")).content.decode()
    assert "Descargar Excel" in html and "Cargar Excel" in html
    assert html.index("Seguimiento") < html.index("Ventas Sala de Ventas") < html.index("Compras")  # orden del Excel, no alfabético


def test_la_lista_de_tareas_sigue_el_orden_de_proceso(mundo):
    html = cli(mundo["jefa"]).get(reverse("mant_tareas")).content.decode()
    assert html.index("01-SEG.01.001") < html.index("02-VEN.01.001") < html.index("03-VST.01.001")


# ---- Cargar tareas: dos pasos -------------------------------------------------------------------------------------


def test_subir_el_excel_muestra_la_vista_previa_y_no_guarda(mundo):
    c = cli(mundo["jefa"])
    contenido = con_cambio(lambda h: setattr(h["E4"], "value", "Analista Contable"))
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(contenido)})
    html = r.content.decode()
    assert r.status_code == 200 and "Aún no se guardó nada" in html and "Tareas modificadas" in html and "Responsable" in html
    assert "Aplicar la carga" in html and Tarea.objects.get(secuencia=1).cargo_ejecuta.nombre != "Analista Contable"


def test_confirmar_aplica_los_cambios(mundo):
    c = cli(mundo["jefa"])
    c.post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(con_cambio(lambda h: setattr(h["E4"], "value", "Analista Contable")))})
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "aplicar"}, follow=True)
    assert "Carga aplicada" in r.content.decode() and "1 modificadas" in r.content.decode()
    assert Tarea.objects.get(secuencia=1).cargo_ejecuta.nombre == "Analista Contable"
    # el archivo en espera ya no sirve: aplicar otra vez avisa que venció
    assert "venció" in c.post(reverse("mant_tareas_cargar"), {"accion": "aplicar"}, follow=True).content.decode()


def test_desactivar_tareas_exige_marcar_la_confirmacion(mundo):
    c = cli(mundo["jefa"])
    c.post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(con_cambio(lambda h: h.delete_rows(4, 2)))})
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "aplicar"})
    assert "desactiva 2" in r.content.decode() and Tarea.objects.filter(activa=False).count() == 0  # vuelve a la vista previa con el aviso
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "aplicar", "confirmo": "on"}, follow=True)
    assert "2 desactivadas" in r.content.decode() and Tarea.objects.filter(activa=False).count() == 2


def test_cancelar_no_cambia_nada_y_borra_el_archivo(mundo):
    c = cli(mundo["jefa"])
    c.post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(con_cambio(lambda h: setattr(h["E4"], "value", "Analista Contable")))})
    token = c.session["carga_masiva"]["token"]
    r = c.post(reverse("mant_tareas_cargar"), {"accion": "cancelar"}, follow=True)
    assert "Carga cancelada" in r.content.decode() and "carga_masiva" not in c.session
    with pytest.raises(Exception):
        excel_masivo.leer_en_espera(token)


def test_un_archivo_que_no_es_excel_vuelve_con_un_mensaje(mundo):
    r = cli(mundo["jefa"]).post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(b"hola", "tareas.xlsx")}, follow=True)
    assert "no parece un Excel" in r.content.decode()
    r = cli(mundo["jefa"]).post(reverse("mant_tareas_cargar"), {"accion": "revisar"}, follow=True)
    assert "Elige primero el archivo" in r.content.decode()


def test_con_un_cargo_inexistente_no_se_ofrece_aplicar(mundo):
    r = cli(mundo["jefa"]).post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(con_cambio(lambda h: setattr(h["E4"], "value", "Cargo inventado")))})
    html = r.content.decode()
    assert "No se puede aplicar todavía" in html and "Cargo inventado" in html and "Aplicar la carga" not in html


def test_el_colaborador_no_puede_aplicar_aunque_conozca_la_url(mundo):
    r = cli(mundo["cont"]).post(reverse("mant_tareas_cargar"), {"accion": "revisar", "archivo": archivo(excel_masivo.exportar_tareas())})
    assert r.status_code == 403


# ---- Cargar procesos ----------------------------------------------------------------------------------------------


def test_cargar_procesos_reordena_y_avisa(mundo):
    wb = openpyxl.load_workbook(io.BytesIO(excel_masivo.exportar_procesos()))
    wb["Procesos"]["A2"] = 999
    s = io.BytesIO()
    wb.save(s)
    r = cli(mundo["jefa"]).post(reverse("mant_procesos_cargar"), {"archivo": archivo(s.getvalue(), "procesos.xlsx")}, follow=True)
    assert "Procesos cargados" in r.content.decode()
    assert Proceso.objects.last().nombre == "Seguimiento"


def test_cargar_procesos_con_un_archivo_malo_avisa(mundo):
    r = cli(mundo["jefa"]).post(reverse("mant_procesos_cargar"), {"archivo": archivo(b"x", "p.xlsx")}, follow=True)
    assert "no parece un Excel" in r.content.decode()
    assert cli(mundo["jefa"]).get(reverse("mant_procesos_cargar")).status_code == 405
