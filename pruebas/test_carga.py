"""Carga del equipo: horas estimadas contra capacidad (160 h al mes) y carga del cierre por día hábil. Todo es estimación."""
import pytest
from django.test import Client
from django.urls import reverse

from nucleo.servicios import carga, parametros
from pruebas.ayudas import cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def revision_de_15_minutos():
    """Estas pruebas miden el mecanismo de la revisión con 15 minutos; el valor general real es 0 (va dentro de las horas de quien ejecuta)."""
    parametros.guardar("minutos_revision", "15", usuario=None, confirmado=True)


def con_horas(t, minutos, ejecuciones, **cambios):
    t.minutos_estimados, t.ejecuciones_mes = minutos, ejecuciones
    for k, v in cambios.items():
        setattr(t, k, v)
    t.save()
    return t


@pytest.fixture
def mundo():
    cont, ger, jefa, bodega = cargo("Contador Senior"), cargo("Gerente AyF"), cargo("Jefa de Control"), cargo("Bodega", externo=True)
    for orden, c in enumerate((ger, jefa, cont), start=1):
        c.orden = orden
        c.save()
    con_horas(tarea("TAR-0001", cont, "DIARIA_HABIL", revisa=ger), 60, 21)  # 21 h al mes; el Gerente revisa 15 min cada vez = 5,25 h
    con_horas(tarea("TAR-0002", cont, "CIERRE_DIA_HABIL", revisa=ger, n=3), 30, 1)  # 0,5 h el día 3; revisión 0,25 h (15 min)
    con_horas(tarea("TAR-0003", ger, "CIERRE_DIA_HABIL", n=3), 120, 1)  # 2 h el día 3, sin revisor
    con_horas(tarea("TAR-0004", bodega, "CIERRE_DIA_HABIL", revisa=ger, n=3), 60, 1)  # de un externo: no entra a la capacidad, pero el revisor sí revisa
    con_horas(tarea("TAR-0005", cont, "CIERRE_DIA_HABIL", n=4), 600, 1, activa=False)  # inactiva: no cuenta
    tarea("TAR-0006", cont, "CIERRE_DIA_HABIL", n=4)  # sin horas: se avisa, no se inventa
    return {"cont": cont, "ger": ger, "jefa": jefa}


def fila(filas, nombre):
    return next(f for f in filas if f.cargo.nombre == nombre)


def test_horas_al_mes_de_ejecucion_y_de_revision_por_cargo(mundo):
    filas = carga.por_cargo()
    c, g = fila(filas, "Contador Senior"), fila(filas, "Gerente AyF")
    assert (c.horas_ejecucion, c.horas_revision, c.total) == (pytest.approx(21.5), 0, pytest.approx(21.5))
    assert g.horas_ejecucion == pytest.approx(2) and g.horas_revision == pytest.approx(5.25 + 0.25 + 0.25)
    assert (c.tareas_ejecuta, g.tareas_revisa) == (3, 3)


def test_la_ocupacion_es_horas_sobre_160_y_el_semaforo_trae_texto(mundo):
    c = fila(carga.por_cargo(), "Contador Senior")
    assert c.capacidad == 160 and c.ocupacion_pct == pytest.approx(13.4, abs=0.1) and c.semaforo == "verde"
    con_horas(tarea("TAR-0090", mundo["cont"], "DIARIA_HABIL"), 420, 21)  # +147 h
    assert fila(carga.por_cargo(), "Contador Senior").semaforo == "ambar"  # 168,5 h = 105 %: al límite, sobre el tope de 160 h


@pytest.mark.parametrize("horas,esperado", [(100, "verde"), (144, "ambar"), (160, "ambar"), (176, "ambar"), (177, "rojo")])
def test_umbrales_del_semaforo_de_carga(horas, esperado):
    assert carga.semaforo_de_carga(horas, 160) == esperado  # verde bajo 90 %, ámbar hasta 110 %, rojo sobre 110 %


def test_los_externos_no_tienen_capacidad_y_las_tareas_sin_horas_se_avisan(mundo):
    filas = carga.por_cargo()
    assert "Bodega" not in [f.cargo.nombre for f in filas]
    assert carga.tareas_sin_horas() == 1  # TAR-0006


def test_se_listan_en_el_orden_de_los_cargos(mundo):
    assert [f.cargo.nombre for f in carga.por_cargo()] == ["Gerente AyF", "Jefa de Control", "Contador Senior"]


def test_carga_del_cierre_por_dia_habil_con_la_capacidad_que_deja_la_operacion(mundo):
    cierre = carga.por_dia_de_cierre(2026, 12)
    g, c = fila(cierre, "Gerente AyF"), fila(cierre, "Contador Senior")
    assert g.horas[3] == pytest.approx(2 + 0.25 + 0.25) and c.horas[3] == pytest.approx(0.5)
    assert g.horas[1] == 0 and len(g.horas) == 10  # del día hábil 1 (DH01) a la entrega al Directorio (DH10)
    assert c.disponible_por_dia == pytest.approx(160 / 21 - 21 / 21, abs=0.01)  # la operación diaria ya ocupa 1 h por día
    assert g.disponible_por_dia == pytest.approx(160 / 21, abs=0.01)


def test_un_dia_sobre_la_capacidad_se_marca(mundo):
    con_horas(tarea("TAR-0091", mundo["cont"], "CIERRE_DIA_HABIL", n=5), 480, 1)  # 8 h el día 5, y le quedan 6,6 h
    c = fila(carga.por_dia_de_cierre(), "Contador Senior")
    assert c.sobrecargados() == [5]


def test_los_parametros_de_carga_son_pendientes_de_confirmar():
    assert parametros.entero("horas_disponibles_mes") == 160 and parametros.entero("minutos_revision") == 15  # (fijado por la prueba)
    assert parametros.estado("horas_disponibles_mes") == "pendiente_confirmar"


# ---- Pantalla ----------------------------------------------------------------------------------------------


def test_la_pantalla_dice_quien_lleva_mas_carga_y_marca_todo_como_estimado(mundo):
    c = Client()
    c.force_login(usuario_con_rol("lectura", "LECTURA"))
    html = c.get(reverse("informe_carga")).content.decode()
    assert "Carga del equipo" in html and "Estimado" in html and "160" in html
    assert "Contador Senior" in html and "21,5" in html  # horas con coma decimal
    assert "1 tarea sin horas estimadas" in html
    assert "Verde" in html or "Dentro de su capacidad" in html


def test_la_pantalla_exige_perfil(mundo):
    c = Client()
    c.force_login(usuario_con_rol("fantasma", None))
    assert c.get(reverse("informe_carga")).status_code == 403


def test_la_revision_usa_los_minutos_de_la_tarea_y_si_no_hay_los_15_generales(mundo):
    """Karla (02-11-2026): la revisión es un tiempo real por tarea (ej. 15 min), no un % de lo que demora quien la hace."""
    ger = fila(carga.por_cargo(), "Gerente AyF")
    assert ger.horas_revision == pytest.approx(5.75)
    t = tarea("TAR-0100", mundo["cont"], "CIERRE_DIA_HABIL", revisa=mundo["ger"], n=3)
    con_horas(t, 120, 1)  # la tarea demora 2 h; revisar toma el valor general: 15 min, no el 25 % (30 min)
    assert fila(carga.por_cargo(), "Gerente AyF").horas_revision == pytest.approx(5.75 + 0.25)
    con_horas(t, 120, 1, minutos_revision=45)  # esta tarea se revisa en 45 min
    assert fila(carga.por_cargo(), "Gerente AyF").horas_revision == pytest.approx(5.75 + 0.75)
    con_horas(t, 120, 1, minutos_revision=0)  # 0 = la revisión no toma tiempo
    assert fila(carga.por_cargo(), "Gerente AyF").horas_revision == pytest.approx(5.75)


def test_revision_por_dia_del_cierre_y_sin_horas_de_ejecucion_no_inventa(mundo):
    assert carga.horas_de_revision(tarea("TAR-0101", mundo["cont"], "CIERRE_DIA_HABIL", revisa=mundo["ger"], n=3)) == 0  # sin tiempo de ejecución estimado
    t = con_horas(tarea("TAR-0102", mundo["cont"], "CIERRE_DIA_HABIL", revisa=mundo["ger"], n=3), 90, 1, minutos_revision=20)
    assert carga.horas_de_revision(t) == pytest.approx(20 / 60)
    t.minutos_revision = None
    assert carga.horas_de_revision(t) == pytest.approx(0.25)
    assert carga.horas_de_revision(t, por_defecto_min=30) == pytest.approx(0.5)
