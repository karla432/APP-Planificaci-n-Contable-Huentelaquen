"""Ejemplo de la estructura de tres niveles (solo desarrollo, solo sobre una base sin procesos): catálogo base de 11 procesos y el proceso
Ventas y sala de venta (VEN) con 3 tareas y 8 subtareas. Sirve para ver cómo funciona la codificación OO-PPP.TT.SSS en una instalación nueva."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from nucleo.models import Cargo, Proceso, Tarea
from nucleo.servicios import estructura, importador

VENTAS = [
    ("Registro de ventas", ["Ingresar arqueo de caja", "Registrar diferencias de caja", "Validar documentos de venta"]),
    ("Cierre de caja", ["Revisar medios de pago", "Cuadrar caja", "Generar informe de cierre"]),
    ("Registro contable", ["Generar asiento contable", "Validar cuentas contables"]),
]


class Command(BaseCommand):
    help = "Carga el catálogo base y el ejemplo de Ventas (VEN). Solo desarrollo y solo si no hay procesos."

    def handle(self, *args, **opciones):
        if settings.PRODUCCION:
            raise CommandError("Este comando es solo de desarrollo: se niega a correr en producción.")
        if Proceso.objects.exists():
            raise CommandError("La base ya tiene procesos: este ejemplo es para una instalación nueva (sin procesos).")
        estructura.cargar_catalogo_base(None, validar_permiso=False)
        ventas = Proceso.objects.get(sigla="VEN")
        responsable, _ = Cargo.objects.get_or_create(nombre="Contador Senior", defaults={"orden": 3})
        orden = 0
        for tarea, subtareas in VENTAS:
            for subtarea in subtareas:
                orden += 1
                Tarea.objects.create(
                    clave_estable=importador._clave(ventas.nombre, tarea, subtarea), proceso=ventas, tarea_principal=tarea, subtarea=subtarea, cargo_ejecuta=responsable,
                    regla_tipo="CIERRE_DIA_HABIL", regla_n=2, secuencia=orden, minutos_estimados=30, ejecuciones_mes=1)
        self.stdout.write(self.style.SUCCESS(f"Ejemplo listo: {Proceso.objects.count()} procesos; {ventas.codigo} con {ventas.tareas_principales.count()} tareas y {ventas.tareas.count()} subtareas."))
