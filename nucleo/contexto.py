from django.conf import settings

from nucleo import permisos


def modo_prueba(request):
    return {"modo_prueba": settings.ACCESO_RAPIDO}


def menu(request):
    """Qué ve cada persona en el menú lateral (la decisión real de permiso se vuelve a validar en el servidor)."""
    usuario = getattr(request, "user", None)
    rol = permisos.rol_de(usuario) if usuario is not None and usuario.is_authenticated else None
    destino = getattr(getattr(request, "resolver_match", None), "url_name", "")
    return {
        "rol": rol, "url_actual": destino,
        "ve_mantenedor_tareas": rol in (permisos.GERENTE, permisos.JEFATURA),
        "ve_usuarios": rol in (permisos.GERENTE, permisos.ADMIN_SISTEMA),
    }
