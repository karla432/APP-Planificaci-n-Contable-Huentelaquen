"""Mantenedor de procesos y tareas: Proceso, Tarea principal, Subtarea, responsable y periodicidad."""
import pytest

from nucleo.models import EventoAuditoria, Ocurrencia, Proceso, Tarea
from nucleo.servicios import mantenedor, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture
def mundo():
    jefa, cont, ger = cargo("Jefa Gestión y Control"), cargo("Contadora Senior"), cargo("Gerente AyF")
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


def test_crear_una_tarea_con_codigo_regla_y_revisora(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["jefa"], datos(mundo))
    assert t.codigo == "TAR-0001" and t.cargo_ejecuta == mundo["cont"] and t.cargo_revisa == mundo["jefa"]
    assert (t.regla_tipo, t.regla_n) == ("CIERRE_DIA_HABIL", 2) and t.activa and not t.requiere_revision
    assert mantenedor.crear_tarea(mundo["u"]["ger"], datos(mundo, subtarea="Otra subtarea")).codigo == "TAR-0002"
    assert EventoAuditoria.objects.filter(accion="tarea.creada", entidad_id=str(t.pk)).exists()


def test_la_tarea_de_la_jefa_la_revisa_el_gerente(mundo):
    t = mantenedor.crear_tarea(mundo["u"]["ger"], datos(mundo, cargo_ejecuta_id=mundo["jefa"].pk))
    assert t.cargo_revisa == mundo["ger"]


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
        (dict(tipo="CIERRE_HITO", n=8), "7 o 10"),
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
    assert t.codigo == "TAR-0001" and t.clave_estable == clave and t.subtarea == "Texto corregido"


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
