"""Apertura de mes: vista previa, idempotencia, copia de responsable y regla, avisos."""
from datetime import date

import pytest

from nucleo.models import EventoAuditoria, Ocurrencia, Periodo
from nucleo.servicios import periodos
from nucleo.servicios.errores import ErrorDeNegocio
from pruebas.ayudas import anio_abierto, cargo, persona, tarea

pytestmark = pytest.mark.django_db
INICIO_NOV = date(2026, 11, 5)  # P7


@pytest.fixture
def equipo():
    jefa, cont, anal, ger = cargo("Jefa de Control"), cargo("Contador Senior"), cargo("Analista Contable"), cargo("Gerente AyF")
    return {
        "jefa": jefa, "cont": cont, "anal": anal, "ger": ger,
        "p_jefa": persona("Jefa", jefa), "p_cont": persona("Contadora", cont), "p_anal": persona("Analista", anal),
    }


def test_la_vista_previa_no_guarda_nada(equipo):
    anio_abierto()
    tarea("TAR-0001", equipo["anal"], "DIARIA_HABIL", revisa=equipo["jefa"])
    vp = periodos.vista_previa(2026, 11, inicio_medicion=INICIO_NOV)
    assert len(vp.ocurrencias) == 18 and vp.ocurrencias[0].fecha == INICIO_NOV
    assert Periodo.objects.count() == 0 and Ocurrencia.objects.count() == 0


def test_no_se_abre_un_mes_de_un_anio_no_abierto(equipo):
    tarea("TAR-0001", equipo["anal"], "DIARIA_HABIL")
    with pytest.raises(ErrorDeNegocio, match="año"):
        periodos.abrir_mes(2026, 11, usuario=None)


def test_abrir_mes_genera_ocurrencias_con_copia_de_responsable_y_regla(equipo):
    anio_abierto()
    t = tarea("TAR-0001", equipo["anal"], "SEMANAL", revisa=equipo["jefa"], dia_semana=0)
    res = periodos.abrir_mes(2026, 11, usuario=None, inicio_medicion=INICIO_NOV)
    assert res.creadas == 4  # lunes 9, 16, 23 y 30 (el 2 es anterior al inicio de medición)
    o = Ocurrencia.objects.order_by("fecha_limite").first()
    assert o.fecha_limite == date(2026, 11, 9) and o.estado == "pendiente"
    assert o.colaborador.nombre == "Analista" and o.cargo_ejecuta == equipo["anal"] and o.cargo_revisa == equipo["jefa"]
    assert o.regla_copia["tipo"] == "SEMANAL" and o.regla_copia["dia_semana"] == 0
    assert Periodo.objects.get().inicio_medicion == INICIO_NOV


def test_abrir_dos_veces_no_duplica(equipo):
    anio_abierto()
    tarea("TAR-0001", equipo["anal"], "DIARIA_HABIL")
    periodos.abrir_mes(2026, 11, usuario=None, inicio_medicion=INICIO_NOV)
    antes = Ocurrencia.objects.count()
    res = periodos.abrir_mes(2026, 11, usuario=None, inicio_medicion=INICIO_NOV)
    assert res.creadas == 0 and res.ya_existian == antes and Ocurrencia.objects.count() == antes
    assert Periodo.objects.count() == 1


def test_el_cierre_de_diciembre_cae_en_las_fechas_correctas(equipo):
    anio_abierto()
    for i, n in enumerate((1, 2, 3, 4), start=1):
        tarea(f"TAR-001{i}", equipo["cont"], "CIERRE_DIA_HABIL", n=n)
    tarea("TAR-0020", equipo["cont"], "CIERRE_HITO", n=8)
    tarea("TAR-0021", equipo["cont"], "CIERRE_HITO", n=10)
    tarea("TAR-0022", equipo["cont"], "DIA_FIJO", dia=13, ajuste="anterior")
    periodos.abrir_mes(2026, 12, usuario=None)
    fechas = {o.tarea.codigo: o.fecha_limite for o in Ocurrencia.objects.select_related("tarea")}
    assert fechas == {
        "TAR-0011": date(2026, 12, 1), "TAR-0012": date(2026, 12, 2), "TAR-0013": date(2026, 12, 3), "TAR-0014": date(2026, 12, 4),
        "TAR-0020": date(2026, 12, 9), "TAR-0021": date(2026, 12, 11), "TAR-0022": date(2026, 12, 11),  # el 8 es feriado: día 8 → 09-12, día 10 → 11-12
    }


def test_las_tareas_externas_se_generan_sin_persona_y_sin_aviso(equipo):
    anio_abierto()
    bodega = cargo("Bodega", externo=True)
    tarea("TAR-0030", bodega, "CIERRE_DIA_HABIL", revisa=equipo["jefa"], n=1)
    res = periodos.abrir_mes(2026, 12, usuario=None)
    o = Ocurrencia.objects.get()
    assert res.creadas == 1 and o.colaborador is None and o.cargo_ejecuta == bodega
    assert not res.avisos


def test_un_cargo_sin_persona_vigente_avisa_y_no_genera(equipo):
    anio_abierto()
    sin_nadie = cargo("Cargo vacío")
    tarea("TAR-0040", sin_nadie, "CIERRE_DIA_HABIL", n=1)
    res = periodos.abrir_mes(2026, 12, usuario=None)
    assert res.creadas == 0 and [a.tipo for a in res.avisos] == ["sin_responsable"]


def test_al_asignar_la_persona_reabrir_completa_lo_que_faltaba(equipo):
    anio_abierto()
    vacio = cargo("Cargo vacío")
    tarea("TAR-0040", vacio, "CIERRE_DIA_HABIL", n=1)
    periodos.abrir_mes(2026, 12, usuario=None)
    persona("Nueva persona", vacio)
    res = periodos.abrir_mes(2026, 12, usuario=None)
    assert res.creadas == 1 and not res.avisos


def test_un_cargo_con_dos_personas_vigentes_avisa_y_no_adivina(equipo):
    anio_abierto()
    persona("Otra contadora", equipo["cont"])
    tarea("TAR-0050", equipo["cont"], "CIERRE_DIA_HABIL", n=1)
    res = periodos.abrir_mes(2026, 12, usuario=None)
    assert res.creadas == 0 and [a.tipo for a in res.avisos] == ["varias_personas"]


def test_un_reemplazo_a_mitad_de_mes_asigna_a_cada_uno_su_tramo(equipo):
    anio_abierto()
    cargo_x = cargo("Cargo con reemplazo")
    persona("Titular", cargo_x, hasta=date(2026, 11, 15))
    persona("Reemplazo", cargo_x, desde=date(2026, 11, 16))
    tarea("TAR-0060", cargo_x, "SEMANAL", dia_semana=0)
    periodos.abrir_mes(2026, 11, usuario=None)
    quien = {o.fecha_limite: o.colaborador.nombre for o in Ocurrencia.objects.all()}
    assert quien[date(2026, 11, 9)] == "Titular" and quien[date(2026, 11, 16)] == "Reemplazo" and quien[date(2026, 11, 30)] == "Reemplazo"


def test_tareas_para_revision_o_inactivas_no_se_generan_y_se_listan(equipo):
    anio_abierto()
    t1 = tarea("TAR-0070", equipo["cont"], "SEMANAL")  # le falta el día
    t1.requiere_revision, t1.motivo_revision = True, "Semanal sin día"
    t1.save()
    t2 = tarea("TAR-0071", equipo["cont"], "DIARIA_HABIL")
    t2.activa = False
    t2.save()
    res = periodos.abrir_mes(2026, 11, usuario=None)
    assert res.creadas == 0
    assert [a.tipo for a in res.avisos] == ["requiere_revision"]


def test_una_regla_incompleta_avisa_en_vez_de_romper(equipo):
    anio_abierto()
    tarea("TAR-0080", equipo["cont"], "MESES", meses="4,6,9,11")  # sin día de vencimiento
    res = periodos.abrir_mes(2026, 11, usuario=None)
    assert res.creadas == 0 and [a.tipo for a in res.avisos] == ["regla_incompleta"]


def test_un_cambio_posterior_en_la_tarea_no_reescribe_el_pasado(equipo):
    anio_abierto()
    t = tarea("TAR-0090", equipo["anal"], "CIERRE_DIA_HABIL", n=1)
    periodos.abrir_mes(2026, 12, usuario=None)
    t.cargo_ejecuta, t.regla_n = equipo["cont"], 2
    t.save()
    res = periodos.abrir_mes(2026, 12, usuario=None)
    o = Ocurrencia.objects.get()
    assert o.cargo_ejecuta == equipo["anal"] and o.fecha_limite == date(2026, 12, 1)
    assert o.regla_copia["n"] == 1


def test_un_periodo_cerrado_no_se_vuelve_a_abrir(equipo):
    anio_abierto()
    tarea("TAR-0090", equipo["anal"], "DIARIA_HABIL")
    periodos.abrir_mes(2026, 12, usuario=None)
    Periodo.objects.update(estado="cerrado")
    with pytest.raises(ErrorDeNegocio, match="cerrado"):
        periodos.abrir_mes(2026, 12, usuario=None)


def test_abrir_mes_queda_en_auditoria_con_los_conteos(equipo):
    anio_abierto()
    tarea("TAR-0090", equipo["anal"], "CIERRE_DIA_HABIL", n=1)
    periodos.abrir_mes(2026, 12, usuario=None)
    ev = EventoAuditoria.objects.get(accion="periodo.abierto")
    assert ev.entidad_id == "12-2026" and ev.despues["creadas"] == 1
