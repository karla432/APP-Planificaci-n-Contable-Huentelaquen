"""Mantenedor de procesos y tareas: Proceso, Tarea principal, Subtarea, responsable y periodicidad."""
import pytest

from nucleo.models import EventoAuditoria, Ocurrencia, Proceso, Tarea
from nucleo.servicios import mantenedor, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa de Control"), cargo("Contador Senior"), cargo("Gerente AyF")
    p = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont), "ger": persona("Gerente", ger)}
    u = {k: usuario_con_rol(k, r, p.get(k)) for k, r in (("jefa", "JEFATURA"), ("cont", "COLABORADOR"), ("ger", "GERENTE"))}
    u["admin"], u["lectura"] = usuario_con_rol("admin", "ADMIN_SISTEMA"), usuario_con_rol("lectura", "LECTURA")
    return {"u": u, "jefa": jefa, "cont": cont, "ger": ger, "proceso": Proceso.objects.create(nombre="Compras")}


def datos(mundo, **cambios):
    base = dict(proceso_id=mundo["proceso"].pk, tarea_principal="Libro de compras", subtarea="Cotejar el RCV contra Odoo",
                cargo_ejecuta_id=mundo["cont"].pk, tipo="CIERRE_DIA_HABIL", n=2)
    base.update(cambios)
    return mantenedor.DatosTarea(**base)


# ---- Crear y editar tareas ---------------------------------------------------------------------------------


def test_crear_una_tarea_con_codigo_regla_horas_y_revisor(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, cargo_revisa_id=mundo["ger"].pk, minutos=45))
    assert t.codigo == f"{mundo['proceso'].codigo}.01.001" and t.cargo_ejecuta == mundo["cont"] and t.cargo_revisa == mundo["ger"]
    assert (t.regla_tipo, t.regla_n) == ("CIERRE_DIA_HABIL", 2) and t.activa and not t.requiere_revision
    assert t.minutos_estimados == 45 and float(t.ejecuciones_mes) == 1  # una vez al mes: es del cierre
    assert mantenedor.crear_tarea(mundo["u"]["ger"], datos(mundo, subtarea="Otra subtarea")).codigo.endswith(".01.002")  # misma tarea: sigue la subtarea
    assert EventoAuditoria.objects.filter(accion="tarea.creada", entidad_id=str(t.pk)).exists()


def test_las_ejecuciones_al_mes_salen_de_la_periodicidad(mundo):
    d = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, subtarea="Diaria", tipo="DIARIA_HABIL", n=None, minutos=10))
    s = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, subtarea="Semanal", tipo="SEMANAL", n=None, dia_semana=0, minutos=10))
    assert float(d.ejecuciones_mes) == 21 and float(s.ejecuciones_mes) == pytest.approx(4.33)


def test_sin_revisor_queda_sin_revisor_no_se_inventa(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["ger"], datos(mundo, cargo_ejecuta_id=mundo["jefa"].pk))
    assert t.cargo_revisa is None


def test_la_tarea_de_un_externo_propone_a_la_jefa_como_quien_recibe(mundo):
    from pruebas.ayudas import cargo as nuevo_cargo
    bodega = nuevo_cargo("Bodega", externo=True)
    t = mantenedor.crear_tarea(mundo["u"]["ger"], datos(mundo, cargo_ejecuta_id=bodega.pk))
    assert t.cargo_revisa == mundo["jefa"]


@pytest.mark.parametrize("quien", ["cont", "admin", "lectura"])
def test_solo_gerente_y_jefatura_editan_tareas(mundo, quien):
    with pytest.raises(PermisoDenegado):
        mantenedor.crear_tarea(mundo["u"][quien], datos(mundo))
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    with pytest.raises(PermisoDenegado):
        mantenedor.editar_tarea(mundo["u"][quien], t, datos(mundo, subtarea="Cambiada"))
    t.refresh_from_db()
    assert t.subtarea == "Cotejar el RCV contra Odoo"


@pytest.mark.parametrize(
    "cambios,mensaje",
    [
        (dict(tipo="SEMANAL", n=None), "día de la semana"),
        (dict(tipo="CIERRE_HITO", n=7), "día 8, 9 o 10"),
        (dict(tipo="CIERRE_DIA_HABIL", n=0), "día hábil"),
        (dict(tipo="DIA_FIJO", n=None, dia=32), "día del mes"),
        (dict(tipo="QUINCENAL"), "periodicidad"),
        (dict(subtarea="   "), "subtarea"),
        (dict(tarea_principal=""), "tarea principal"),
    ],
)
def test_no_se_guarda_una_tarea_con_datos_invalidos(mundo, cambios, mensaje):
    with pytest.raises(ErrorDeNegocio, match=mensaje):
        mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, **cambios))
    assert Tarea.objects.count() == 0


def test_no_se_repite_la_misma_tarea_en_el_mismo_proceso(mundo):
    mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    with pytest.raises(ErrorDeNegocio, match="ya existe"):
        mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, subtarea="  cotejar el rcv contra odoo "))


def test_una_regla_de_meses_sin_dia_se_guarda_pero_queda_para_revision(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, tipo="MESES", n=None, meses=(4, 6, 9, 11)))
    assert t.requiere_revision and "día" in t.motivo_revision
    t = mantenedor.editar_tarea(mundo["u"]["jefa"], t, datos(mundo, tipo="MESES", n=None, meses=(4, 6, 9, 11), dia=20))
    assert not t.requiere_revision and t.regla_dia == 20


def test_editar_guarda_quien_cuando_antes_y_despues(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    mantenedor.editar_tarea(mundo["u"]["ger"], t, datos(mundo, n=3))
    ev = EventoAuditoria.objects.filter(accion="tarea.editada").get()
    assert ev.usuario == mundo["u"]["ger"] and ev.antes["regla_n"] == 2 and ev.despues["regla_n"] == 3


def test_un_cambio_rige_desde_el_proximo_mes_y_no_reescribe_lo_ya_generado(mundo):
    anio_abierto()
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, n=1))
    periodos.abrir_mes(2026, 12, usuario=None)
    mantenedor.editar_tarea(mundo["u"]["jefa"], t, datos(mundo, n=3, cargo_ejecuta_id=mundo["jefa"].pk))
    o = Ocurrencia.objects.get()
    assert o.cargo_ejecuta == mundo["cont"] and o.regla_copia["n"] == 1


def test_el_codigo_y_la_clave_no_cambian_al_editar_el_texto(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    clave = t.clave_estable
    t = mantenedor.editar_tarea(mundo["u"]["jefa"], t, datos(mundo, subtarea="Texto corregido"))
    assert t.codigo.endswith(".01.001") and t.clave_estable == clave and t.subtarea == "Texto corregido"


def test_desactivar_no_borra(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    mantenedor.editar_tarea(mundo["u"]["jefa"], t, datos(mundo, activa=False))
    assert Tarea.objects.filter(pk=t.pk, activa=False).exists()


# ---- Procesos --------------------------------------------------------------------------------------------


def test_crear_y_renombrar_procesos(mundo):
    p = mantenedor.crear_proceso(mundo["u"]["jefa"], "Remuneraciones")
    assert Proceso.objects.filter(nombre="Remuneraciones").exists()
    mantenedor.renombrar_proceso(mundo["u"]["jefa"], p, "Remuneraciones y leyes sociales")
    p.refresh_from_db()
    assert p.nombre == "Remuneraciones y leyes sociales"
    assert set(EventoAuditoria.objects.values_list("accion", flat=True)) >= {"proceso.creado", "proceso.editado"}


def test_un_proceso_no_se_repite_ni_queda_vacio(mundo):
    with pytest.raises(ErrorDeNegocio, match="ya existe"):
        mantenedor.crear_proceso(mundo["u"]["jefa"], " compras ")
    with pytest.raises(ErrorDeNegocio, match="nombre"):
        mantenedor.crear_proceso(mundo["u"]["jefa"], "  ")


def test_solo_gerente_y_jefatura_editan_procesos(mundo):
    with pytest.raises(PermisoDenegado):
        mantenedor.crear_proceso(mundo["u"]["cont"], "Nuevo")
    with pytest.raises(PermisoDenegado):
        mantenedor.renombrar_proceso(mundo["u"]["lectura"], mundo["proceso"], "Otro")


def test_codigo_pro_tar_sub_una_tarea_principal_nueva_abre_numero_y_sus_subtareas_siguen(mundo):
    pro = mundo["proceso"].codigo
    a1 = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, tarea_principal="Libro de compras", subtarea="Cotejar"))
    b1 = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, tarea_principal="Libro de ventas", subtarea="Cotejar ventas"))
    a2 = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, tarea_principal="Libro de compras", subtarea="Corregir diferencias"))
    assert (a1.codigo, b1.codigo, a2.codigo) == (f"{pro}.01.001", f"{pro}.02.001", f"{pro}.01.002")
    assert a1.secuencia < b1.secuencia < a2.secuencia  # lo nuevo se procesa al final


def test_un_proceso_nuevo_toma_el_codigo_y_el_orden_siguientes(mundo):
    p1, p2 = mundo["proceso"], mantenedor.crear_proceso(mundo["u"]["jefa"], "Proceso nuevo")
    assert p2.orden == p1.orden + 1 and p2.codigo == f"{p2.orden:02d}-{p2.sigla}" and len(p2.sigla) == 3


# ---- Minutos de revisión (Karla, 02-11-2026) -----------------------------------------------------------------


def test_los_minutos_de_revision_se_guardan_por_tarea_y_vacio_es_el_valor_general(mundo):
    sin = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, cargo_revisa_id=mundo["ger"].pk, minutos=120))
    assert sin.minutos_revision is None  # vacío: la app usa los 15 min generales
    con = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, subtarea="Otra", cargo_revisa_id=mundo["ger"].pk, minutos=120, minutos_revision=30))
    assert con.minutos_revision == 30
    con = mantenedor.editar_tarea(mundo["u"]["jefa"], con, datos(mundo, subtarea="Otra", cargo_revisa_id=mundo["ger"].pk, minutos=120, minutos_revision=None))
    assert con.minutos_revision is None


@pytest.mark.parametrize("valor", [-1, 481])
def test_los_minutos_de_revision_fuera_de_rango_se_rechazan(mundo, valor):
    with pytest.raises(ErrorDeNegocio, match="minutos de revisión"):
        mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo, minutos_revision=valor))
