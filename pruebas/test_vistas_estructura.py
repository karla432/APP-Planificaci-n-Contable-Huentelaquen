"""Pantallas de la estructura: árbol y tabla con filtros, exportación, procesos con orden y dependencias, tareas y planificación."""
import io
from datetime import date

import openpyxl
import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import DependenciaProceso, EventoAuditoria, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import estructura, mantenedor
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))


@pytest.fixture
def mundo():
    u = {"jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", cargo("Jefa de Control"))), "ger": usuario_con_rol("ger", "GERENTE", persona("Ger", cargo("Gerente AyF"))),
         "cont": usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior"))), "lectura": usuario_con_rol("lec", "LECTURA"), "sin": usuario_con_rol("sin", None)}
    ven = estructura.crear_proceso(u["jefa"], "Ventas y sala de venta", "VEN")
    com = estructura.crear_proceso(u["jefa"], "Compras", "COM")
    tes = estructura.crear_proceso(u["jefa"], "Tesorería y bancos", "TES")
    for p, tareas in ((ven, {"Registro de ventas": ["Ingresar arqueo de caja", "Registrar diferencias de caja"], "Cierre de caja": ["Cuadrar caja"]}), (com, {"Registro de compras": ["Ingresar facturas"]})):
        for tarea, subs in tareas.items():
            for s in subs:
                mantenedor.crear_tarea(u["jefa"], mantenedor.DatosTarea(proceso_id=p.pk, tarea_principal=tarea, subtarea=s, cargo_ejecuta_id=cargo("Contador Senior").pk, tipo="CIERRE_DIA_HABIL", n=2))
    return {"u": u, "ven": ven, "com": com, "tes": tes}


def cli(u):
    c = Client()
    c.force_login(u)
    return c


def ver(mundo, quien="jefa", **params):
    html = cli(mundo["u"][quien]).get(reverse("planificacion"), params).content.decode()
    return html.split('aria-label="Filtros"', 1)[1].split("</form>", 1)[1] if 'aria-label="Filtros"' in html else html  # sin el formulario de filtros, que lista todos los procesos


# ---- Árbol y tabla --------------------------------------------------------------------------------------------------------


def test_el_arbol_muestra_los_tres_niveles_con_sus_codigos(mundo):
    html = ver(mundo, vista="arbol")
    for texto in ("01-VEN", "01-VEN.01", "01-VEN.01.001", "01-VEN.02.001", "02-COM.01.001", "Ingresar arqueo de caja", "Registro de ventas", "no depende de otro"):
        assert texto in html, texto
    assert html.index("01-VEN.01.001") < html.index("01-VEN.01.002") < html.index("01-VEN.02.001") < html.index("02-COM.01.001")


def test_la_tabla_muestra_los_tres_niveles_en_filas(mundo):
    html = ver(mundo, vista="tabla")
    assert html.count('class="nivel1"') == 3 and html.count('class="nivel2"') == 3 and html.count('class="nivel3"') == 4
    assert "Cuadrar caja" in html and "Pendiente" in html


def test_los_procesos_sin_tareas_se_ven_en_el_arbol(mundo):
    assert "03-TES" in ver(mundo)  # un proceso nuevo todavía vacío no desaparece


@pytest.mark.parametrize("quien", ["jefa", "ger", "cont", "lectura"])
def test_todos_los_perfiles_ven_la_planificacion(mundo, quien):
    assert cli(mundo["u"][quien]).get(reverse("planificacion")).status_code == 200


def test_sin_perfil_o_sin_sesion_no_ve_nada(mundo):
    assert cli(mundo["u"]["sin"]).get(reverse("planificacion")).status_code == 403
    assert Client().get(reverse("planificacion")).status_code == 302


# ---- Filtros --------------------------------------------------------------------------------------------------------------


def test_filtrar_por_proceso(mundo):
    html = ver(mundo, vista="tabla", proceso=mundo["com"].pk)
    assert "02-COM.01.001" in html and "01-VEN.01.001" not in html


def test_filtrar_por_tarea_y_por_subtarea(mundo):
    html = ver(mundo, vista="tabla", tarea="cierre de caja")
    assert "01-VEN.02.001" in html and "01-VEN.01.001" not in html and "02-COM" not in html
    html = ver(mundo, vista="tabla", subtarea="arqueo")
    assert "Ingresar arqueo de caja" in html and "Cuadrar caja" not in html


def test_filtrar_por_rango_de_orden_de_ejecucion(mundo):
    html = ver(mundo, vista="tabla", orden_desde=2, orden_hasta=3)
    assert "02-COM" in html and "03-TES" in html and "01-VEN" not in html


def test_filtrar_por_estado_y_por_activos(mundo):
    t = Tarea.objects.get(codigo="01-VEN.01.002")
    t.estado_plan = "en_curso"
    t.save()
    html = ver(mundo, vista="tabla", estado="en_curso")
    assert "01-VEN.01.002" in html and "01-VEN.01.001" not in html
    estructura.fijar_activa_tarea_principal(mundo["u"]["jefa"], TareaPrincipal.objects.get(codigo="02-COM.01"), False)
    assert "02-COM.01.001" not in ver(mundo, vista="tabla")  # por defecto, solo lo activo
    assert "02-COM.01.001" in ver(mundo, vista="tabla", activos="todos") and "02-COM.01.001" in ver(mundo, vista="tabla", activos="0")


def test_buscar_por_codigo_incluso_uno_anterior_despues_de_reordenar(mundo):
    estructura.reordenar_procesos(mundo["u"]["jefa"], [mundo["com"].pk, mundo["ven"].pk, mundo["tes"].pk])
    assert "02-VEN.01.001" in ver(mundo, vista="tabla", q="02-VEN.01.001")
    html = ver(mundo, vista="tabla", q="01-VEN.01.001")  # el código de antes del reordenamiento sigue encontrando la subtarea
    assert "02-VEN.01.001" in html and "02-COM" not in html


def test_un_filtro_con_valores_raros_no_rompe_la_pantalla(mundo):
    assert cli(mundo["u"]["jefa"]).get(reverse("planificacion"), {"proceso": "x", "orden_desde": "abc", "estado": "inventado", "activos": "zzz"}).status_code == 200


# ---- Exportar ------------------------------------------------------------------------------------------------------------


def test_exportar_la_planificacion_a_excel_con_los_filtros(mundo):
    r = cli(mundo["u"]["jefa"]).get(reverse("planificacion_exportar"), {"proceso": mundo["ven"].pk})
    assert r.status_code == 200 and "spreadsheetml" in r["Content-Type"] and "planificacion_20261204.xlsx" in r["Content-Disposition"]
    hoja = openpyxl.load_workbook(io.BytesIO(r.content))["Planificación"]
    filas = [[c.value for c in f] for f in hoja.iter_rows(min_row=2)]
    assert [f[1] for f in filas] == ["01-VEN", "01-VEN.01", "01-VEN.01.001", "01-VEN.01.002", "01-VEN.02", "01-VEN.02.001"]
    assert [c.value for c in hoja[1]][:7] == ["Nivel", "Código", "Orden del proceso", "Proceso", "Tarea", "Subtarea", "Responsable"]
    assert filas[0][0] == "Proceso" and filas[2][0] == "Subtarea" and filas[2][5] == "Ingresar arqueo de caja"
    assert EventoAuditoria.objects.filter(accion="planificacion.exportada").exists()


def test_exportar_solo_gerente_y_jefatura(mundo):
    for quien in ("cont", "lectura"):
        assert cli(mundo["u"][quien]).get(reverse("planificacion_exportar")).status_code == 403


# ---- Procesos: orden, dependencias, tareas ------------------------------------------------------------------------------------


def test_la_lista_de_procesos_muestra_orden_codigo_y_botones_de_mover(mundo):
    html = cli(mundo["u"]["jefa"]).get(reverse("mant_procesos")).content.decode()
    assert "01-VEN" in html and "02-COM" in html and "▲" in html and "▼" in html and "catálogo base" in html and 'pattern="[A-Za-z]{3}"' in html


def test_subir_y_bajar_un_proceso_actualiza_los_codigos(mundo):
    c = cli(mundo["u"]["jefa"])
    r = c.post(reverse("mant_procesos"), {"accion": "bajar", "proceso": mundo["ven"].pk}, follow=True)
    assert "02-VEN" in r.content.decode()
    assert Tarea.objects.filter(codigo="02-VEN.01.001").exists() and Tarea.objects.filter(codigo="01-COM.01.001").exists()


def test_crear_un_proceso_con_sigla_y_con_sigla_invalida(mundo):
    c = cli(mundo["u"]["jefa"])
    c.post(reverse("mant_procesos"), {"accion": "crear", "nombre": "Impuestos", "sigla": "imp"})
    assert Proceso.objects.get(nombre="Impuestos").codigo == "04-IMP"
    r = c.post(reverse("mant_procesos"), {"accion": "crear", "nombre": "Otro", "sigla": "XY"}, follow=True)
    assert "3 letras" in r.content.decode() and not Proceso.objects.filter(nombre="Otro").exists()


def test_cargar_el_catalogo_base_desde_la_pantalla(mundo):
    r = cli(mundo["u"]["jefa"]).post(reverse("mant_procesos"), {"accion": "catalogo"}, follow=True)
    assert "Catálogo base" in r.content.decode() and Proceso.objects.filter(sigla="CIE").exists()
    assert Proceso.objects.filter(sigla="VEN").count() == 1


def test_el_detalle_del_proceso_guarda_datos_de_planificacion(mundo):
    c = cli(mundo["u"]["jefa"])
    r = c.post(reverse("mant_proceso_detalle", args=[mundo["ven"].pk]), {"accion": "guardar", "nombre": "Ventas y sala de venta", "sigla": "VTA", "responsable": cargo("Contador Senior").pk,
                                                                         "estado_plan": "en_curso", "fecha_inicio": "2026-12-01", "fecha_termino": "2026-12-08", "observaciones": "Cierre"}, follow=True)
    p = Proceso.objects.get(pk=mundo["ven"].pk)
    assert p.codigo == "01-VTA" and p.estado_plan == "en_curso" and p.fecha_termino == date(2026, 12, 8) and "01-VTA" in r.content.decode()
    assert Tarea.objects.filter(codigo="01-VTA.01.001").exists()


def test_el_detalle_rechaza_fechas_incoherentes_y_fechas_mal_escritas(mundo):
    c = cli(mundo["u"]["jefa"])
    base = {"accion": "guardar", "nombre": "Compras", "sigla": "COM", "estado_plan": "pendiente"}
    r = c.post(reverse("mant_proceso_detalle", args=[mundo["com"].pk]), {**base, "fecha_inicio": "2026-12-08", "fecha_termino": "2026-12-01"}, follow=True)
    assert "no puede ser anterior" in r.content.decode()
    r = c.post(reverse("mant_proceso_detalle", args=[mundo["com"].pk]), {**base, "fecha_inicio": "no-es-fecha"}, follow=True)
    assert "no es válida" in r.content.decode()
    assert Proceso.objects.get(pk=mundo["com"].pk).fecha_inicio is None


def test_dependencias_desde_la_pantalla_y_secuencia_de_ejecucion(mundo):
    c = cli(mundo["u"]["jefa"])
    url = reverse("mant_proceso_detalle", args=[mundo["tes"].pk])
    c.post(url, {"accion": "dependencias", "depende_de": [mundo["ven"].pk, mundo["com"].pk]})
    assert DependenciaProceso.objects.filter(proceso=mundo["tes"]).count() == 2
    html = c.get(reverse("mant_procesos")).content.decode()
    assert "Etapa 1" in html and "en paralelo" in html and "Etapa 2" in html
    # un ciclo o un prerrequisito posterior se rechaza con un mensaje
    r = c.post(reverse("mant_proceso_detalle", args=[mundo["ven"].pk]), {"accion": "dependencias", "depende_de": [mundo["tes"].pk]}, follow=True)
    assert "va después en el orden" in r.content.decode() and DependenciaProceso.objects.count() == 2
    assert "Etapa 1" in ver(mundo)  # y la planificación también muestra el orden y el paralelismo


def test_tareas_desde_la_pantalla_crear_guardar_y_desactivar(mundo):
    c = cli(mundo["u"]["jefa"])
    url = reverse("mant_proceso_detalle", args=[mundo["ven"].pk])
    c.post(url, {"accion": "tarea_crear", "nombre": "Registro contable"})
    tp = TareaPrincipal.objects.get(codigo="01-VEN.03")
    c.post(url, {"accion": "tarea_guardar", "tarea": tp.pk, "nombre": "Registro contable de ventas", "estado_plan": "completado", "fecha_inicio": "2026-12-01", "observaciones": "ok"})
    tp.refresh_from_db()
    assert (tp.nombre, tp.estado_plan, tp.fecha_inicio) == ("Registro contable de ventas", "completado", date(2026, 12, 1))
    uno = TareaPrincipal.objects.get(codigo="01-VEN.01")
    c.post(url, {"accion": "tarea_activa", "tarea": uno.pk, "valor": "0"})
    assert not Tarea.objects.filter(padre=uno, activa=True).exists()
    html = c.get(url).content.decode()
    assert "01-VEN.03" in html and "Inactiva" in html and "Activar" in html


def test_activar_y_desactivar_un_proceso_desde_la_pantalla(mundo):
    c = cli(mundo["u"]["jefa"])
    url = reverse("mant_proceso_detalle", args=[mundo["ven"].pk])
    c.post(url, {"accion": "activo", "valor": "0"})
    assert not Proceso.objects.get(pk=mundo["ven"].pk).activo and not Tarea.objects.filter(proceso=mundo["ven"], activa=True).exists()
    c.post(url, {"accion": "activo", "valor": "1", "con_hijos": "on"})
    assert Tarea.objects.filter(proceso=mundo["ven"], activa=True).count() == 3


def test_solo_gerente_y_jefatura_abren_el_detalle_y_cambian_el_orden(mundo):
    for quien in ("cont", "lectura"):
        c = cli(mundo["u"][quien])
        assert c.get(reverse("mant_proceso_detalle", args=[mundo["ven"].pk])).status_code == 403
        assert c.post(reverse("mant_procesos"), {"accion": "bajar", "proceso": mundo["ven"].pk}).status_code == 403
    assert Proceso.objects.get(pk=mundo["ven"].pk).orden == 1


# ---- Subtarea: planificación ------------------------------------------------------------------------------------------------


def test_el_formulario_de_subtarea_pide_estado_fechas_y_observaciones_y_sugiere_las_tareas_existentes(mundo):
    c = cli(mundo["u"]["jefa"])
    html = c.get(reverse("mant_tarea_nueva")).content.decode()
    assert 'name="estado_plan"' in html and 'name="fecha_inicio"' in html and 'name="observaciones"' in html and '<option value="Registro de ventas">' in html
    r = c.post(reverse("mant_tarea_nueva"), {"proceso": mundo["ven"].pk, "tarea_principal": "Registro de ventas", "subtarea": "Validar documentos de venta", "cargo_ejecuta": cargo("Contador Senior").pk,
                                             "tipo": "CIERRE_DIA_HABIL", "n": "2", "activa": "on", "estado_plan": "en_curso", "fecha_inicio": "2026-12-02", "fecha_termino": "2026-12-03",
                                             "observaciones": "Prioritaria"}, follow=True)
    t = Tarea.objects.get(subtarea="Validar documentos de venta")
    assert t.codigo == "01-VEN.01.003" and t.estado_plan == "en_curso" and t.fecha_termino == date(2026, 12, 3) and t.observaciones == "Prioritaria" and "01-VEN.01.003" in r.content.decode()


def test_la_subtarea_rechaza_fechas_incoherentes(mundo):
    r = cli(mundo["u"]["jefa"]).post(reverse("mant_tarea_nueva"), {"proceso": mundo["ven"].pk, "tarea_principal": "X", "subtarea": "Y", "cargo_ejecuta": cargo("Contador Senior").pk, "tipo": "DIARIA_HABIL",
                                                                   "activa": "on", "fecha_inicio": "2026-12-05", "fecha_termino": "2026-12-01"})
    assert "no puede ser anterior" in r.content.decode() and not Tarea.objects.filter(subtarea="Y").exists()
