"""KPI de cumplimiento (docs/f1/03_kpi_roles_sod.md §1). Todas las fechas de negocio son de America/Santiago."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from nucleo.models import Ocurrencia, Periodo
from nucleo.servicios import kpi, parametros
from pruebas.ayudas import anio_abierto, cargo, persona, tarea

pytestmark = pytest.mark.django_db
SCL = ZoneInfo("America/Santiago")
HOY = date(2026, 12, 11)  # viernes: lo del 4 al 10 de diciembre ya venció


def local(dia, hora=12, minuto=0, mes=12):
    return datetime(2026, mes, dia, hora, minuto, tzinfo=SCL)


@pytest.fixture
def base():
    anio_abierto()
    p = Periodo.objects.create(anio=2026, mes=12, inicio_medicion=date(2026, 12, 1))
    cont, jefa, bodega = cargo("Contadora Senior"), cargo("Jefa Gestión y Control"), cargo("Bodega", externo=True)
    c = persona("Contadora", cont)
    j = persona("Jefa", jefa)
    return {"p": p, "cont": cont, "jefa": jefa, "bodega": bodega, "c": c, "j": j, "n": 0}


def ocurrencia(b, fecha, colaborador="c", cargo_="cont", estado="pendiente", primera=None, proceso="Proceso de prueba", **extra):
    b["n"] += 1
    t = tarea(f"TAR-{b['n']:04d}", b[cargo_], "CIERRE_DIA_HABIL", n=1, proceso_nombre=proceso)
    return Ocurrencia.objects.create(
        tarea=t, periodo=b["p"], fecha_limite=fecha, cargo_ejecuta=b[cargo_], colaborador=b[colaborador] if colaborador else None,
        cargo_revisa=extra.pop("cargo_revisa", None), estado=estado, primera_hecha_en=primera, hecha_en=primera, **extra,
    )


def kpi_de(b, quien="c"):
    return {k.colaborador.pk: k for k in kpi.por_colaborador(b["p"], HOY)}[b[quien].pk]


def test_hecha_el_dia_del_vencimiento_es_a_tiempo(base):
    ocurrencia(base, date(2026, 12, 4), estado="hecha", primera=local(4, 17))
    k = kpi_de(base)
    assert (k.vencidas, k.a_tiempo, k.completas) == (1, 1, 1)


def test_hecha_tarde_nunca_suma_a_tiempo_pero_si_a_completitud(base):
    ocurrencia(base, date(2026, 12, 4), estado="hecha", primera=local(7, 9))
    k = kpi_de(base)
    assert (k.vencidas, k.a_tiempo, k.completas) == (1, 0, 1)


def test_lo_vencido_y_no_hecho_cuenta_en_el_denominador(base):
    ocurrencia(base, date(2026, 12, 4), estado="pendiente")
    ocurrencia(base, date(2026, 12, 3), estado="hecha", primera=local(3, 10))
    k = kpi_de(base)
    assert (k.vencidas, k.a_tiempo, k.pendientes_vencidas) == (2, 1, 1)
    assert k.a_tiempo_pct == 50


def test_lo_que_vence_hoy_o_despues_aun_no_cuenta(base):
    ocurrencia(base, HOY, estado="pendiente")
    ocurrencia(base, date(2026, 12, 14), estado="hecha", primera=local(10))  # hecha por adelantado
    k = kpi_de(base)
    assert k.vencidas == 0 and k.a_tiempo_pct is None


def test_no_aplica_aprobada_sale_del_denominador_y_se_mide_aparte(base):
    ocurrencia(base, date(2026, 12, 4), estado="no_aplica")
    ocurrencia(base, date(2026, 12, 3), estado="hecha", primera=local(3, 10))
    k = kpi_de(base)
    assert (k.vencidas, k.a_tiempo, k.no_aplica) == (1, 1, 1)
    assert k.tasa_no_aplica_pct == 50  # 1 de 2 tareas de la persona


def test_una_devuelta_conserva_su_a_tiempo_original_y_sube_la_tasa_de_devolucion(base):
    ocurrencia(base, date(2026, 12, 4), estado="devuelta", primera=local(4, 9), veces_devuelta=1)
    ocurrencia(base, date(2026, 12, 3), estado="revisada", primera=local(3, 9))
    k = kpi_de(base)
    assert k.a_tiempo == 2 and k.tasa_devolucion_pct == 50


def test_las_tareas_de_externos_no_entran_al_kpi_de_nadie_pero_se_miden_aparte(base):
    ocurrencia(base, date(2026, 12, 4), colaborador=None, cargo_="bodega", estado="hecha", primera=local(4, 10), tipo_marca="RECIBIDA")
    ocurrencia(base, date(2026, 12, 3), colaborador=None, cargo_="bodega", estado="pendiente", tipo_marca="RECIBIDA")
    assert kpi.por_colaborador(base["p"], HOY) == []
    insumos = {i.cargo.nombre: i for i in kpi.insumos_por_cargo_externo(base["p"], HOY)}
    assert (insumos["Bodega"].vencidas, insumos["Bodega"].a_tiempo) == (2, 1)


def test_la_fecha_se_mide_en_hora_de_chile_no_en_utc(base):
    # 23:30 del 04-12 en Santiago ya es 02:30 UTC del 05-12: sigue siendo a tiempo para un vencimiento del 04-12.
    ocurrencia(base, date(2026, 12, 4), estado="hecha", primera=local(4, 23, 30))
    # 00:30 del 05-12 en Santiago es tarde.
    ocurrencia(base, date(2026, 12, 3), estado="hecha", primera=local(4, 0, 30))
    k = kpi_de(base)
    assert (k.vencidas, k.a_tiempo) == (2, 1)


def test_el_cambio_de_horario_de_verano_no_mueve_el_vencimiento(base):
    # En Chile el horario de verano empieza el primer sábado de septiembre; se prueba con una marca de esa noche.
    p = Periodo.objects.create(anio=2026, mes=9, inicio_medicion=date(2026, 9, 1))
    t = tarea("TAR-DST", base["cont"], "CIERRE_DIA_HABIL", n=1)
    o = Ocurrencia.objects.create(tarea=t, periodo=p, fecha_limite=date(2026, 9, 5), cargo_ejecuta=base["cont"], colaborador=base["c"],
                                  estado="hecha", primera_hecha_en=datetime(2026, 9, 5, 23, 50, tzinfo=SCL))
    k = {x.colaborador.pk: x for x in kpi.por_colaborador(p, date(2026, 9, 10))}[base["c"].pk]
    assert k.a_tiempo == 1


@pytest.mark.parametrize(
    "a_tiempo,vencidas,esperado",
    [(20, 20, "verde"), (19, 20, "verde"), (18, 20, "ambar"), (36, 40, "ambar"), (17, 20, "rojo"), (0, 10, "rojo")],
)
def test_semaforo_con_los_umbrales_de_95_y_90(a_tiempo, vencidas, esperado):
    assert kpi.semaforo(a_tiempo, vencidas) == esperado


def test_semaforo_exacto_sin_errores_de_redondeo():
    assert kpi.semaforo(95, 100) == "verde"  # 95,0 %
    assert kpi.semaforo(19, 20) == "verde"  # 95 % exacto
    assert kpi.semaforo(94, 100) == "ambar"  # 94 %
    assert kpi.semaforo(9, 10) == "ambar" and kpi.semaforo(89, 100) == "rojo"


def test_con_muestra_chica_no_se_colorea_y_sin_datos_dice_sin_datos():
    assert kpi.semaforo(1, 2) == "muestra_insuficiente"  # el Gerente tiene 2 tareas
    assert kpi.semaforo(0, 0) == "sin_datos"
    parametros.guardar("minimo_muestra_semaforo", "2", usuario=None, confirmado=True)
    assert kpi.semaforo(1, 2) == "rojo"


def test_cumplimiento_de_revision_mide_contra_el_plazo_de_1_dia_habil(base):
    # La Jefa revisa. Hecha el lunes 07-12: plazo hasta el martes 08-12 (feriado) → miércoles 09-12.
    for dia_hecha, dia_rev in ((7, 9), (7, 10)):  # una a tiempo y una tarde
        ocurrencia(base, date(2026, 12, 7), estado="revisada", primera=local(dia_hecha, 10), cargo_revisa=base["jefa"],
                   primera_revision_en=local(dia_rev, 10))
    ocurrencia(base, date(2026, 12, 7), estado="hecha", primera=local(7, 11), cargo_revisa=base["jefa"])  # sin revisar y ya vencida
    rev = {r.cargo.nombre: r for r in kpi.cumplimiento_de_revision(base["p"], HOY)}["Jefa Gestión y Control"]
    assert (rev.debidas, rev.a_tiempo) == (3, 1)


def test_ruta_del_cierre_cuenta_hechas_sobre_total_por_dia(base):
    ocurrencia(base, date(2026, 12, 1), estado="revisada", primera=local(1, 9))
    ocurrencia(base, date(2026, 12, 1), estado="pendiente")
    ocurrencia(base, date(2026, 12, 2), estado="hecha", primera=local(2, 9))
    ruta = {r.fecha: r for r in kpi.ruta_del_cierre(base["p"], HOY)}
    assert (ruta[date(2026, 12, 1)].hechas, ruta[date(2026, 12, 1)].total, ruta[date(2026, 12, 1)].atrasadas) == (1, 2, 1)
    assert (ruta[date(2026, 12, 2)].hechas, ruta[date(2026, 12, 2)].total) == (1, 1)


def test_resumen_del_cierre_avance_y_atrasadas(base):
    ocurrencia(base, date(2026, 12, 3), estado="hecha", primera=local(3, 9))
    ocurrencia(base, date(2026, 12, 3), estado="pendiente")
    ocurrencia(base, date(2026, 12, 14), estado="pendiente")
    ocurrencia(base, HOY, estado="pendiente")
    r = kpi.resumen(base["p"], HOY)
    assert (r.hechas, r.total, r.atrasadas, r.vencen_hoy) == (1, 4, 1, 1)
    assert r.avance_pct == 25.0
    assert (r.equipo_a_tiempo, r.equipo_vencidas) == (1, 2)


def test_avance_por_proceso_con_semaforo_al_dia_por_vencer_y_atrasado(base):
    ocurrencia(base, date(2026, 12, 3), estado="hecha", primera=local(3, 9), proceso="Compras")
    ocurrencia(base, date(2026, 12, 3), estado="revisada", primera=local(3, 9), proceso="Compras")
    ocurrencia(base, date(2026, 12, 3), estado="pendiente", proceso="Conciliación")  # vencida y sin hacer
    ocurrencia(base, date(2026, 12, 14), estado="pendiente", proceso="Remuneraciones")  # aún no vence
    av = {a.proceso: a for a in kpi.avance_por_proceso(base["p"], HOY)}
    assert (av["Compras"].hechas, av["Compras"].total, av["Compras"].estado) == (2, 2, "al_dia")
    assert av["Conciliación"].estado == "atrasado"
    assert av["Remuneraciones"].estado == "por_vencer"
