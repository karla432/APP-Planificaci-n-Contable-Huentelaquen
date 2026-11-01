"""Pantalla y descarga de la matriz del cierre."""
import io
from datetime import date

import openpyxl
import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Cargo, EventoAuditoria, Tarea
from nucleo.servicios import excel_masivo, importador
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))


@pytest.fixture
def mundo():
    anio_abierto()
    nombres = (("Gerente AyF", 1), ("Jefa de Control", 2), ("Contador Senior", 3), ("Asistente Contable", 4))
    c = {n: cargo(n) for n, _ in nombres}
    for n, orden in nombres:
        Cargo.objects.filter(nombre=n).update(orden=orden)
    Cargo.objects.filter(nombre="Gerente AyF").update(horas_mes_max=80)
    u = {"jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", c["Jefa de Control"])), "ger": usuario_con_rol("ger", "GERENTE", persona("Ger", c["Gerente AyF"])),
         "cont": usuario_con_rol("cont", "COLABORADOR", persona("Cont", c["Contador Senior"])), "lectura": usuario_con_rol("lec", "LECTURA")}
    for i in range(3):
        t = tarea(f"C{i}", c["Jefa de Control"], "CIERRE_DIA_HABIL", proceso_nombre="Costeo", n=1)
        t.minutos_estimados = 300
        t.save()
    t = tarea("K", c["Contador Senior"], "CIERRE_DIA_HABIL", proceso_nombre="Costeo", n=5)
    t.minutos_estimados = 60
    t.save()
    o = tarea("O1", c["Contador Senior"], "DIARIA_HABIL", proceso_nombre="Compras")
    o.minutos_estimados = 120
    o.save()
    for t in Tarea.objects.select_related("proceso"):  # la misma clave que calculan el importador y el Mantenedor
        t.clave_estable = importador._clave(t.proceso.nombre, t.tarea_principal, t.subtarea)
        t.save()
    return {"u": u, "c": c}


def cli(u):
    c = Client()
    c.force_login(u)
    return c


def libro(r):
    return openpyxl.load_workbook(io.BytesIO(r.content))


def test_la_pantalla_muestra_hoy_propuesta_cambios_y_si_cabe(mundo):
    html = cli(mundo["u"]["jefa"]).get(reverse("informe_matriz"), {"mes": "2026-12"}).content.decode()
    for texto in ("Matriz del cierre", "Como está hoy", "Propuesta", "¿Cabe el cierre en la jornada del equipo?", "Cambios propuestos", "Descargar matriz (Excel)", "Jefa de Control", "Asistente Contable", "lunes a jueves 9 h y viernes 5 h", "80 h"):
        assert texto in html, texto
    assert 'class="celda rd"' in html  # la Jefa tiene 15 h el día 1: se marca en rojo en «Como está hoy»


def test_el_menu_ofrece_la_matriz_solo_a_gerente_y_jefatura(mundo):
    assert "Matriz del cierre" in cli(mundo["u"]["ger"]).get(reverse("hoy")).content.decode()
    assert "Matriz del cierre" not in cli(mundo["u"]["cont"]).get(reverse("hoy")).content.decode()


@pytest.mark.parametrize("nombre", ["informe_matriz", "informe_matriz_exportar"])
def test_solo_gerente_y_jefatura_ven_y_descargan_la_matriz(mundo, nombre):
    assert cli(mundo["u"]["cont"]).get(reverse(nombre)).status_code == 403
    assert cli(mundo["u"]["lectura"]).get(reverse(nombre)).status_code == 403
    assert Client().get(reverse(nombre)).status_code == 302
    assert cli(mundo["u"]["ger"]).get(reverse(nombre), {"mes": "2026-12"}).status_code == 200


def test_el_mes_invalido_cae_en_el_mes_actual(mundo):
    assert cli(mundo["u"]["jefa"]).get(reverse("informe_matriz"), {"mes": "basura"}).status_code == 200


def test_la_descarga_es_un_excel_con_todas_las_hojas_para_revisar(mundo):
    r = cli(mundo["u"]["jefa"]).get(reverse("informe_matriz_exportar"), {"mes": "2026-12"})
    assert r.status_code == 200 and "spreadsheetml" in r["Content-Type"] and "matriz_del_cierre_2026-12.xlsx" in r["Content-Disposition"]
    wb = libro(r)
    assert wb.sheetnames == ["Resumen", "Matriz hoy", "Matriz propuesta", "Detalle por día", "Cambios propuestos", "Alertas", "Planificación", "Instrucciones"]
    assert EventoAuditoria.objects.filter(accion="matriz.descargada").exists()
    hoja = wb["Matriz hoy"]
    cabecera = [c.value for c in hoja[4]]
    assert cabecera[0] == "Cargo" and any("jue 03-12" in str(c) for c in cabecera) and any("Reportes listos" in str(c) for c in cabecera)
    jefa = next(f for f in hoja.iter_rows(min_row=5, values_only=True) if f[0] == "Jefa de Control")
    assert jefa[1] == 15.0  # 15 h el martes 01-12 (día hábil 1)
    assert hoja.cell(row=jefa_fila(hoja), column=2).fill.start_color.rgb.endswith("F8D7DA")  # en rojo


def jefa_fila(hoja):
    return next(i for i, f in enumerate(hoja.iter_rows(values_only=True), start=1) if f[0] == "Jefa de Control")


def test_el_resumen_dice_si_el_trabajo_cabe_o_cuanto_falta(mundo):
    wb = libro(cli(mundo["u"]["jefa"]).get(reverse("informe_matriz_exportar"), {"mes": "2026-12"}))
    textos = " ".join(str(c.value) for f in wb["Resumen"].iter_rows() for c in f if c.value)
    assert "Para revisar antes de entregarla" in textos and ("cabe en la jornada" in textos or "faltan" in textos) and "Desequilibrio" in textos


def test_la_hoja_planificacion_trae_la_propuesta_aplicada_y_se_puede_cargar(mundo):
    wb = libro(cli(mundo["u"]["jefa"]).get(reverse("informe_matriz_exportar"), {"mes": "2026-12"}))
    hoja = wb["Planificación"]
    filas = {f[0]: f for f in hoja.iter_rows(min_row=4, values_only=True) if f[0]}
    o1 = filas[Tarea.objects.get(subtarea="Subtarea O1").codigo]
    assert o1[12:15] == ("Reasignar", "Asistente Contable", "Contador Senior")  # compras: la analista cubre y el contador solo revisa
    # cargada, aplica la propuesta y deja la planificación como dice la hoja
    contenido = io.BytesIO()
    wb.save(contenido)
    jefa = mundo["u"]["jefa"]
    vp = excel_masivo.previsualizar_tareas(jefa, contenido.getvalue(), "matriz.xlsx")
    assert not vp.altas and not vp.bajas and len(vp.cambios) >= 1
    excel_masivo.aplicar_tareas(jefa, contenido.getvalue(), "matriz.xlsx")
    t = Tarea.objects.get(subtarea="Subtarea O1")
    assert (t.modo_cierre, t.cargo_cierre.nombre, t.cargo_revisa_cierre.nombre) == ("reasignar", "Asistente Contable", "Contador Senior")


def test_cargar_la_propuesta_y_volver_a_calcular_deja_menos_exceso(mundo):
    from nucleo.servicios import matriz
    antes = matriz.proponer(2026, 12)
    contenido = io.BytesIO()
    libro(cli(mundo["u"]["jefa"]).get(reverse("informe_matriz_exportar"), {"mes": "2026-12"})).save(contenido)
    excel_masivo.aplicar_tareas(mundo["u"]["jefa"], contenido.getvalue(), "matriz.xlsx")
    despues = matriz.construir(2026, 12)  # ahora la planificación guardada ya es la propuesta
    assert despues.exceso_total == pytest.approx(antes.despues.exceso_total, abs=0.01) and despues.exceso_total < antes.antes.exceso_total
