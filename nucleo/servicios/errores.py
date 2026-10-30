class ErrorDeNegocio(Exception):
    """Una regla del negocio impide la operación. El mensaje se muestra tal cual a la persona."""


class PermisoDenegado(ErrorDeNegocio):
    """La persona no tiene permiso para esta acción (validado siempre en el servidor)."""
