"""Menú Informes: Panel del cierre y Cumplimiento por colaborador (visibles para todo el equipo, solo lectura)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Ocurrencia
from nucleo.servicios import periodos
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db
HOY = date(2026, 12, 4)  # viernes, día hábil 4; el 08-12 es feriado
SCL = ZoneInfo("America/Santiago")


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: HOY)


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa de Control"), cargo("Contador Senior"), cargo("Gerente AyF")
    bodega = cargo("Bodega", externo=True)
    p = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont)}
    u = {"cont": usuario_con_rol("cont", "COLABORADOR", p["cont"]), "jefa": usuario_con_rol("jefa", "JEFATURA", p["jefa"]), "lectura": usuario_con_rol("lectura", "LECTURA")}
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=3)  # vencida y sin hacer
    tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=4)  # vence hoy, hecha a tiempo
    tarea("TAR-0003", jefa, "CIERRE_HITO", revisa=ger, proceso_nombre="Conciliación", n=8)  # aún no vence (miércoles 09-12)
    tarea("TAR-0004", cont, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Conciliación", n=1)  # hecha tarde
    tarea("TAR-0005", bodega, "CIERRE_DIA_HABIL", revisa=jefa, proceso_nombre="Compras", n=2)  # externo, sin recibir
    periodos.abrir_mes(2026, 12, usuario=None)
    o = {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}
    for codigo, dia in (("TAR-0002", 4), ("TAR-0004", 2)):
        hora = datetime(2026, 12, dia, 10, 0, tzinfo=SCL)
        Ocurrencia.objects.filter(pk=o[codigo].pk).update(estado="hecha", primera_hecha_en=hora, hecha_en=hora)
    return {"u": u}


def ver(usuario, nombre, **params):
    c = Client()
    c.force_login(usuario)
    r = c.get(reverse(nombre), params)
    assert r.status_code == 200, r.status_code
    return r.content.decode()


# ---- Panel del cierre -----------------------------------------------------------------------------


def test_el_panel_muestra_el_cierre_del_mes_y_los_dias_habiles_que_faltan(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Cierre contable" in html and "diciembre 2026" in html
    assert "día hábil 4" in html
    # Los días 8, 9 y 10 son días del mes (Karla, 01-11-2026): el 08-12 es feriado, así que el día 8 pasa al 09-12, el 9 al 10-12 y el 10 al 11-12.
    assert "faltan para los reportes listos (día 8, 09-12): <strong>2 días hábiles" in html and "para el Directorio (día 10, 11-12): <strong>4 días hábiles" in html


def test_el_panel_tiene_la_ruta_del_cierre_con_sus_fechas(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Ruta del cierre" in html
    for texto in ("Día 1", "Día 4", "Día 8", "01-12-2026", "09-12-2026", "10-12-2026", "11-12-2026", "Reportes listos", "Entrega al Gerente General", "Informes al Directorio"):
        assert texto in html, texto


def test_el_panel_resume_avance_atrasadas_y_cumplimiento_del_equipo(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Avance del cierre" in html and "2 de 5" in html  # hechas 2 de 5 tareas del cierre
    assert "Atrasadas sin hacer" in html
    assert "Cumplimiento a tiempo del equipo" in html and "0 de 2" in html  # TAR-0001 y TAR-0004 vencidas, ninguna a tiempo (la del externo no entra al equipo)


def test_el_panel_muestra_el_avance_por_proceso_con_texto(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Avance por proceso" in html and "Compras" in html and "Conciliación" in html
    assert "Atrasado" in html and "Por vencer" in html


def test_el_panel_incluye_el_cumplimiento_por_colaborador(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Cumplimiento por colaborador" in html and "Contadora" in html and "Meta 95%" in html


def test_un_mes_sin_abrir_lo_dice(mundo):
    assert "no se ha abierto" in ver(mundo["u"]["lectura"], "informe_panel", mes="2027-03").lower()


# ---- Cumplimiento por colaborador -----------------------------------------------------------------


def test_el_cumplimiento_lista_a_cada_colaborador_con_su_porcentaje_y_texto(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Contadora" in html and "Jefa" in html
    assert "0 de 2" in html  # la Contadora: TAR-0001 (sin hacer) y TAR-0004 (tarde)
    assert "Muestra insuficiente" in html and "Sin datos" in html


def test_los_externos_se_miden_aparte_y_no_entran_en_el_cuadro_del_equipo(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Insumos de responsables externos" in html and "Bodega" in html
    cuadro = html.split("Insumos de responsables externos")[0]
    assert "Bodega" not in cuadro


def test_el_cumplimiento_incluye_la_revision(mundo):
    html = ver(mundo["u"]["cont"], "informe_cumplimiento")
    assert "Cumplimiento de revisión" in html and "Jefa de Control" in html


def test_cualquier_perfil_con_acceso_puede_verlo_pero_sin_perfil_no(mundo):
    sin = usuario_con_rol("fantasma", None)
    c = Client()
    c.force_login(sin)
    assert c.get(reverse("informe_panel")).status_code == 403
    assert c.get(reverse("informe_cumplimiento")).status_code == 403


def test_el_panel_lista_los_feriados_confirmados_del_mes_y_no_inventa_ninguno(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Feriados del mes" in html and "08-12-2026" in html and "25-12-2026" in html
    from nucleo.models import Feriado
    Feriado.objects.all().delete()
    sin = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Feriados del mes" not in sin and "08 de diciembre" not in sin


def test_el_cumplimiento_lista_a_las_personas_en_el_orden_de_los_cargos(mundo):
    """Gerente AyF, Jefa, Contador Senior, Asistente Contable: el orden que definió Karla, no el alfabético."""
    from nucleo.models import Cargo
    for nombre, orden in (("Gerente AyF", 1), ("Jefa de Control", 2), ("Contador Senior", 3), ("Asistente Contable", 4)):
        Cargo.objects.update_or_create(nombre=nombre, defaults={"orden": orden})
    asistente = cargo("Asistente Contable")
    ger = persona("Aaa Gerente", cargo("Gerente AyF"))
    pa = persona("Zzz Asistente", asistente)
    tarea("TAR-0090", asistente, "CIERRE_DIA_HABIL", revisa=cargo("Jefa de Control"), n=1)
    tarea("TAR-0091", cargo("Gerente AyF"), "CIERRE_DIA_HABIL", revisa=cargo("Jefa de Control"), n=1)
    periodos.abrir_mes(2026, 12, usuario=None)
    html = ver(mundo["u"]["lectura"], "informe_cumplimiento")
    cuadro = html.split("Cumplimiento de revisión")[0]
    posiciones = [cuadro.index(n) for n in ("Aaa Gerente", "Jefa", "Contadora", "Zzz Asistente")]
    assert posiciones == sorted(posiciones)


def test_el_titular_resume_el_cierre_contra_el_plan_y_hay_cifra_grande(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Día hábil 4: el cierre va 40 puntos bajo el plan." in html  # van 2 de 5 (40 %) y el plan pedía 4 de 5 (80 %)
    assert 'class="cifra-grande">40<' in html and "el plan esperaba 80 % a hoy" in html


def test_requiere_tu_atencion_muestra_lo_que_el_perfil_debe_hacer(mundo):
    jefa = ver(mundo["u"]["jefa"], "informe_panel")
    atencion = jefa.split("Requiere atención")[1]
    assert "Subtarea TAR-0002" in atencion and "Por revisar" in atencion  # la Jefa revisa lo hecho por la Contadora
    assert "Subtarea TAR-0001" in atencion  # y se ve lo atrasado, agrupado por quien debe actuar
    from nucleo.models import Cargo
    Cargo.objects.filter(nombre="Jefa de Control").update(orden=2)
    Cargo.objects.filter(nombre="Contador Senior").update(orden=3)
    atencion = ver(mundo["u"]["jefa"], "informe_panel").split("Requiere atención")[1]
    assert atencion.index("Jefa de Control") < atencion.index("Contador Senior")  # ordenado por responsable, en el orden de los cargos
    cont = ver(mundo["u"]["cont"], "informe_panel")
    assert "Mis pendientes" in cont and "Subtarea TAR-0001" in cont.split("Mis pendientes")[1]


# ---- Mejoras del QA de Karla (01-11-2026) -------------------------------------------------------------


def test_el_panel_no_repite_el_cumplimiento_por_colaborador_y_remite_a_su_pantalla(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel")
    assert "Hechas a tiempo ÷ tareas que ya vencieron" not in html and "Informes → Cumplimiento por colaborador" in html
    assert "Cómo se calcula" in ver(mundo["u"]["lectura"], "informe_cumplimiento")  # sigue en su propio menú


def test_se_pueden_ver_las_atrasadas_pinchando_el_numero(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel", ver="atrasadas")
    lista = html.split('id="listado"')[1].split("</section>")[0]
    assert "Tareas atrasadas" in lista and "Subtarea TAR-0001" in lista and "Atrasada" in lista and "Subtarea TAR-0002" not in lista


def test_se_ven_las_tareas_de_un_dia_pinchando_el_dia_de_la_ruta(mundo):
    html = ver(mundo["u"]["lectura"], "informe_panel", fecha="2026-12-03")
    lista = html.split('id="listado"')[1].split("</section>")[0]
    assert "03-12-2026" in lista and "Subtarea TAR-0001" in lista and "Subtarea TAR-0002" not in lista  # TAR-0002 vence el 04-12
    assert 'href="?mes=2026-12&fecha=2026-12-03#listado"' in html  # el día de la ruta es un enlace


def test_el_avance_por_proceso_sigue_el_orden_de_los_codigos(mundo):
    from nucleo.servicios import estructura, kpi
    from nucleo.models import Periodo, Proceso
    periodo = Periodo.objects.get()
    nombres = [a.proceso for a in kpi.avance_por_proceso(periodo, HOY)]
    assert nombres == list(Proceso.objects.filter(nombre__in=nombres).values_list("nombre", flat=True))  # mismo orden que el de ejecución
    primero = Proceso.objects.filter(nombre__in=nombres).last()
    estructura.reordenar_procesos(mundo["u"]["jefa"], [primero.pk] + [p.pk for p in Proceso.objects.exclude(pk=primero.pk)])
    assert [a.proceso for a in kpi.avance_por_proceso(periodo, HOY)][0] == primero.nombre
    primero.refresh_from_db()
    assert primero.codigo.startswith("01-") and f"{primero.codigo}</strong> · {primero.nombre}" in ver(mundo["u"]["lectura"], "informe_panel")


@pytest.mark.parametrize("nombre,params", [("informe_panel", {}), ("informe_panel", {"ver": "atrasadas"}), ("informe_panel", {"fecha": "2026-12-03"}), ("informe_cronograma", {}),
                                           ("informe_cronograma", {"vista": "semana"}), ("informe_cronograma", {"vista": "mes"}), ("informe_tablero", {}), ("informe_carga", {}),
                                           ("informe_cumplimiento", {}), ("hoy", {}), ("semana", {}), ("mes", {})])
def test_las_pantallas_tienen_sus_etiquetas_div_bien_cerradas(mundo, nombre, params):
    """Un </div> de más saca el contenido de su sitio y el menú lateral lo tapa (pasó en el panel). Se cuida en todas las pantallas del cierre."""
    html = ver(mundo["u"]["lectura"] if nombre.startswith("informe") else mundo["u"]["cont"], nombre, **params)
    assert html.count("<div") == html.count("</div>"), (nombre, params)
