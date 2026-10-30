"""Qué entorno usa la aplicación cuando nadie lo indica (Karla, 2026-09-26: «por defecto producción»).

* `ARQUEO_ENTORNO` manda si está definida.
* Si no, es PRODUCCIÓN: la opción segura para cualquier servidor.
* La única excepción es un equipo de desarrollo que tenga el archivo local `.entorno_desarrollo` en la carpeta del
  proyecto (no se versiona, así que jamás llega a un servidor por el repositorio)."""
from pathlib import Path

MARCA_LOCAL = ".entorno_desarrollo"


def resolver_entorno(variable: str | None, base_dir: Path) -> str:
    if variable is not None and variable.strip():
        return variable.strip().lower()
    return "desarrollo" if (Path(base_dir) / MARCA_LOCAL).exists() else "produccion"


def acceso_rapido_permitido(variable: str | None, produccion: bool) -> bool:
    """«Entrar sin clave» es solo para probar en un computador local (Karla, 2026-10-30).

    Se enciende únicamente con PLANIFICACION_SIN_CLAVE=1 y **fuera de producción**. Si alguien lo pide en producción, la
    aplicación se niega a arrancar (falla cerrada) en vez de ignorarlo en silencio."""
    if (variable or "").strip() != "1":
        return False
    if produccion:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("PLANIFICACION_SIN_CLAVE no se permite en producción: el acceso sin clave solo existe en desarrollo.")
    return True
