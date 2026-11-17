"""Carga el plan (el Excel «Planificación vigente» o la Planificación 2.0) y, si se pide, abre el mes con su fecha de comienzo. Lo ejecuta Eugenio con el archivo que le entregue Karla.
El archivo NO va en el repositorio: contiene datos reales de la empresa."""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from nucleo.servicios import importador, periodos
from nucleo.servicios.errores import ErrorDeNegocio


class Command(BaseCommand):
    help = "Carga el plan desde un Excel. Sin --aplicar solo muestra qué cambiaría."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--aplicar", action="store_true", help="Guarda los cambios (sin esto solo se muestra la vista previa).")
        parser.add_argument("--confirmo-desactivar", action="store_true", help="Acepta desactivar las tareas que el archivo ya no trae.")
        parser.add_argument("--abrir-mes", help="Mes a abrir después de cargar, AAAA-MM (por ejemplo 2026-11).")
        parser.add_argument("--desde", help="Fecha de comienzo de la medición, AAAA-MM-DD (por ejemplo 2026-11-01).")

    def handle(self, *args, archivo, aplicar, confirmo_desactivar, abrir_mes, desde, **opciones):
        try:
            vp = importador.previsualizar(archivo, incluir_dia_9=False)
        except Exception as e:  # el archivo no es un Excel del plan
            raise CommandError(f"No pude leer el archivo: {e}") from e
        self.stdout.write(f"Filas: {vp.total_filas} · nuevas: {len(vp.altas)} · modificadas: {len(vp.cambios)} · a desactivar: {len(vp.bajas)} · por revisar: {len(vp.requieren_revision)}")
        if vp.cargos_nuevos:
            raise CommandError(f"Hay cargos que no existen en la app: {', '.join(vp.cargos_nuevos)}. Corrígelos en el Excel (el responsable es un CARGO) o créalos primero.")
        for t in vp.bajas:
            self.stdout.write(f"  se desactivaría: {t.codigo} {t.subtarea[:70]}")
        for f, motivo in vp.requieren_revision:
            self.stdout.write(f"  por revisar: {f.subtarea[:60]} — {motivo}")
        if not aplicar:
            self.stdout.write("Vista previa solamente. Repite con --aplicar para guardar.")
            return
        if vp.bajas and not confirmo_desactivar:
            raise CommandError("El archivo desactivaría tareas: revisa la lista y repite con --confirmo-desactivar.")
        resumen = importador.aplicar(vp, usuario=None, detalle={"archivo": str(archivo)[-80:], "por": "consola"})
        self.stdout.write(self.style.SUCCESS(f"Plan cargado: {resumen}"))
        if abrir_mes:
            try:
                anio, mes = (int(x) for x in abrir_mes.split("-"))
                inicio = datetime.strptime(desde, "%Y-%m-%d").date() if desde else None
                r = periodos.abrir_mes(anio, mes, usuario=None, inicio_medicion=inicio)
            except (ValueError, ErrorDeNegocio) as e:
                raise CommandError(f"No pude abrir el mes: {e}") from e
            self.stdout.write(self.style.SUCCESS(f"Mes {abrir_mes} abierto: {r.creadas} tareas generadas, {len(r.avisos)} avisos" + (f", medición desde {inicio:%d-%m-%Y}." if desde else ".")))
