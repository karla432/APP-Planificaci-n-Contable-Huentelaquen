"""Ejecución: marcar, revisar, devolver, «recibido» y «no aplica», con la segregación de funciones validada en el servidor."""
from datetime import date

import pytest

from nucleo.models import EventoAuditoria, Ocurrencia, Periodo, SolicitudNoAplica
from nucleo.servicios import ejecucion, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture
def mundo():
    jefa, cont, anal, ger = cargo("Jefa Gestión y Control"), cargo("Contadora Senior"), cargo("Analista Contable"), cargo("Gerente AyF")
    bodega = cargo("Bodega", externo=True)
    pers = {"jefa": persona("Jefa", jefa), "cont": persona("Contadora", cont), "anal": persona("Analista", anal), "ger": persona("Gerente", ger)}
    u = {
        "jefa": usuario_con_rol("jefa", "JEFATURA", pers["jefa"]), "cont": usuario_con_rol("cont", "COLABORADOR", pers["cont"]),
        "anal": usuario_con_rol("anal", "COLABORADOR", pers["anal"]), "ger": usuario_con_rol("ger", "GERENTE", pers["ger"]),
        "lectura": usuario_con_rol("lectura", "LECTURA"), "admin": usuario_con_rol("admin", "ADMIN_SISTEMA"),
    }
    anio_abierto()
    tarea("TAR-0001", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=1)  # la hace la Contadora, la revisa la Jefa
    tarea("TAR-0002", jefa, "CIERRE_DIA_HABIL", revisa=ger, n=1)  # la hace la Jefa, la revisa el Gerente (P1)
    tarea("TAR-0003", bodega, "CIERRE_DIA_HABIL", revisa=jefa, n=1)  # externo: la Jefa marca «Recibido»
    periodos.abrir_mes(2026, 12, usuario=None)
    o = {x.tarea.codigo: x for x in Ocurrencia.objects.select_related("tarea")}
    return {"u": u, "o": o}


def test_el_colaborador_marca_lo_suyo_y_la_hora_la_fija_el_servidor(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    o.refresh_from_db()
    assert o.estado == "hecha" and o.hecha_por == mundo["u"]["cont"]
    assert o.hecha_en is not None and o.primera_hecha_en == o.hecha_en
    assert EventoAuditoria.objects.filter(accion="ocurrencia.hecha", entidad_id=str(o.pk)).exists()


def test_no_hay_forma_de_indicar_la_hora_de_la_marca(mundo):
    with pytest.raises(TypeError):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], mundo["u"]["cont"], hecha_en=date(2026, 12, 1))


def test_un_colaborador_no_marca_tareas_ajenas(mundo):
    o = mundo["o"]["TAR-0001"]
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_hecha(o, mundo["u"]["anal"])
    o.refresh_from_db()
    assert o.estado == "pendiente" and o.hecha_en is None


@pytest.mark.parametrize("quien", ["lectura", "admin", "jefa", "ger"])
def test_ni_lectura_ni_admin_ni_jefatura_ni_gerente_marcan_la_tarea_de_otro(mundo, quien):
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], mundo["u"][quien])


def test_no_se_marca_dos_veces(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    with pytest.raises(ErrorDeNegocio, match="pendiente"):
        ejecucion.marcar_hecha(o, mundo["u"]["cont"])


def test_la_jefa_revisa_lo_que_hizo_la_contadora(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    ejecucion.revisar(o, mundo["u"]["jefa"])
    o.refresh_from_db()
    assert o.estado == "revisada" and o.revisada_por == mundo["u"]["jefa"] and o.revisada_en is not None


def test_nadie_revisa_su_propia_tarea(mundo):
    o = mundo["o"]["TAR-0002"]  # la ejecuta la Jefa
    ejecucion.marcar_hecha(o, mundo["u"]["jefa"])
    with pytest.raises(PermisoDenegado):
        ejecucion.revisar(o, mundo["u"]["jefa"])  # ni siquiera si fuera su cargo revisor
    ejecucion.revisar(o, mundo["u"]["ger"])  # la revisa el Gerente (P1)
    o.refresh_from_db()
    assert o.estado == "revisada"


def test_la_autorrevision_se_rechaza_aunque_el_gerente_haya_marcado_por_excepcion(mundo):
    o = mundo["o"]["TAR-0002"]
    ejecucion.marcar_por_excepcion(o, mundo["u"]["ger"], motivo="La Jefa estaba con licencia")
    with pytest.raises(PermisoDenegado, match="propia"):
        ejecucion.revisar(o, mundo["u"]["ger"])


@pytest.mark.parametrize("quien", ["cont", "anal", "lectura", "admin"])
def test_quien_no_es_el_revisor_no_revisa(mundo, quien):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    with pytest.raises(PermisoDenegado):
        ejecucion.revisar(o, mundo["u"][quien])


def test_no_se_revisa_lo_que_no_esta_hecho(mundo):
    with pytest.raises(ErrorDeNegocio, match="hecha"):
        ejecucion.revisar(mundo["o"]["TAR-0001"], mundo["u"]["jefa"])


def test_devolver_exige_comentario_y_la_primera_marca_sigue_siendo_la_del_kpi(mundo):
    o = mundo["o"]["TAR-0001"]
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])
    primera = Ocurrencia.objects.get(pk=o.pk).primera_hecha_en
    with pytest.raises(ErrorDeNegocio, match="comentario"):
        ejecucion.devolver(o, mundo["u"]["jefa"], comentario="  ")
    ejecucion.devolver(o, mundo["u"]["jefa"], comentario="Falta cuadrar el saldo")
    o.refresh_from_db()
    assert o.estado == "devuelta" and o.comentario_devolucion == "Falta cuadrar el saldo"
    ejecucion.marcar_hecha(o, mundo["u"]["cont"])  # vuelve a marcarla
    o.refresh_from_db()
    assert o.estado == "hecha" and o.primera_hecha_en == primera  # el «a tiempo» se mide con la primera marca


def test_el_externo_lo_marca_como_recibido_la_jefa_y_no_necesita_revision(mundo):
    o = mundo["o"]["TAR-0003"]
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_recibida(o, mundo["u"]["cont"])
    ejecucion.marcar_recibida(o, mundo["u"]["jefa"])
    o.refresh_from_db()
    assert o.estado == "hecha" and o.tipo_marca == "RECIBIDA" and o.hecha_por == mundo["u"]["jefa"]
    with pytest.raises(ErrorDeNegocio, match="recibid"):
        ejecucion.revisar(o, mundo["u"]["ger"])


def test_una_tarea_interna_no_se_marca_como_recibida_ni_una_externa_como_hecha(mundo):
    with pytest.raises(ErrorDeNegocio):
        ejecucion.marcar_recibida(mundo["o"]["TAR-0001"], mundo["u"]["jefa"])
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0003"], mundo["u"]["jefa"])


def test_marca_por_excepcion_solo_el_gerente_y_con_motivo(mundo):
    o = mundo["o"]["TAR-0001"]
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_por_excepcion(o, mundo["u"]["jefa"], motivo="x")
    with pytest.raises(ErrorDeNegocio, match="motivo"):
        ejecucion.marcar_por_excepcion(o, mundo["u"]["ger"], motivo=" ")
    ejecucion.marcar_por_excepcion(o, mundo["u"]["ger"], motivo="Contadora con licencia")
    o.refresh_from_db()
    assert o.por_excepcion and o.motivo_excepcion == "Contadora con licencia" and o.estado == "hecha"
    assert EventoAuditoria.objects.filter(accion="ocurrencia.hecha_por_excepcion").exists()


# ---- No aplica ------------------------------------------------------------------------------------


def test_no_aplica_la_solicita_el_dueno_y_la_aprueba_otra_persona(mundo):
    o = mundo["o"]["TAR-0001"]
    s = ejecucion.solicitar_no_aplica(o, mundo["u"]["cont"], motivo="Este mes no hubo movimientos")
    with pytest.raises(PermisoDenegado):
        ejecucion.resolver_no_aplica(s, mundo["u"]["cont"], aprobar=True)  # no se aprueba lo propio
    with pytest.raises(PermisoDenegado):
        ejecucion.resolver_no_aplica(s, mundo["u"]["anal"], aprobar=True)  # un colaborador no aprueba
    ejecucion.resolver_no_aplica(s, mundo["u"]["jefa"], aprobar=True)
    o.refresh_from_db()
    s.refresh_from_db()
    assert o.estado == "no_aplica" and s.estado == "aprobada" and s.resuelta_por == mundo["u"]["jefa"]


def test_no_aplica_rechazada_deja_la_tarea_pendiente(mundo):
    o = mundo["o"]["TAR-0001"]
    s = ejecucion.solicitar_no_aplica(o, mundo["u"]["cont"], motivo="No corresponde")
    ejecucion.resolver_no_aplica(s, mundo["u"]["jefa"], aprobar=False)
    o.refresh_from_db()
    s.refresh_from_db()
    assert o.estado == "pendiente" and s.estado == "rechazada"


def test_no_aplica_exige_motivo_y_no_se_pide_por_tareas_ajenas(mundo):
    o = mundo["o"]["TAR-0001"]
    with pytest.raises(ErrorDeNegocio, match="motivo"):
        ejecucion.solicitar_no_aplica(o, mundo["u"]["cont"], motivo="")
    with pytest.raises(PermisoDenegado):
        ejecucion.solicitar_no_aplica(o, mundo["u"]["anal"], motivo="No me toca")
    assert SolicitudNoAplica.objects.count() == 0


def test_la_jefa_pide_no_aplica_de_lo_suyo_y_la_aprueba_el_gerente(mundo):
    o = mundo["o"]["TAR-0002"]
    s = ejecucion.solicitar_no_aplica(o, mundo["u"]["jefa"], motivo="Sin movimientos")
    with pytest.raises(PermisoDenegado):
        ejecucion.resolver_no_aplica(s, mundo["u"]["jefa"], aprobar=True)
    ejecucion.resolver_no_aplica(s, mundo["u"]["ger"], aprobar=True)
    o.refresh_from_db()
    assert o.estado == "no_aplica"


def test_un_periodo_cerrado_no_admite_marcas(mundo):
    Periodo.objects.update(estado="cerrado")
    with pytest.raises(ErrorDeNegocio, match="cerrado"):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], mundo["u"]["cont"])


def test_una_cuenta_sin_perfil_no_hace_nada(mundo):
    sin_perfil = usuario_con_rol("fantasma", None)
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], sin_perfil)


def test_ser_superusuario_no_da_permisos_de_la_aplicacion(mundo):
    from django.contrib.auth import get_user_model
    su = get_user_model().objects.create_superuser("root", password="x" * 12)
    with pytest.raises(PermisoDenegado):
        ejecucion.marcar_hecha(mundo["o"]["TAR-0001"], su)
