"""Documentos y evidencias adjuntos a los comentarios de una tarea (Karla, QA 01-11-2026).

- Solo se aceptan tipos conocidos (PDF, imágenes, Excel, Word, CSV, texto), hasta 10 MB, y se revisa que el contenido corresponda a la extensión.
- El archivo se guarda con un nombre aleatorio en `settings.EVIDENCIAS_ROOT` (fuera del repositorio) y se entrega solo por una vista con permiso.
- Lo puede ver quien ejecuta la tarea, quien la revisa (a quien se reporta), el Gerente y la Jefatura. Cada adjunto deja su huella (SHA-256) en la bitácora.
- Un adjunto nunca se ejecuta: se descarga o, si es PDF o imagen, se muestra en el navegador con cabeceras que impiden que haga nada más.
"""
import hashlib
import re
import uuid
from pathlib import Path

from django.conf import settings

from nucleo import permisos
from nucleo.models import Evidencia, Ocurrencia
from nucleo.servicios.errores import ErrorDeNegocio, PermisoDenegado

MAX_BYTES = 10 * 1024 * 1024
OOXML = b"PK\x03\x04"
OLE = b"\xd0\xcf\x11\xe0"
# extensión → (tipo de contenido, firma esperada al inicio del archivo, se puede mostrar en el navegador)
TIPOS = {
    "pdf": ("application/pdf", b"%PDF", True), "png": ("image/png", b"\x89PNG\r\n\x1a\n", True), "jpg": ("image/jpeg", b"\xff\xd8\xff", True), "jpeg": ("image/jpeg", b"\xff\xd8\xff", True),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", OOXML, False), "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", OOXML, False),
    "xls": ("application/vnd.ms-excel", OLE, False), "doc": ("application/msword", OLE, False), "csv": ("text/csv", None, False), "txt": ("text/plain", None, False),
}
TEXTO = ("Se aceptan PDF, imágenes (PNG, JPG), Excel, Word, CSV y texto, de hasta 10 MB.")


def nombre_seguro(nombre: str) -> str:
    nombre = re.sub(r"[\x00-\x1f\x7f]", "", (nombre or "").replace("\\", "/").split("/")[-1]).strip()
    return nombre[-150:] or "adjunto"


def validar(archivo) -> tuple[str, bytes]:
    """(extensión, contenido) si el archivo se puede guardar; si no, un mensaje claro."""
    nombre = nombre_seguro(getattr(archivo, "name", ""))
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if ext not in TIPOS:
        raise ErrorDeNegocio(f"Ese tipo de archivo no se puede adjuntar. {TEXTO}")
    contenido = archivo.read(MAX_BYTES + 1)
    if not contenido:
        raise ErrorDeNegocio("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ErrorDeNegocio("El archivo pesa más de 10 MB.")
    firma = TIPOS[ext][1]
    if firma is not None and not contenido.startswith(firma):
        raise ErrorDeNegocio(f"El contenido del archivo no corresponde a un .{ext}. Revisa que sea el documento correcto.")
    if firma is None:  # csv o txt: texto de verdad
        try:
            contenido.decode("utf-8")
        except UnicodeDecodeError:
            try:
                contenido.decode("latin-1")
            except UnicodeDecodeError:
                raise ErrorDeNegocio(f"El archivo .{ext} no es de texto.") from None
        if b"\x00" in contenido:
            raise ErrorDeNegocio(f"El archivo .{ext} no es de texto.")
    return ext, contenido


def guardar(o: Ocurrencia, usuario, archivo, evento=None) -> Evidencia:
    ext, contenido = validar(archivo)
    relativa = f"{o.pk}/{uuid.uuid4().hex}.{ext}"
    destino = Path(settings.EVIDENCIAS_ROOT) / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return Evidencia.objects.create(
        ocurrencia=o, evento=evento, ruta=relativa, nombre_original=nombre_seguro(archivo.name), extension=ext, tipo_contenido=TIPOS[ext][0], tamano=len(contenido),
        sha256=hashlib.sha256(contenido).hexdigest(), subido_por=usuario)


def puede_ver(usuario, o: Ocurrencia) -> bool:
    """Ejecuta la tarea, la revisa (a quien se reporta), o es Gerente o Jefatura."""
    rol = permisos.rol_de(usuario)
    if rol in (permisos.GERENTE, permisos.JEFATURA):
        return True
    c = permisos.colaborador_de(usuario)
    if rol == permisos.COLABORADOR and c is not None and o.colaborador_id == c.pk:
        return True
    return o.cargo_revisa_id is not None and o.cargo_revisa_id in permisos.cargos_vigentes_de(usuario)


def ruta_del_archivo(ev: Evidencia, usuario) -> Path:
    if not puede_ver(usuario, ev.ocurrencia):
        raise PermisoDenegado("No tienes acceso a los adjuntos de esta tarea.")
    base = Path(settings.EVIDENCIAS_ROOT).resolve()
    ruta = (base / ev.ruta).resolve()
    if base not in ruta.parents or not ruta.is_file():  # nunca salir de la carpeta de evidencias
        raise ErrorDeNegocio("El archivo ya no está disponible.")
    return ruta


def se_muestra_en_el_navegador(ev: Evidencia) -> bool:
    return TIPOS.get(ev.extension, ("", None, False))[2]
