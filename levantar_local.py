"""Prepara y levanta la web en el computador local (datos de EJEMPLO). Lo usa `.claude/launch.json` y sirve igual a mano:
    .venv/Scripts/python.exe levantar_local.py      (Windows)      ·      .venv/bin/python levantar_local.py   (Linux/Mac)
Con --preparar solo deja todo listo, sin abrir el servidor."""
import os
import subprocess
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
(base / ".entorno_desarrollo").touch()  # modo desarrollo local; no se versiona
env = {
    **os.environ,
    "PLANIFICACION_DB_PATH": str(base / "db_local.sqlite3"),
    "PLANIFICACION_HOY": os.environ.get("PLANIFICACION_HOY", "2026-11-09"),  # simula el lunes 09-11 (Día 6 del cierre de noviembre)
    "PLANIFICACION_SIN_CLAVE": "1",  # solo desarrollo local; en producción la app se niega a arrancar
}


def manage(*args):
    subprocess.run([sys.executable, str(base / "manage.py"), *args], cwd=base, env=env, check=True)


es_nueva = not (base / "db_local.sqlite3").exists()
manage("migrate", "-v0")  # siempre aplica las actualizaciones de la base (no borra nada)
if es_nueva:
    manage("datos_de_ejemplo", "--password", "Ejemplo-local-2026")
if "--preparar" not in sys.argv:
    manage("runserver", "8000")
