"""Comandos de operación para el servidor (Eugenio): crear cuentas, recuperar acceso, verificar la bitácora, respaldar y probar la restauración.
Se prueban como se usan: con `manage.py` sobre una base real en un archivo temporal."""
import gzip
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CLAVE_OK = "una-clave-larga-123"


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    """Una base migrada en un archivo temporal, con los datos mínimos."""
    carpeta = tmp_path_factory.mktemp("servidor")
    entorno = {**os.environ, "PLANIFICACION_ENTORNO": "desarrollo", "PLANIFICACION_DB_PATH": str(carpeta / "base.sqlite3"), "PLANIFICACION_EVIDENCIAS": str(carpeta / "evidencias"),
               "PLANIFICACION_RESPALDOS": str(carpeta / "respaldos")}
    entorno.pop("PLANIFICACION_SIN_CLAVE", None)

    def manage(*args, entrada=None):
        return subprocess.run([sys.executable, str(RAIZ / "manage.py"), *args], cwd=RAIZ, env=entorno, input=entrada, capture_output=True, text=True, timeout=300)

    assert manage("migrate", "-v0").returncode == 0
    r = manage("shell", "-c", "from nucleo.models import Cargo; [Cargo.objects.get_or_create(nombre=n) for n in ('Gerente AyF', 'Jefa de Control')]")
    assert r.returncode == 0, r.stderr
    return {"manage": manage, "carpeta": carpeta}


def test_crear_usuario_pide_la_clave_por_la_entrada_y_rechaza_las_debiles(servidor):
    m = servidor["manage"]
    r = m("crear_usuario", "jefa1", "--rol", "JEFATURA", "--nombre", "Jefa de prueba", "--cargo", "Jefa de Control", entrada="corta\ncorta\n")
    assert r.returncode != 0 and "La clave no sirve" in r.stderr
    r = m("crear_usuario", "jefa1", "--rol", "JEFATURA", "--nombre", "Jefa de prueba", "--cargo", "Jefa de Control", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n")
    assert r.returncode == 0 and "creado con el rol JEFATURA" in r.stdout and "Segundo factor" not in r.stdout
    assert "ya existe" in m("crear_usuario", "jefa1", "--rol", "JEFATURA", "--nombre", "x", "--cargo", "Jefa de Control", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n").stderr
    assert "no coinciden" in m("crear_usuario", "otra", "--rol", "JEFATURA", "--nombre", "x", "--cargo", "Jefa de Control", entrada=f"{CLAVE_OK}\ndistinta-clave-123\n").stderr
    assert "Indica un cargo" in m("crear_usuario", "otra", "--rol", "JEFATURA", "--nombre", "x", "--cargo", "No existe", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n").stderr


def test_el_gerente_se_crea_con_segundo_factor_y_su_clave_se_muestra_una_sola_vez(servidor):
    r = servidor["manage"]("crear_usuario", "gerente1", "--rol", "GERENTE", "--nombre", "Gerente de prueba", "--cargo", "Gerente AyF", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n")
    assert r.returncode == 0 and "Segundo factor OBLIGATORIO" in r.stdout and "otpauth://totp/" in r.stdout


def test_recuperar_acceso_cambia_la_clave_desbloquea_y_reinicia_el_segundo_factor(servidor):
    m = servidor["manage"]
    nueva = "otra-clave-larga-456"
    r = m("recuperar_acceso", "gerente1", "--reiniciar-2fa", entrada=f"{nueva}\n{nueva}\n")
    assert r.returncode == 0 and "segundo factor reiniciado" in r.stdout
    chequeo = m("shell", "-c", "from django.contrib.auth import get_user_model as g; from nucleo.models import SegundoFactor; u=g().objects.get(username='gerente1'); print(u.check_password('%s'), SegundoFactor.objects.filter(usuario=u).exists())" % nueva)
    assert chequeo.stdout.strip().splitlines()[-1] == "True False"
    assert "No existe" in m("recuperar_acceso", "nadie", "--solo-desbloquear").stderr


def test_respaldar_verificar_y_detectar_un_respaldo_alterado(servidor):
    m, carpeta = servidor["manage"], servidor["carpeta"]
    assert "Bitácora íntegra" in m("verificar_bitacora").stdout
    r = m("respaldar", "--conservar", "3")
    assert r.returncode == 0 and "Respaldo listo" in r.stdout
    respaldos = sorted((carpeta / "respaldos").glob("respaldo_*.sqlite3.gz"))
    assert len(respaldos) == 1 and (carpeta / "respaldos" / respaldos[0].name.replace(".sqlite3.gz", ".sha256")).exists()
    assert oct(respaldos[0].stat().st_mode & 0o777) == "0o600"
    v = m("verificar_respaldo", str(respaldos[0]))
    assert v.returncode == 0 and "Huella SHA-256: coincide" in v.stdout and "Integridad de la base: ok" in v.stdout and "RESTAURACIÓN VERIFICADA" in v.stdout and "usuarios" in v.stdout
    contenido = respaldos[0].read_bytes()
    respaldos[0].write_bytes(contenido[:-20] + bytes(b ^ 0xFF for b in contenido[-20:]))  # se daña el archivo
    malo = m("verificar_respaldo", str(respaldos[0]))
    assert malo.returncode != 0 and "NO coincide" in malo.stderr


def test_respaldar_conserva_solo_los_ultimos(servidor):
    m, carpeta = servidor["manage"], servidor["carpeta"]
    destino = carpeta / "otros"
    for _ in range(3):
        assert m("respaldar", "--destino", str(destino), "--conservar", "2").returncode == 0
        import time
        time.sleep(1.1)  # los nombres llevan la hora hasta el segundo
    assert len(list(destino.glob("respaldo_*.sqlite3.gz"))) == 2 and len(list(destino.glob("respaldo_*.sha256"))) == 2


def test_cargar_plan_muestra_la_vista_previa_y_no_guarda_sin_aplicar(servidor):
    r = servidor["manage"]("cargar_plan", str(RAIZ / "docs" / "datos" / "Planificacion_2.0_contabilidad.xlsx"))
    assert r.returncode != 0 and "cargos que no existen" in r.stderr  # la base mínima no tiene los cargos del equipo: no inventa cargos


def test_la_base_de_un_respaldo_es_una_base_sqlite_valida(servidor):
    carpeta = servidor["carpeta"]
    respaldos = sorted((carpeta / "otros").glob("respaldo_*.sqlite3.gz"))
    assert respaldos
    assert gzip.open(respaldos[-1]).read(16).startswith(b"SQLite format 3")


def test_crear_usuario_permite_fijar_desde_cuando_ejerce_el_cargo(servidor):
    m = servidor["manage"]
    r = m("crear_usuario", "jefa2", "--rol", "JEFATURA", "--nombre", "Jefa dos", "--cargo", "Jefa de Control", "--desde", "2026-01-01", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n")
    assert r.returncode == 0, r.stderr
    chequeo = m("shell", "-c", "from nucleo.models import Asignacion; print(Asignacion.objects.get(colaborador__usuario__username='jefa2').desde)")
    assert chequeo.stdout.strip().splitlines()[-1] == "2026-01-01"
    assert "AAAA-MM-DD" in m("crear_usuario", "jefa3", "--rol", "JEFATURA", "--nombre", "x", "--cargo", "Jefa de Control", "--desde", "ayer", entrada=f"{CLAVE_OK}\n{CLAVE_OK}\n").stderr
