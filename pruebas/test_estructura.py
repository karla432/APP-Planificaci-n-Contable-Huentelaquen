"""Estructura de tres niveles con códigos OO-PPP.TT.SSS: generación, reordenamiento, dependencias, relaciones y trazabilidad."""
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from nucleo import siglas
from nucleo.models import CambioDeCodigo, DependenciaProceso, EventoAuditoria, Ocurrencia, Proceso, Tarea, TareaPrincipal
from nucleo.servicios import estructura, mantenedor, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture
def u():
    c = cargo("Jefa de Control")
    return {"jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", c)), "ger": usuario_con_rol("ger", "GERENTE", persona("Ger", cargo("Gerente AyF"))),
            "cont": usuario_con_rol("cont", "COLABORADOR", persona("Cont", cargo("Contador Senior"))), "lectura": usuario_con_rol("lec", "LECTURA")}


def proceso(u, nombre, sigla="", **kw):
    return estructura.crear_proceso(u["jefa"], nombre, sigla, **kw)


def subtarea(u, p, tarea, sub, **kw):
    d = dict(proceso_id=p.pk, tarea_principal=tarea, subtarea=sub, cargo_ejecuta_id=cargo("Contador Senior").pk, tipo="CIERRE_DIA_HABIL", n=2)
    d.update(kw)
    return mantenedor.crear_tarea(u["jefa"], mantenedor.DatosTarea(**d))


@pytest.fixture
def ventas(u):
    """El ejemplo pedido: proceso Ventas y sala de venta (VEN) con 3 tareas y 8 subtareas."""
    p = proceso(u, "Ventas y sala de venta", "VEN")
    for tarea, subs in (("Registro de ventas", ["Ingresar arqueo de caja", "Registrar diferencias de caja", "Validar documentos de venta"]),
                        ("Cierre de caja", ["Revisar medios de pago", "Cuadrar caja", "Generar informe de cierre"]),
                        ("Registro contable", ["Generar asiento contable", "Validar cuentas contables"])):
        for s in subs:
            subtarea(u, p, tarea, s)
    return p


# ---- Generación de códigos ------------------------------------------------------------------------------------------------


def test_el_ejemplo_de_ventas_genera_los_codigos_del_formato(ventas):
    assert ventas.codigo == "01-VEN" and ventas.sigla == "VEN" and ventas.orden == 1
    assert list(TareaPrincipal.objects.values_list("codigo", "nombre")) == [
        ("01-VEN.01", "Registro de ventas"), ("01-VEN.02", "Cierre de caja"), ("01-VEN.03", "Registro contable")]
    assert list(Tarea.objects.order_by("codigo").values_list("codigo", "subtarea")) == [
        ("01-VEN.01.001", "Ingresar arqueo de caja"), ("01-VEN.01.002", "Registrar diferencias de caja"), ("01-VEN.01.003", "Validar documentos de venta"),
        ("01-VEN.02.001", "Revisar medios de pago"), ("01-VEN.02.002", "Cuadrar caja"), ("01-VEN.02.003", "Generar informe de cierre"),
        ("01-VEN.03.001", "Generar asiento contable"), ("01-VEN.03.002", "Validar cuentas contables")]


def test_cada_nivel_conserva_la_relacion_con_su_nivel_superior(ventas):
    for t in Tarea.objects.select_related("padre__proceso"):
        assert t.padre.proceso_id == t.proceso_id == ventas.pk
        assert t.codigo.startswith(t.padre.codigo + ".") and t.padre.codigo.startswith(ventas.codigo + ".")
        assert t.tarea_principal == t.padre.nombre  # el texto y la relación dicen lo mismo


def test_los_correlativos_son_por_proceso_y_por_tarea(u, ventas):
    otro = proceso(u, "Compras", "COM")
    t = subtarea(u, otro, "Registro de compras", "Ingresar facturas")
    assert t.codigo == "02-COM.01.001"  # vuelve a empezar en cada proceso
    assert subtarea(u, ventas, "Cierre de caja", "Archivar el informe").codigo == "01-VEN.02.004"  # sigue dentro de su tarea


def test_la_sigla_se_valida_y_no_se_repite(u, ventas):
    assert estructura.validar_sigla("com") == "COM"  # se pasa a mayúsculas
    for mala in ("VE", "VENT", "V3N", "ÑAN", "", "V N"):
        with pytest.raises(ErrorDeNegocio, match="3 letras"):
            estructura.validar_sigla(mala)
    with pytest.raises(ErrorDeNegocio, match="ya la usa"):
        proceso(u, "Otro proceso", "VEN")


def test_sin_sigla_la_app_propone_una_libre(u, ventas):
    p = proceso(u, "Ventas por mayor")
    assert siglas.valida(p.sigla) and p.sigla != "VEN"
    assert siglas.derivar("Cuentas por cobrar y pagar", set()) == "CCP"  # iniciales cuando hay 3 palabras o más
    assert siglas.derivar("Tesorería", set()) == "TES"


def test_un_codigo_no_se_puede_duplicar_ni_a_la_fuerza(ventas, u):
    t = Tarea.objects.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        Tarea.objects.filter(pk=Tarea.objects.exclude(pk=t.pk).first().pk).update(codigo=t.codigo)
    with pytest.raises(IntegrityError), transaction.atomic():
        TareaPrincipal.objects.create(proceso=ventas, nombre="Registro de ventas")  # misma tarea dos veces
    with pytest.raises(IntegrityError), transaction.atomic():
        Proceso.objects.filter(pk=proceso(u, "Compras", "COM").pk).update(orden=ventas.orden)  # orden repetido


def test_no_se_borra_lo_que_tiene_hijos(ventas):
    with pytest.raises(ProtectedError):
        ventas.delete()
    with pytest.raises(ProtectedError):
        TareaPrincipal.objects.first().delete()


def test_un_codigo_de_otro_formato_no_se_toca(u):
    p = proceso(u, "Compras", "COM")
    t = Tarea.objects.create(codigo="X-LEGADO-1", clave_estable="k" * 64, proceso=p, tarea_principal="T", subtarea="S", cargo_ejecuta=cargo("Contador Senior"))
    estructura.reordenar_procesos(u["jefa"], [p.pk])
    p.orden = 5
    p.save()
    t.refresh_from_db()
    assert t.codigo == "X-LEGADO-1" and t.padre is not None


# ---- Reordenar --------------------------------------------------------------------------------------------------------------


@pytest.fixture
def tres(u):
    a, b, c = proceso(u, "Ventas", "VEN"), proceso(u, "Compras", "COM"), proceso(u, "Tesorería", "TES")
    for p in (a, b, c):
        subtarea(u, p, "Tarea uno", "Subtarea uno")
        subtarea(u, p, "Tarea dos", "Subtarea dos")
    return a, b, c


def codigos():
    return sorted(Tarea.objects.values_list("codigo", flat=True))


def test_reordenar_actualiza_el_prefijo_de_todo_el_arbol_sin_duplicados(u, tres):
    a, b, c = tres
    antes_pk = list(Tarea.objects.order_by("id").values_list("pk", flat=True))
    estructura.reordenar_procesos(u["jefa"], [c.pk, a.pk, b.pk])
    for p in (a, b, c):
        p.refresh_from_db()
    assert (c.codigo, a.codigo, b.codigo) == ("01-TES", "02-VEN", "03-COM")
    assert (c.orden, a.orden, b.orden) == (1, 2, 3)
    assert codigos() == ["01-TES.01.001", "01-TES.02.001", "02-VEN.01.001", "02-VEN.02.001", "03-COM.01.001", "03-COM.02.001"]
    assert len(set(Tarea.objects.values_list("codigo", flat=True))) == 6 and len(set(TareaPrincipal.objects.values_list("codigo", flat=True))) == 6
    assert list(Tarea.objects.order_by("id").values_list("pk", flat=True)) == antes_pk  # misma identidad: nada se recreó
    assert a.sigla == "VEN"  # la sigla no cambia con el orden


def test_el_codigo_anterior_queda_en_el_historial_y_se_puede_buscar(u, tres):
    a, b, c = tres
    estructura.reordenar_procesos(u["jefa"], [c.pk, a.pk, b.pk])
    cambio = CambioDeCodigo.objects.get(codigo_anterior="03-TES.01.001")
    assert cambio.codigo_nuevo == "01-TES.01.001" and cambio.nivel == 3 and cambio.objeto_id == Tarea.objects.get(codigo="01-TES.01.001").pk
    assert CambioDeCodigo.objects.filter(nivel=1, codigo_anterior="01-VEN", codigo_nuevo="02-VEN").exists()
    assert CambioDeCodigo.objects.filter(nivel=2).count() == 6 and CambioDeCodigo.objects.filter(nivel=3).count() == 6
    e = EventoAuditoria.objects.filter(accion="proceso.reordenado").latest("id")
    assert e.antes["orden"] == ["01-VEN", "02-COM", "03-TES"] and e.despues["orden"] == ["01-TES", "02-VEN", "03-COM"]


def test_las_ocurrencias_siguen_ligadas_a_su_subtarea_al_reordenar(u, tres):
    a, b, c = tres
    anio_abierto()
    periodos.abrir_mes(2026, 12, usuario=None)
    antes = dict(Ocurrencia.objects.values_list("pk", "tarea_id"))
    estructura.reordenar_procesos(u["jefa"], [b.pk, c.pk, a.pk])
    assert dict(Ocurrencia.objects.values_list("pk", "tarea_id")) == antes
    assert Ocurrencia.objects.filter(tarea__proceso=b).first().tarea.codigo.startswith("01-COM.")


def test_reordenar_exige_la_lista_completa_y_sin_repetidos(u, tres):
    a, b, c = tres
    for mala in ([a.pk, b.pk], [a.pk, a.pk, b.pk, c.pk], [a.pk, b.pk, c.pk, 9999]):
        with pytest.raises(ErrorDeNegocio, match="todos los procesos"):
            estructura.reordenar_procesos(u["jefa"], mala)
    assert list(Proceso.objects.values_list("orden", flat=True)) == [1, 2, 3]  # no cambió nada


def test_mover_un_lugar_y_a_una_posicion(u, tres):
    a, b, c = tres
    estructura.mover_proceso(u["jefa"], c, "subir")
    assert list(Proceso.objects.values_list("sigla", flat=True)) == ["VEN", "TES", "COM"]
    estructura.mover_proceso(u["jefa"], Proceso.objects.get(sigla="VEN"), "subir")  # ya es el primero: no pasa nada
    assert Proceso.objects.get(sigla="VEN").orden == 1
    estructura.mover_a_posicion(u["jefa"], Proceso.objects.get(sigla="COM"), 1)
    assert list(Proceso.objects.values_list("sigla", flat=True)) == ["COM", "VEN", "TES"]
    with pytest.raises(ErrorDeNegocio, match="entre 1 y 3"):
        estructura.mover_a_posicion(u["jefa"], c, 9)


def test_un_proceso_nuevo_puede_crearse_en_una_posicion(u, tres):
    p = proceso(u, "Planificación", "PLA", orden=1)
    assert list(Proceso.objects.values_list("sigla", flat=True)) == ["PLA", "VEN", "COM", "TES"]
    assert Tarea.objects.filter(codigo="02-VEN.01.001").exists() and p.refresh_from_db() is None and p.codigo == "01-PLA"


def test_cambiar_la_sigla_cambia_el_codigo_de_todo_el_proceso_con_historial(u, tres):
    a, _, _ = tres
    estructura.editar_proceso(u["jefa"], a, "Ventas", "vta", estructura.DatosPlan())
    a.refresh_from_db()
    assert a.sigla == "VTA" and a.codigo == "01-VTA" and Tarea.objects.filter(codigo="01-VTA.02.001").exists()
    assert CambioDeCodigo.objects.filter(codigo_anterior="01-VEN.01.001", codigo_nuevo="01-VTA.01.001").exists()


# ---- Dependencias y etapas -------------------------------------------------------------------------------------------------


def test_dependencias_etapas_y_paralelismo(u):
    pla, ven, com, cxp, tes = (proceso(u, n, s) for n, s in (("Planificación", "PLA"), ("Ventas", "VEN"), ("Compras", "COM"), ("Cuentas por pagar", "CXP"), ("Tesorería", "TES")))
    estructura.fijar_dependencias(u["jefa"], ven, [pla.pk])
    estructura.fijar_dependencias(u["jefa"], com, [pla.pk])
    estructura.fijar_dependencias(u["jefa"], cxp, [com.pk])
    estructura.fijar_dependencias(u["jefa"], tes, [ven.pk, cxp.pk])
    fases = [(e.numero, [p.sigla for p in e.procesos], e.en_paralelo) for e in estructura.etapas()]
    assert fases == [(1, ["PLA"], False), (2, ["VEN", "COM"], True), (3, ["CXP"], False), (4, ["TES"], False)]
    assert [p.sigla for p in estructura.dependencias_de()[tes.pk]] == ["VEN", "CXP"]


def test_sin_dependencias_todos_pueden_ir_en_paralelo(u, tres):
    (etapa,) = estructura.etapas()
    assert etapa.numero == 1 and etapa.en_paralelo and len(etapa.procesos) == 3


def test_no_se_aceptan_dependencias_a_si_mismo_ciclos_ni_contra_el_orden(u, tres):
    a, b, c = tres
    with pytest.raises(ErrorDeNegocio, match="de sí mismo"):
        estructura.fijar_dependencias(u["jefa"], a, [a.pk])
    with pytest.raises(ErrorDeNegocio, match="va después en el orden"):
        estructura.fijar_dependencias(u["jefa"], a, [b.pk])  # Ventas es primero: no puede depender de Compras
    estructura.fijar_dependencias(u["jefa"], b, [a.pk])
    estructura.fijar_dependencias(u["jefa"], c, [b.pk])
    with pytest.raises(ErrorDeNegocio):
        estructura.fijar_dependencias(u["jefa"], a, [c.pk])
    assert DependenciaProceso.objects.count() == 2


def test_fijar_dependencias_reemplaza_y_queda_en_la_bitacora(u, tres):
    a, b, c = tres
    estructura.fijar_dependencias(u["jefa"], c, [a.pk, b.pk])
    estructura.fijar_dependencias(u["jefa"], c, [b.pk])
    assert list(DependenciaProceso.objects.filter(proceso=c).values_list("depende_de__sigla", flat=True)) == ["COM"]
    e = EventoAuditoria.objects.filter(accion="proceso.dependencias").latest("id")
    assert e.antes["depende_de"] == ["01-VEN", "02-COM"] and e.despues["depende_de"] == ["02-COM"]


def test_no_se_puede_reordenar_contra_una_dependencia(u, tres):
    a, b, c = tres
    estructura.fijar_dependencias(u["jefa"], b, [a.pk])
    with pytest.raises(ErrorDeNegocio, match="depende de"):
        estructura.reordenar_procesos(u["jefa"], [b.pk, a.pk, c.pk])
    assert Proceso.objects.get(pk=a.pk).orden == 1  # nada cambió
    estructura.reordenar_procesos(u["jefa"], [a.pk, c.pk, b.pk])  # moverlo después sí se puede


# ---- Tareas (nivel 2), desactivación y movimientos -------------------------------------------------------------------------------


def test_crear_editar_y_renombrar_tareas_actualiza_sus_subtareas(u, ventas):
    tp = estructura.crear_tarea_principal(u["jefa"], ventas, "Conciliación de ventas")
    assert tp.codigo == "01-VEN.04"
    with pytest.raises(ErrorDeNegocio, match="ya tiene"):
        estructura.crear_tarea_principal(u["jefa"], ventas, "conciliación de ventas")
    registro = TareaPrincipal.objects.get(codigo="01-VEN.01")
    estructura.editar_tarea_principal(u["jefa"], registro, "Registro diario de ventas", estructura.DatosPlan(estado_plan="en_curso"))
    registro.refresh_from_db()
    assert registro.codigo == "01-VEN.01" and registro.estado_plan == "en_curso"
    assert set(Tarea.objects.filter(padre=registro).values_list("tarea_principal", flat=True)) == {"Registro diario de ventas"}


def test_una_subtarea_que_cambia_de_tarea_toma_el_correlativo_nuevo_y_deja_historial(u, ventas):
    t = Tarea.objects.get(codigo="01-VEN.01.002")
    d = mantenedor.DatosTarea(proceso_id=ventas.pk, tarea_principal="Cierre de caja", subtarea=t.subtarea, cargo_ejecuta_id=t.cargo_ejecuta_id, tipo="CIERRE_DIA_HABIL", n=2)
    mantenedor.editar_tarea(u["jefa"], t, d)
    t.refresh_from_db()
    assert t.codigo == "01-VEN.02.004" and t.padre.codigo == "01-VEN.02"
    assert CambioDeCodigo.objects.filter(codigo_anterior="01-VEN.01.002", codigo_nuevo="01-VEN.02.004", nivel=3).exists()
    assert not Tarea.objects.filter(codigo="01-VEN.01.002").exists()  # el hueco no se reutiliza para otra cosa


def test_desactivar_un_proceso_desactiva_sus_tareas_y_subtareas_y_se_puede_reactivar(u, ventas):
    estructura.fijar_activo_proceso(u["jefa"], ventas, False)
    assert not TareaPrincipal.objects.filter(activa=True).exists() and not Tarea.objects.filter(activa=True).exists()
    estructura.fijar_activo_proceso(u["jefa"], ventas, True)
    assert not Tarea.objects.filter(activa=True).exists()  # reactivar el proceso no reactiva lo de abajo por sorpresa
    estructura.fijar_activo_proceso(u["jefa"], ventas, True, con_hijos=True)
    assert Tarea.objects.filter(activa=True).count() == 8 and TareaPrincipal.objects.filter(activa=True).count() == 3


def test_desactivar_una_tarea_desactiva_sus_subtareas_y_no_se_activa_bajo_un_proceso_apagado(u, ventas):
    tp = TareaPrincipal.objects.get(codigo="01-VEN.02")
    estructura.fijar_activa_tarea_principal(u["jefa"], tp, False)
    assert Tarea.objects.filter(padre=tp, activa=True).count() == 0 and Tarea.objects.filter(activa=True).count() == 5
    estructura.fijar_activo_proceso(u["jefa"], ventas, False)
    with pytest.raises(ErrorDeNegocio, match="actívalo primero"):
        estructura.fijar_activa_tarea_principal(u["jefa"], tp, True)
    with pytest.raises(ErrorDeNegocio, match="desactivado"):
        estructura.crear_tarea_principal(u["jefa"], ventas, "Nueva")


# ---- Campos de planificación --------------------------------------------------------------------------------------------------------


def test_responsable_estado_fechas_y_observaciones(u):
    plan = estructura.DatosPlan(responsable_id=cargo("Contador Senior").pk, estado_plan="en_curso", fecha_inicio=date(2026, 12, 1), fecha_termino=date(2026, 12, 8), observaciones="  Cierre de diciembre ")
    p = proceso(u, "Ventas", "VEN", plan=plan)
    p.refresh_from_db()
    assert (p.responsable.nombre, p.estado_plan, p.fecha_inicio, p.fecha_termino, p.observaciones) == ("Contador Senior", "en_curso", date(2026, 12, 1), date(2026, 12, 8), "Cierre de diciembre")


def test_la_fecha_de_termino_no_puede_ser_anterior_en_ningun_nivel(u, ventas):
    mala = estructura.DatosPlan(fecha_inicio=date(2026, 12, 8), fecha_termino=date(2026, 12, 1))
    with pytest.raises(ErrorDeNegocio, match="término"):
        proceso(u, "Otro", "OTR", plan=mala)
    with pytest.raises(ErrorDeNegocio, match="término"):
        estructura.editar_tarea_principal(u["jefa"], TareaPrincipal.objects.first(), "X", mala)
    with pytest.raises(ValidationError):
        Tarea(fecha_inicio=date(2026, 12, 8), fecha_termino=date(2026, 12, 1)).clean()
    with pytest.raises(IntegrityError), transaction.atomic():  # y la base de datos también lo impide
        Tarea.objects.filter(pk=Tarea.objects.first().pk).update(fecha_inicio=date(2026, 12, 8), fecha_termino=date(2026, 12, 1))
    with pytest.raises(ErrorDeNegocio, match="estado"):
        proceso(u, "Otro", "OTR", plan=estructura.DatosPlan(estado_plan="inventado"))


def test_la_subtarea_tambien_lleva_estado_fechas_y_observaciones(u, ventas):
    t = Tarea.objects.get(codigo="01-VEN.01.001")
    t.estado_plan, t.fecha_inicio, t.observaciones = "completado", date(2026, 12, 1), "ok"
    t.save()
    t.refresh_from_db()
    assert (t.estado_plan, t.fecha_inicio, t.observaciones) == ("completado", date(2026, 12, 1), "ok")


# ---- Permisos y catálogo base -----------------------------------------------------------------------------------------------------


def test_solo_gerente_y_jefatura_modifican_la_estructura(u, ventas):
    for quien in ("cont", "lectura"):
        for llamada in (lambda: estructura.crear_proceso(u[quien], "X", "XXX"), lambda: estructura.reordenar_procesos(u[quien], [ventas.pk]),
                        lambda: estructura.fijar_activo_proceso(u[quien], ventas, False), lambda: estructura.cargar_catalogo_base(u[quien]),
                        lambda: estructura.fijar_dependencias(u[quien], ventas, [])):
            with pytest.raises(PermisoDenegado):
                llamada()
    assert estructura.crear_proceso(u["ger"], "Compras", "COM").codigo == "02-COM"


def test_el_catalogo_base_trae_los_11_procesos_en_el_orden_pedido_con_dependencias_editables(u):
    r = estructura.cargar_catalogo_base(u["jefa"])
    assert r["creados"] == [s for s, _, _ in siglas.CATALOGO_BASE] and not r["ya_existian"] and not r["dependencias_omitidas"]
    assert [(p.codigo, p.nombre) for p in Proceso.objects.all()][:3] == [("01-PLA", "Planificación y configuración contable"), ("02-VEN", "Ventas y sala de venta"), ("03-CXC", "Cuentas por cobrar")]
    assert Proceso.objects.count() == 11 and Proceso.objects.get(sigla="CIE").orden == 11
    assert sorted(Proceso.objects.get(sigla="CIE").dependencias.values_list("depende_de__sigla", flat=True)) == ["CON", "IMP"]
    assert estructura.etapas()[0].procesos[0].sigla == "PLA"
    # editable: se puede cambiar una dependencia del catálogo
    estructura.fijar_dependencias(u["jefa"], Proceso.objects.get(sigla="CIE"), [Proceso.objects.get(sigla="CON").pk])
    assert Proceso.objects.get(sigla="CIE").dependencias.count() == 1


def test_el_catalogo_no_duplica_ni_pisa_lo_que_ya_existe(u):
    proceso(u, "Compras", "COM")
    proceso(u, "Tesorería", "TES")
    r = estructura.cargar_catalogo_base(u["jefa"])
    assert sorted(r["ya_existian"]) == ["COM", "TES"] and len(r["creados"]) == 9
    assert Proceso.objects.filter(sigla="COM").count() == 1 and Proceso.objects.get(sigla="COM").orden == 1
    # PLA quedó después de COM, y COM no puede depender de él: esa dependencia se omite y se informa, no se rompe el orden
    assert estructura.cargar_catalogo_base(u["jefa"])["creados"] == [] and Proceso.objects.count() == 11
