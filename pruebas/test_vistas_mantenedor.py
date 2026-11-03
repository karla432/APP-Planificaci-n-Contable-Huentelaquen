"""Pantallas del Mantenedor: Tareas, Procesos y Usuarios."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from nucleo import permisos
from nucleo.models import Proceso, Tarea
from nucleo.servicios import mantenedor
from pruebas.ayudas import cargo, persona, usuario_con_rol

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr("nucleo.servicios.reloj.hoy", lambda: date(2026, 12, 4))


@pytest.fixture
def mundo():
    jefa, cont, ger, anal = cargo("Jefa de Control"), cargo("Contador Senior"), cargo("Gerente AyF"), cargo("Analista Contable")
    u = {"jefa": usuario_con_rol("jefa", "JEFATURA", persona("Jefa", jefa)), "ger": usuario_con_rol("ger", "GERENTE", persona("Gerente", ger)),
         "cont": usuario_con_rol("cont", "COLABORADOR", persona("Contadora", cont)), "admin": usuario_con_rol("admin", "ADMIN_SISTEMA"),
         "lectura": usuario_con_rol("lectura", "LECTURA")}
    proceso = Proceso.objects.create(nombre="Compras")
    t = mantenedor.crear_tarea(u["jefa"], mantenedor.DatosTarea(proceso_id=proceso.pk, tarea_principal="Libro de compras", subtarea="Cotejar el RCV contra Odoo", cargo_ejecuta_id=cont.pk, tipo="CIERRE_DIA_HABIL", n=2))
    return {"u": u, "proceso": proceso, "cont": cont, "anal": anal, "ger": ger, "tarea": t}


def cli(usuario):
    c = Client()
    c.force_login(usuario)
    return c


# ---- Permisos de acceso ---------------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["mant_tareas", "mant_procesos", "mant_tarea_nueva"])
@pytest.mark.parametrize("quien,esperado", [("jefa", 200), ("ger", 200), ("cont", 403), ("admin", 403), ("lectura", 403)])
def test_tareas_y_procesos_solo_para_gerente_y_jefatura(mundo, nombre, quien, esperado):
    assert cli(mundo["u"][quien]).get(reverse(nombre)).status_code == esperado


@pytest.mark.parametrize("nombre", ["mant_usuarios", "mant_usuario_nuevo"])
@pytest.mark.parametrize("quien,esperado", [("ger", 200), ("admin", 200), ("jefa", 403), ("cont", 403), ("lectura", 403)])
def test_usuarios_solo_para_gerente_y_administrador(mundo, nombre, quien, esperado):
    assert cli(mundo["u"][quien]).get(reverse(nombre)).status_code == esperado


# ---- Tareas ---------------------------------------------------------------------------------------------


def test_la_lista_muestra_proceso_tarea_subtarea_responsable_y_periodicidad(mundo):
    html = cli(mundo["u"]["jefa"]).get(reverse("mant_tareas")).content.decode()
    for texto in ("Proceso", "Tarea principal", "Subtarea", "Responsable", "Periodicidad", "Compras", "Libro de compras", "Cotejar el RCV contra Odoo", "Contador Senior", "Día hábil 2 del cierre"):
        assert texto in html, texto


def test_la_lista_se_filtra_por_proceso_responsable_y_texto(mundo):
    otro = Proceso.objects.create(nombre="Pagos")
    mantenedor.crear_tarea(mundo["u"]["jefa"], mantenedor.DatosTarea(proceso_id=otro.pk, tarea_principal="Nómina", subtarea="Preparar la nómina", cargo_ejecuta_id=mundo["anal"].pk, tipo="SEMANAL", dia_semana=2))
    c = cli(mundo["u"]["jefa"])
    html = c.get(reverse("mant_tareas"), {"proceso": otro.pk}).content.decode()
    assert "Preparar la nómina" in html and "Cotejar el RCV" not in html
    assert "Cotejar el RCV" in c.get(reverse("mant_tareas"), {"cargo": mundo["cont"].pk}).content.decode()
    assert "Preparar la nómina" not in c.get(reverse("mant_tareas"), {"q": "rcv"}).content.decode()


def datos_post(mundo, **cambios):
    d = {"proceso": mundo["proceso"].pk, "tarea_principal": "Libro de ventas", "subtarea": "Cuadrar el libro de ventas", "cargo_ejecuta": mundo["cont"].pk,
         "tipo": "SEMANAL", "dia_semana": "0", "franja": "mañana", "ajuste": "siguiente", "activa": "on", "cargo_revisa": mundo["ger"].pk, "horas": "0,5"}
    d.update(cambios)
    return d


def test_crear_una_tarea_desde_el_formulario(mundo):
    r = cli(mundo["u"]["jefa"]).post(reverse("mant_tarea_nueva"), datos_post(mundo))
    assert r.status_code == 302
    t = Tarea.objects.get(subtarea="Cuadrar el libro de ventas")
    assert (t.regla_tipo, t.regla_dia_semana, t.regla_franja, t.cargo_revisa.nombre, t.minutos_estimados) == ("SEMANAL", 0, "mañana", "Gerente AyF", 30)


def test_un_dato_invalido_vuelve_al_formulario_con_el_error_y_sin_guardar(mundo):
    r = cli(mundo["u"]["jefa"]).post(reverse("mant_tarea_nueva"), datos_post(mundo, tipo="CIERRE_HITO", n="7"))
    assert r.status_code == 200 and "día hábil 8, 9 o 10" in r.content.decode()
    assert not Tarea.objects.filter(subtarea="Cuadrar el libro de ventas").exists()


def test_editar_una_tarea_desde_el_formulario_y_ver_el_aviso_de_vigencia(mundo):
    url = reverse("mant_tarea_editar", args=[mundo["tarea"].pk])
    c = cli(mundo["u"]["ger"])
    assert "próximo mes" in c.get(url).content.decode()
    r = c.post(url, datos_post(mundo, subtarea="Cotejar el RCV (corregido)", tipo="CIERRE_DIA_HABIL", n="3", dia_semana=""))
    assert r.status_code == 302
    mundo["tarea"].refresh_from_db()
    assert mundo["tarea"].subtarea == "Cotejar el RCV (corregido)" and mundo["tarea"].regla_n == 3


def test_quien_no_puede_editar_tampoco_puede_enviar_el_formulario(mundo):
    r = cli(mundo["u"]["cont"]).post(reverse("mant_tarea_editar", args=[mundo["tarea"].pk]), datos_post(mundo))
    assert r.status_code == 403
    mundo["tarea"].refresh_from_db()
    assert mundo["tarea"].subtarea == "Cotejar el RCV contra Odoo"


def test_meses_especificos_desde_el_formulario(mundo):
    r = cli(mundo["u"]["jefa"]).post(reverse("mant_tarea_nueva"), datos_post(mundo, tipo="MESES", meses=["4", "6"], dia="20", dia_semana=""))
    assert r.status_code == 302
    t = Tarea.objects.get(subtarea="Cuadrar el libro de ventas")
    assert t.regla_meses == "4,6" and t.regla_dia == 20


# ---- Procesos -------------------------------------------------------------------------------------------


def test_crear_renombrar_y_desactivar_un_proceso(mundo):
    c = cli(mundo["u"]["jefa"])
    assert c.post(reverse("mant_procesos"), {"accion": "crear", "nombre": "Remuneraciones"}).status_code == 302
    p = Proceso.objects.get(nombre="Remuneraciones")
    c.post(reverse("mant_procesos"), {"accion": "editar", "proceso": p.pk, "nombre": "Remuneraciones y leyes", "activo": ""})
    p.refresh_from_db()
    assert p.nombre == "Remuneraciones y leyes" and p.activo is False
    html = c.get(reverse("mant_procesos")).content.decode()
    assert "Remuneraciones y leyes" in html and "Compras" in html and "tarea" in html.lower()


# ---- Usuarios -------------------------------------------------------------------------------------------


def test_crear_un_usuario_desde_el_formulario(mundo):
    r = cli(mundo["u"]["ger"]).post(reverse("mant_usuario_nuevo"), {"username": "analista", "nombre": "Analista de ejemplo", "correo": "", "rol": "COLABORADOR", "cargo": mundo["anal"].pk})
    assert r.status_code == 302
    u = get_user_model().objects.get(username="analista")
    assert permisos.rol_de(u) == "COLABORADOR"


def test_el_formulario_de_usuarios_avisa_que_la_clave_viene_despues(mundo):
    assert "etapa de seguridad" in cli(mundo["u"]["ger"]).get(reverse("mant_usuario_nuevo")).content.decode()


def test_la_lista_de_usuarios_muestra_perfil_cargo_y_estado(mundo):
    html = cli(mundo["u"]["ger"]).get(reverse("mant_usuarios")).content.decode()
    for texto in ("ger", "GERENTE", "Gerente AyF", "jefa", "JEFATURA", "Activo"):
        assert texto in html, texto


def test_editar_un_usuario_y_la_proteccion_del_propio_perfil(mundo):
    u = get_user_model().objects.get(username="cont")
    c = cli(mundo["u"]["ger"])
    r = c.post(reverse("mant_usuario_editar", args=[u.pk]), {"nombre": "Contadora", "correo": "", "rol": "COLABORADOR", "cargo": mundo["anal"].pk, "activo": "on"})
    assert r.status_code == 302
    propio = c.post(reverse("mant_usuario_editar", args=[mundo["u"]["ger"].pk]), {"nombre": "Gerente", "correo": "", "rol": "LECTURA", "activo": "on"})
    assert propio.status_code == 403 and permisos.rol_de(mundo["u"]["ger"]) == "GERENTE"


def test_el_formulario_de_tarea_pide_los_minutos_de_revision_y_los_guarda(mundo):
    c = cli(mundo["u"]["jefa"])
    html = c.get(reverse("mant_tarea_nueva")).content.decode()
    assert 'name="minutos_revision"' in html and "0 minutos extra" in html and 'name="dh_inicio"' in html  # explica el valor general
    assert c.post(reverse("mant_tarea_nueva"), datos_post(mundo, minutos_revision="45")).status_code == 302
    t = Tarea.objects.get(subtarea="Cuadrar el libro de ventas")
    assert t.minutos_revision == 45
    url = reverse("mant_tarea_editar", args=[t.pk])
    assert 'value="45"' in c.get(url).content.decode()
    c.post(url, datos_post(mundo, minutos_revision=""))
    t.refresh_from_db()
    assert t.minutos_revision is None  # vacío = el valor general
    r = c.post(reverse("mant_tarea_nueva"), datos_post(mundo, subtarea="Otra", minutos_revision="999"))
    assert r.status_code == 200 and "minutos de revisión" in r.content.decode()
