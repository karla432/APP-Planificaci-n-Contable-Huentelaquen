"""Carga el plan (el Excel «Planificación vigente» o la Planificación 2.0) y, si se pide, abre el mes con su fecha de comienzo. Lo ejecuta Eugenio con el archivo que le entregue Karla.
El archivo NO va en el repositorio: contiene datos reales de la empresa."""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from nucleo.servicios import gracia, importador, periodos
from nucleo.servicios.errores import ErrorDeNegocio


class Command(BaseCommand):
    help = "Carga el plan desde un Excel. Sin --aplicar solo muestra qué cambiaría."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--aplicar", action="store_true", help="Guarda los cambios (sin esto solo se muestra la vista previa).")
        parser.add_argument("--confirmo-desactivar", action="store_true", help="Acepta desactivar las tareas que el archivo ya no trae.")
        parser.add_argument("--abrir-mes", help="Mes a abrir después de cargar, AAAA-MM (por ejemplo 2026-11).")
        parser.add_argument("--desde", help="Fecha de comienzo de la medición, AAAA-MM-DD (por ejemplo 2026-11-01).")
        parser.add_argument("--crear-cargos", action="store_true", help="En una base nueva todavía no existen los cargos del equipo: con esta opción se crean los que trae el Excel. Revisa antes la lista (que sean cargos, no nombres de personas).")
        parser.add_argument("--inicio-uso", help="Primer día en que el equipo usa la app, AAAA-MM-DD. Lo anterior no cuenta como atrasado durante la gracia.")
        parser.add_argument("--dias-de-gracia", type=int, default=21)
        parser.add_argument("--cargo", action="append", default=[], metavar="TEXTO=CARGO", help="Si el Excel trae otro texto donde va un cargo (por ejemplo el nombre de una persona), dice a qué cargo corresponde. Se puede repetir.")

    def handle(self, *args, archivo, aplicar, confirmo_desactivar, abrir_mes, desde, inicio_uso, dias_de_gracia, cargo, crear_cargos, **opciones):
        equivalencias = {}
        for par in cargo:
            if "=" not in par:
                raise CommandError(f"--cargo debe ser «TEXTO=CARGO» (recibí «{par}»).")
            texto, destino = par.split("=", 1)
            equivalencias[texto.strip()] = destino.strip()
        try:
            vp = importador.previsualizar(archivo, incluir_dia_9=False, renombrar_cargos=equivalencias)
        except Exception as e:  # el archivo no es un Excel del plan
            raise CommandError(f"No pude leer el archivo: {e}") from e
        self.stdout.write(f"Filas: {vp.total_filas} · nuevas: {len(vp.altas)} · modificadas: {len(vp.cambios)} · a desactivar: {len(vp.bajas)} · por revisar: {len(vp.requieren_revision)}")
        if vp.cargos_nuevos and not crear_cargos:
            raise CommandError(f"Hay cargos que no existen en la app: {', '.join(vp.cargos_nuevos)}. Si son los cargos reales del equipo (base nueva), repite con --crear-cargos; "
                               "si alguno es el nombre de una persona, corrígelo en el Excel (el responsable es un CARGO) o tradúcelo con --cargo \"TEXTO=CARGO\".")
        if vp.cargos_nuevos:
            self.stdout.write(f"Se crearán {len(vp.cargos_nuevos)} cargos: {', '.join(vp.cargos_nuevos)}.")
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
        if inicio_uso:
            try:
                cuantas = gracia.configurar(datetime.strptime(inicio_uso, "%Y-%m-%d").date(), dias_de_gracia)
            except ValueError as e:
                raise CommandError(f"Inicio de uso inválido: {e}") from e
            self.stdout.write(self.style.SUCCESS(f"Gracia: lo anterior al {inicio_uso} no cuenta como atrasado hasta el {gracia.gracia_hasta():%d-%m-%Y} ({cuantas} tareas ya generadas)."))
        if abrir_mes:
            try:
                anio, mes = (int(x) for x in abrir_mes.split("-"))
                inicio = datetime.strptime(desde, "%Y-%m-%d").date() if desde else None
                r = periodos.abrir_mes(anio, mes, usuario=None, inicio_medicion=inicio)
            except (ValueError, ErrorDeNegocio) as e:
                raise CommandError(f"No pude abrir el mes: {e}") from e
            self.stdout.write(self.style.SUCCESS(f"Mes {abrir_mes} abierto: {r.creadas} tareas generadas, {len(r.avisos)} avisos" + (f", medición desde {inicio:%d-%m-%Y}." if desde else ".")))
