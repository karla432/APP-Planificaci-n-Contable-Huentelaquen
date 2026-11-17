"""Recupera el acceso de una cuenta: pone una clave nueva, quita el bloqueo por intentos y, si se pide, reinicia el segundo factor. Exige acceso a la consola del servidor."""
import getpass
import sys

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from nucleo import bloqueo_acceso
from nucleo.servicios import auditoria, segundo_factor


class Command(BaseCommand):
    help = "Clave nueva y desbloqueo de una cuenta (la clave se pide por teclado)."

    def add_arguments(self, parser):
        parser.add_argument("usuario")
        parser.add_argument("--reiniciar-2fa", action="store_true", help="La persona cambió de teléfono: se borra su segundo factor y vuelve a darlo de alta.")
        parser.add_argument("--solo-desbloquear", action="store_true", help="No cambia la clave; solo quita el bloqueo por intentos fallidos.")

    def handle(self, *args, usuario, reiniciar_2fa, solo_desbloquear, **opciones):
        u = get_user_model().objects.filter(username=usuario).first()
        if u is None:
            raise CommandError(f"No existe el usuario «{usuario}».")
        if not solo_desbloquear:
            if sys.stdin.isatty():
                a, b = getpass.getpass("Clave nueva (mínimo 12 caracteres): "), getpass.getpass("Repite la clave: ")
            else:
                a, b = sys.stdin.readline().rstrip("\n"), sys.stdin.readline().rstrip("\n")
            if a != b:
                raise CommandError("Las dos claves no coinciden.")
            try:
                validate_password(a, u)
            except ValidationError as e:
                raise CommandError("La clave no sirve: " + " ".join(e.messages)) from None
            u.set_password(a)
            u.save(update_fields=["password"])
        bloqueo_acceso.limpiar(usuario)
        bloqueo_acceso.limpiar(f"2fa:{usuario}")
        if reiniciar_2fa:
            segundo_factor.reiniciar(u)
        auditoria.registrar("acceso.recuperado", usuario=None, entidad="Usuario", entidad_id=u.pk, despues={"usuario": usuario, "clave_nueva": not solo_desbloquear, "reinicio_2fa": reiniciar_2fa})
        self.stdout.write(self.style.SUCCESS(f"Acceso de «{usuario}» recuperado" + (" y segundo factor reiniciado." if reiniciar_2fa else ".")))
