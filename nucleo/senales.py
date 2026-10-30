"""Registro de sesiones en la bitácora y conteo de intentos fallidos."""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from nucleo import bloqueo_acceso
from nucleo.servicios import auditoria


def _origen(request) -> str:
    return (request.META.get("REMOTE_ADDR", "") if request is not None else "")[:100]


@receiver(user_logged_in)
def _ingreso(sender, request, user, **kwargs):
    bloqueo_acceso.limpiar(user.get_username())
    auditoria.registrar("sesion.iniciada", usuario=user, entidad="Usuario", entidad_id=user.pk, despues={"origen": _origen(request)})


@receiver(user_logged_out)
def _salida(sender, request, user, **kwargs):
    if user is not None:
        auditoria.registrar("sesion.cerrada", usuario=user, entidad="Usuario", entidad_id=user.pk)


@receiver(user_login_failed)
def _fallo(sender, credentials, request=None, **kwargs):
    nombre = credentials.get("username", "")
    if bloqueo_acceso.registrar_fallo(nombre, _origen(request)):
        usuario = get_user_model().objects.filter(username__iexact=nombre.strip()).first()
        if usuario is not None:  # solo las cuentas reales quedan en la bitácora; así no se revela cuáles existen
            auditoria.registrar("sesion.cuenta_bloqueada", usuario=usuario, entidad="Usuario", entidad_id=usuario.pk,
                                despues={"origen": _origen(request)})
