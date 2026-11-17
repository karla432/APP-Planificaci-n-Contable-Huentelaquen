"""Cambiar quién ejecuta una tarea (Karla, 17-11-2026): en la reestructuración cualquiera del equipo puede pasarla a otra persona o tomarla."""


import pytest
from django.test import Client
from django.urls import reverse

from nucleo.models import Colaborador, EventoAuditoria, Ocurrencia
from nucleo.servicios import ejecucion, periodos
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado
from pruebas.ayudas import anio_abierto, cargo, persona, tarea, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture
def equipo():
    anio_abierto()
    cont, anal, jefa, ger = cargo("Contador Senior"), cargo("Analista Contable"), cargo("Jefa de Control"), cargo("Gerente AyF")
    p = {"cont": persona("Contadora", cont), "anal": persona("Analista", anal), "jefa": persona("Jefa", jefa), "ger": persona("Gerente", ger)}
    u = {"cont": usuario_con_rol("cont", "COLABORADOR", p["cont"]), "anal": usuario_con_rol("anal", "COLABORADOR", p["anal"]),
         "jefa": usuario_con_rol("jefa", "JEFATURA", p["jefa"]), "ger": usuario_con_rol("ger", "GERENTE", p["ger"]), "lectura": usuario_con_rol("lectura", "LECTURA")}
    t = tarea("T-1", cont, "CIERRE_DIA_HABIL", revisa=jefa, n=3)
    periodos.abrir_mes(2026, 12, usuario=None)
    o = Ocurrencia.objects.get(tarea=t)
    return {"u": u, "p": p, "o": o, "cargos": {"cont": cont, "anal": anal, "jefa": jefa, "ger": ger}}


def test_una_colaboradora_pasa_la_tarea_a_otra_persona_y_queda_en_la_bitacora(equipo):
    o, u, p = equipo["o"], equipo["u"], equipo["p"]
    assert o.colaborador == p["cont"]
    ejecucion.reasignar(o, u["cont"], p["anal"].pk, "está de vacaciones")
    o.refresh_from_db()
    assert o.colaborador == p["anal"] and o.cargo_ejecuta.nombre == "Analista Contable"
    e = EventoAuditoria.objects.get(accion="ocurrencia.reasignada", entidad_id=str(o.pk))
    assert e.antes["colaborador"] == "Contadora" and e.despues["colaborador"] == "Analista" and e.motivo == "está de vacaciones"


def test_cualquiera_del_equipo_puede_tomar_una_tarea_ajena(equipo):
    o, u, p = equipo["o"], equipo["u"], equipo["p"]
    ejecucion.reasignar(o, u["anal"], p["anal"].pk)  # la analista se la queda para sí
    o.refresh_from_db()
    assert o.colaborador == p["anal"]


def test_quien_revisa_no_puede_ser_quien_la_hace(equipo):
    with pytest.raises(PermisoDenegado, match="Quien revisa"):
        ejecucion.reasignar(equipo["o"], equipo["u"]["cont"], equipo["p"]["jefa"].pk)
    equipo["o"].refresh_from_db()
    assert equipo["o"].colaborador == equipo["p"]["cont"]
    assert equipo["p"]["jefa"] not in ejecucion.candidatos_a_ejecutar(equipo["o"]) and equipo["p"]["cont"] not in ejecucion.candidatos_a_ejecutar(equipo["o"])


@pytest.mark.parametrize("estado", [Ocurrencia.HECHA, Ocurrencia.REVISADA, Ocurrencia.NO_APLICA])
def test_una_tarea_ya_hecha_no_se_reasigna(equipo, estado):
    o = equipo["o"]
    Ocurrencia.objects.filter(pk=o.pk).update(estado=estado)
    o.refresh_from_db()
    with pytest.raises(ErrorDeNegocio, match="ya no se puede reasignar"):
        ejecucion.reasignar(o, equipo["u"]["cont"], equipo["p"]["anal"].pk)


@pytest.mark.parametrize("estado", [Ocurrencia.PENDIENTE, Ocurrencia.DEVUELTA, Ocurrencia.BLOQUEADA])
def test_pendiente_devuelta_o_bloqueada_si_se_reasignan(equipo, estado):
    o = equipo["o"]
    Ocurrencia.objects.filter(pk=o.pk).update(estado=estado)
    o.refresh_from_db()
    ejecucion.reasignar(o, equipo["u"]["ger"], equipo["p"]["anal"].pk)
    o.refresh_from_db()
    assert o.colaborador == equipo["p"]["anal"] and o.estado == estado


def test_quien_solo_lee_no_reasigna_y_hay_que_elegir_a_alguien_valido(equipo):
    o, u, p = equipo["o"], equipo["u"], equipo["p"]
    with pytest.raises(PermisoDenegado):
        ejecucion.reasignar(o, u["lectura"], p["anal"].pk)
    for malo in (None, 0, 99999):
        with pytest.raises(ErrorDeNegocio, match="Elige"):
            ejecucion.reasignar(o, u["cont"], malo)
    with pytest.raises(ErrorDeNegocio, match="ya es quien"):
        ejecucion.reasignar(o, u["cont"], p["cont"].pk)
    Colaborador.objects.filter(pk=p["anal"].pk).update(activo=False)
    with pytest.raises(ErrorDeNegocio, match="Elige"):
        ejecucion.reasignar(o, u["cont"], p["anal"].pk)


def test_una_persona_sin_cargo_vigente_no_puede_recibirla(equipo):
    sin_cargo = Colaborador.objects.create(nombre="Sin cargo")
    with pytest.raises(ErrorDeNegocio, match="cargo vigente"):
        ejecucion.reasignar(equipo["o"], equipo["u"]["cont"], sin_cargo.pk)


def test_un_periodo_cerrado_no_admite_el_cambio(equipo):
    o = equipo["o"]
    o.periodo.estado = "cerrado"
    o.periodo.save()
    o.refresh_from_db()
    with pytest.raises(PermisoDenegado):
        ejecucion.reasignar(o, equipo["u"]["cont"], equipo["p"]["anal"].pk)


def test_desde_la_pantalla_se_pasa_se_toma_y_el_historial_lo_muestra(equipo):
    o, u, p = equipo["o"], equipo["u"], equipo["p"]
    c = Client()
    c.force_login(u["cont"])
    html = c.get(reverse("detalle_ocurrencia", args=[o.pk])).content.decode()
    assert "Quién la hace" in html and "Pasarla a otra persona" in html and "Analista" in html and "Jefa" not in html.split("Pasarla a otra persona")[1].split("</select>")[0]
    r = c.post(reverse("ocurrencia_accion", args=[o.pk, "reasignar"]), {"para": str(p["anal"].pk), "motivo": "apoyo", "siguiente": "/"})
    assert r.status_code == 302
    o.refresh_from_db()
    assert o.colaborador == p["anal"]
    c2 = Client()
    c2.force_login(u["ger"])
    assert "Cambió quién la hace" in c2.get(reverse("detalle_ocurrencia", args=[o.pk])).content.decode()
    c2.post(reverse("ocurrencia_accion", args=[o.pk, "tomar"]), {"siguiente": "/"})  # el gerente se la queda
    o.refresh_from_db()
    assert o.colaborador == p["ger"]


def test_el_servidor_rechaza_a_quien_no_tiene_perfil_aunque_conozca_el_enlace(equipo):
    c = Client()
    c.force_login(equipo["u"]["lectura"])
    r = c.post(reverse("ocurrencia_accion", args=[equipo["o"].pk, "reasignar"]), {"para": str(equipo["p"]["anal"].pk)})
    assert r.status_code == 403
    equipo["o"].refresh_from_db()
    assert equipo["o"].colaborador == equipo["p"]["cont"]
