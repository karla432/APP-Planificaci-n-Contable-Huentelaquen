"""Roles de la aplicación (docs/f1/03_kpi_roles_sod.md). Se guardan como grupos de Django.

Ser superusuario o staff de Django NO otorga ningún permiso de la aplicación (mismo criterio del Arqueo).
Todo se valida en el servidor; la interfaz solo esconde botones.
"""
from django.utils import timezone

from nucleo.models import Asignacion, Colaborador

ADMIN_SISTEMA, GERENTE, JEFATURA, COLABORADOR, LECTURA = "ADMIN_SISTEMA", "GERENTE", "JEFATURA", "COLABORADOR", "LECTURA"
ROLES = (ADMIN_SISTEMA, GERENTE, JEFATURA, COLABORADOR, LECTURA)  # de mayor a menor precedencia
QUE_MARCAN = (COLABORADOR, JEFATURA, GERENTE)  # roles que ejecutan tareas propias


def rol_de(usuario) -> str | None:
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None
    grupos = set(usuario.groups.values_list("name", flat=True))
    return next((r for r in ROLES if r in grupos), None)


def colaborador_de(usuario) -> Colaborador | None:
    if usuario is None:
        return None
    return Colaborador.objects.filter(usuario=usuario, activo=True).first()


def cargos_vigentes_de(usuario, fecha=None) -> set[int]:
    fecha = fecha or timezone.localdate()
    c = colaborador_de(usuario)
    if c is None:
        return set()
    return set(
        Asignacion.objects.filter(colaborador=c, desde__lte=fecha).exclude(hasta__lt=fecha).values_list("cargo_id", flat=True)
    )
