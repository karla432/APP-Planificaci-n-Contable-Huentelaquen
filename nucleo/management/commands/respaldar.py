"""Copia consistente de la base (con la API de respaldo de SQLite, sin detener la app) y de los adjuntos. Deja un archivo de huellas SHA-256 para comprobarlos después.

El cifrado y la copia FUERA del servidor los hace el servidor (gpg/age y rsync o similar): ver docs/f1/08_guia_de_despliegue.md."""
import gzip
import hashlib
import os
import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from nucleo.servicios import auditoria


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Respalda la base y los adjuntos en una carpeta (por defecto la de PLANIFICACION_RESPALDOS)."

    def add_arguments(self, parser):
        parser.add_argument("--destino", default=os.environ.get("PLANIFICACION_RESPALDOS", ""), help="Carpeta donde dejar los respaldos (fuera de la carpeta del código).")
        parser.add_argument("--conservar", type=int, default=30, help="Cuántos respaldos mantener (los más antiguos se borran). Por defecto 30.")

    def handle(self, *args, destino, conservar, **opciones):
        if not destino:
            raise CommandError("Indica la carpeta con --destino o con la variable PLANIFICACION_RESPALDOS.")
        carpeta = Path(destino)
        carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
        origen = Path(connection.settings_dict["NAME"])
        if not origen.exists():
            raise CommandError(f"No encuentro la base en {origen}.")
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = carpeta / f"respaldo_{sello}.sqlite3"
        con_origen, con_destino = sqlite3.connect(origen), sqlite3.connect(base)
        try:
            con_origen.backup(con_destino)
        finally:
            con_destino.close()
            con_origen.close()
        comprimido = Path(str(base) + ".gz")
        with open(base, "rb") as f, gzip.open(comprimido, "wb") as g:
            shutil.copyfileobj(f, g)
        base.unlink()
        archivos = [comprimido]
        evidencias = Path(settings.EVIDENCIAS_ROOT)
        if evidencias.exists() and any(evidencias.iterdir()):
            tar = carpeta / f"adjuntos_{sello}.tar.gz"
            with tarfile.open(tar, "w:gz") as t:
                t.add(evidencias, arcname="evidencias")
            archivos.append(tar)
        huellas = carpeta / f"respaldo_{sello}.sha256"
        huellas.write_text("".join(f"{_sha256(a)}  {a.name}\n" for a in archivos), encoding="utf-8")
        for a in archivos + [huellas]:
            os.chmod(a, 0o600)
        antiguos = sorted(carpeta.glob("respaldo_*.sqlite3.gz"))[:-conservar] if conservar > 0 else []
        for viejo in antiguos:
            clave = viejo.name.removeprefix("respaldo_").removesuffix(".sqlite3.gz")
            for p in carpeta.glob(f"*_{clave}.*"):
                p.unlink()
        auditoria.registrar("respaldo.hecho", usuario=None, entidad="Base", despues={"archivos": [a.name for a in archivos]})
        self.stdout.write(self.style.SUCCESS("Respaldo listo: " + ", ".join(str(a) for a in archivos)))
