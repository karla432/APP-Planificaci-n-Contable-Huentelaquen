"""Prueba de restauración: abre un respaldo en una base temporal, comprueba su integridad y la cadena de la bitácora, y cuenta lo importante.
Es la evidencia que exige la puerta G3 antes de producción. No toca la base en uso."""
import gzip
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restaura un respaldo (.sqlite3.gz) en una base temporal y lo verifica."

    def add_arguments(self, parser):
        parser.add_argument("archivo")

    def handle(self, *args, archivo, **opciones):
        ruta = Path(archivo)
        if not ruta.exists():
            raise CommandError(f"No existe {ruta}.")
        huellas = ruta.with_name(ruta.name.replace(".sqlite3.gz", ".sha256"))
        if huellas.exists():
            esperado = {linea.split("  ", 1)[1]: linea.split("  ", 1)[0] for linea in huellas.read_text(encoding="utf-8").splitlines() if "  " in linea}
            h = hashlib.sha256(ruta.read_bytes()).hexdigest()
            if esperado.get(ruta.name) != h:
                raise CommandError("La huella SHA-256 del respaldo NO coincide: el archivo está dañado o fue alterado.")
            self.stdout.write("Huella SHA-256: coincide.")
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "restaurada.sqlite3"
            with gzip.open(ruta, "rb") if ruta.suffix == ".gz" else open(ruta, "rb") as f, open(destino, "wb") as g:
                shutil.copyfileobj(f, g)
            con = sqlite3.connect(destino)
            try:
                integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
                if integridad != "ok":
                    raise CommandError(f"La base restaurada está dañada: {integridad}")
                cuentas = {tabla: con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] for tabla in ("nucleo_tarea", "nucleo_ocurrencia", "nucleo_eventoauditoria", "auth_user")}
            finally:
                con.close()
            entorno = {**os.environ, "PLANIFICACION_DB_PATH": str(destino)}
            r = subprocess.run([sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "verificar_bitacora"], env=entorno, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise CommandError("La bitácora del respaldo no es íntegra: " + (r.stderr or r.stdout).strip())
        self.stdout.write("Integridad de la base: ok.")
        self.stdout.write(f"Contenido: {cuentas['nucleo_tarea']} tareas, {cuentas['nucleo_ocurrencia']} ocurrencias, {cuentas['nucleo_eventoauditoria']} eventos de bitácora, {cuentas['auth_user']} usuarios.")
        self.stdout.write(r.stdout.strip())
        self.stdout.write(self.style.SUCCESS("RESTAURACIÓN VERIFICADA: guarda esta salida como evidencia."))
