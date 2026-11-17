"""Gracia de arranque: desde el inicio de uso, lo anterior no se considera atrasado durante unos días (por defecto 21). Ver servicios/gracia.py."""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from nucleo.servicios import gracia


class Command(BaseCommand):
    help = "Fija el inicio de uso de la app y los días de gracia (por ejemplo --inicio 2026-11-18 --dias 21). Con --quitar se apaga."

    def add_arguments(self, parser):
        parser.add_argument("--inicio", help="Primer día en que el equipo usa la app, AAAA-MM-DD.")
        parser.add_argument("--dias", type=int, default=21)
        parser.add_argument("--quitar", action="store_true")

    def handle(self, *args, inicio, dias, quitar, **opciones):
        if not inicio and not quitar:
            actual = gracia.inicio_de_operacion()
            self.stdout.write(f"Inicio de uso: {actual or 'sin gracia'}" + (f" · gracia hasta el {gracia.gracia_hasta():%d-%m-%Y}" if actual else ""))
            return
        try:
            fecha = None if quitar else datetime.strptime(inicio, "%Y-%m-%d").date()
            cuantas = gracia.configurar(fecha, dias)
        except ValueError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(self.style.SUCCESS("Gracia apagada." if quitar else f"Gracia fijada: {cuantas} tareas anteriores al {fecha:%d-%m-%Y} no cuentan como atrasadas hasta el {gracia.gracia_hasta():%d-%m-%Y}."))
