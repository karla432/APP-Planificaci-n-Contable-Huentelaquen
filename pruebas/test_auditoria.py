"""Bitácora append-only y sellada (RC-04 / AM-08)."""
import pytest
from django.contrib.auth import get_user_model
from django.db import connection, DatabaseError

from nucleo.models import EventoAuditoria
from nucleo.servicios import auditoria

pytestmark = pytest.mark.django_db


def test_registrar_guarda_quien_que_y_antes_despues():
    u = get_user_model().objects.create_user("karla", password="x" * 12)
    ev = auditoria.registrar("tarea.editada", usuario=u, entidad="Tarea", entidad_id="1", antes={"a": 1}, despues={"a": 2})
    ev.refresh_from_db()
    assert ev.usuario == u and ev.accion == "tarea.editada" and ev.antes == {"a": 1} and ev.despues == {"a": 2}
    assert ev.momento is not None and len(ev.sello) == 64


def test_cada_sello_encadena_el_anterior():
    a = auditoria.registrar("uno")
    b = auditoria.registrar("dos")
    assert a.sello_anterior == "" and b.sello_anterior == a.sello and a.sello != b.sello


def test_cadena_integra_se_verifica():
    for i in range(3):
        auditoria.registrar(f"evento.{i}", despues={"i": i})
    assert auditoria.verificar_cadena() == []


def test_no_se_puede_actualizar_un_evento():
    ev = auditoria.registrar("uno")
    with pytest.raises(DatabaseError):
        EventoAuditoria.objects.filter(pk=ev.pk).update(accion="otra")


def test_no_se_puede_borrar_un_evento():
    ev = auditoria.registrar("uno")
    with pytest.raises(DatabaseError):
        EventoAuditoria.objects.filter(pk=ev.pk).delete()


def test_alterar_una_fila_saltandose_los_triggers_se_detecta():
    a = auditoria.registrar("uno", despues={"v": 1})
    auditoria.registrar("dos")
    with connection.cursor() as c:  # quien tenga el archivo de la base puede quitar los triggers…
        c.execute("DROP TRIGGER IF EXISTS auditoria_sin_update")
        c.execute("UPDATE nucleo_eventoauditoria SET despues = '{\"v\": 999}' WHERE id = %s", [a.pk])
    # …pero el sello encadenado lo delata.
    assert auditoria.verificar_cadena() == [a.pk]
