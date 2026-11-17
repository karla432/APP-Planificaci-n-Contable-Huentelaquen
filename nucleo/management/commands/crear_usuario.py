"""Crea una cuenta real en el servidor (la hace el administrador del sistema, Eugenio). La clave se pide por teclado: nunca va en el comando ni en un archivo."""
import getpass
import sys
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nucleo import permisos
from nucleo.models import Asignacion, Cargo, Colaborador
from nucleo.servicios import auditoria, segundo_factor


class Command(BaseCommand):
    help = "Crea un usuario con su rol y su cargo. Para el Gerente AyF y el administrador también crea el segundo factor y muestra su clave UNA vez."

    def add_arguments(self, parser):
        parser.add_argument("usuario")
        parser.add_argument("--rol", required=True, choices=[r for r in permisos.ROLES])
        parser.add_argument("--nombre", required=True, help="Nombre de la persona, como quiere verlo en la app.")
        parser.add_argument("--cargo", help="Cargo que ejerce (por ejemplo «Jefa de Control»). Obligatorio salvo para el administrador y los perfiles de solo lectura.")
        parser.add_argument("--correo", default="")
        parser.add_argument("--desde", help="Desde cuándo ejerce el cargo, AAAA-MM-DD (por defecto hoy). Para abrir un mes que ya empezó (por ejemplo noviembre desde el 01-11) usa una fecha anterior, por ejemplo 2026-01-01.")

    def _clave(self) -> str:
        if sys.stdin.isatty():
            a, b = getpass.getpass("Clave (mínimo 12 caracteres): "), getpass.getpass("Repite la clave: ")
        else:  # para pruebas y scripts: dos líneas por la entrada estándar
            a, b = sys.stdin.readline().rstrip("\n"), sys.stdin.readline().rstrip("\n")
        if a != b:
            raise CommandError("Las dos claves no coinciden.")
        return a

    @transaction.atomic
    def handle(self, *args, usuario, rol, nombre, cargo, correo, desde=None, **opciones):
        usuarios = get_user_model()
        try:
            fecha_desde = date.fromisoformat(desde) if desde else date.today()
        except ValueError:
            raise CommandError(f"--desde debe ser una fecha AAAA-MM-DD (recibí «{desde}»).") from None
        if usuarios.objects.filter(username=usuario).exists():
            raise CommandError(f"El usuario «{usuario}» ya existe. Para cambiar su clave usa `recuperar_acceso`.")
        c = None
        if rol not in (permisos.ADMIN_SISTEMA, permisos.LECTURA) or cargo:
            c = Cargo.objects.filter(nombre=cargo).first() if cargo else None
            if c is None:
                raise CommandError(f"Indica un cargo que exista con --cargo (no encontré «{cargo or ''}»).")
        clave = self._clave()
        try:
            validate_password(clave, usuarios(username=usuario))
        except ValidationError as e:
            raise CommandError("La clave no sirve: " + " ".join(e.messages)) from None
        u = usuarios.objects.create_user(usuario, email=correo, password=clave)
        u.groups.add(Group.objects.get_or_create(name=rol)[0])
        if c is not None:
            colaborador = Colaborador.objects.create(usuario=u, nombre=nombre, correo=correo)
            Asignacion.objects.create(cargo=c, colaborador=colaborador, desde=fecha_desde)
        auditoria.registrar("usuario.creado_por_consola", usuario=None, entidad="Usuario", entidad_id=u.pk, despues={"usuario": usuario, "rol": rol, "cargo": cargo or ""})
        self.stdout.write(self.style.SUCCESS(f"Usuario «{usuario}» creado con el rol {rol}."))
        if rol in segundo_factor.ROLES_QUE_LO_EXIGEN:
            sf = segundo_factor.crear(u)
            self.stdout.write("\nSegundo factor OBLIGATORIO. Entrégale a la persona (una sola vez, en privado) esta clave para su aplicación de códigos:")
            self.stdout.write(f"  Clave: {segundo_factor.clave_legible(sf)}\n  Enlace: {segundo_factor.uri(sf)}")
            self.stdout.write("En su primer ingreso escribirá el código de 6 números y quedará confirmado.")
