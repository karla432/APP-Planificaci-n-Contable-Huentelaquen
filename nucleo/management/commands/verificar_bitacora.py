"""Revisa que la bitácora no haya sido alterada (cada evento encadena el sello del anterior). Termina con error si encuentra algo."""
from django.core.management.base import BaseCommand, CommandError

from nucleo.models import EventoAuditoria
from nucleo.servicios import auditoria


class Command(BaseCommand):
    help = "Verifica la cadena de sellos de la bitácora. Sale con error si hay eventos alterados."

    def handle(self, *args, **opciones):
        total = EventoAuditoria.objects.count()
        malos = auditoria.verificar_cadena()
        if malos:
            raise CommandError(f"Bitácora ALTERADA: {len(malos)} de {total} eventos no calzan (ids {malos[:20]}{'…' if len(malos) > 20 else ''}).")
        self.stdout.write(self.style.SUCCESS(f"Bitácora íntegra: {total} eventos verificados."))
