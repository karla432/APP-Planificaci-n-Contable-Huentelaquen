"""Datos de EJEMPLO para mostrar la aplicación (solo desarrollo). No usa personas reales y se niega a correr en producción."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from nucleo.models import Asignacion, Cargo, Colaborador, Ocurrencia
from nucleo.servicios import feriados, importador, periodos

EXCEL = Path(settings.BASE_DIR) / "docs" / "datos" / "Planificacion_Mensual_Huentelauquen_Revisada.xlsx"
PERSONAS = [  # usuario, nombre de ejemplo, cargo, rol
    ("gerente", "Gerente AyF (ejemplo)", "Gerente AyF", "GERENTE"),
    ("jefa", "Jefa de Control (ejemplo)", "Jefa de Control", "JEFATURA"),
    ("contadora", "Contador Senior (ejemplo)", "Contador Senior", "COLABORADOR"),
    ("asistente", "Asistente Contable (ejemplo)", "Asistente Contable", "COLABORADOR"),
]
SCL = ZoneInfo("America/Santiago")


class Command(BaseCommand):
    help = "Carga el Excel, 4 usuarios de ejemplo y abre diciembre de 2026 con avance simulado. Solo desarrollo."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Contraseña de los 4 usuarios de ejemplo (mínimo 12 caracteres).")

    def handle(self, *args, password, **opciones):
        if settings.PRODUCCION:
            raise CommandError("Este comando es solo de desarrollo: se niega a correr en producción.")
        importador.aplicar(importador.previsualizar(EXCEL), usuario=None)
        for usuario, nombre, cargo, rol in PERSONAS:
            u = get_user_model().objects.create_user(usuario, password=password)
            u.groups.add(Group.objects.get(name=rol))
            c = Colaborador.objects.create(usuario=u, nombre=nombre)
            Asignacion.objects.create(cargo=Cargo.objects.get(nombre=cargo), colaborador=c, desde=date(2026, 1, 1))
        feriados.cargar_propuesta(2026)
        feriados.confirmar_anio(2026, None)
        feriados.abrir_anio(2026, None)
        res = periodos.abrir_mes(2026, 12, usuario=None, inicio_medicion=date(2026, 12, 1))
        self._simular_avance()
        self.stdout.write(self.style.SUCCESS(f"Ejemplo listo: {res.creadas} ocurrencias en 12-2026, {len(res.avisos)} avisos. Usuarios: gerente, jefa, contadora, asistente."))

    def _simular_avance(self):
        """Avance de EJEMPLO hasta el 03-12-2026: casi todo a tiempo, algo tarde y algo sin hacer."""
        for i, o in enumerate(Ocurrencia.objects.filter(periodo__mes=12, colaborador__isnull=False, fecha_limite__lte=date(2026, 12, 3)).order_by("fecha_limite", "id")):
            if i % 9 == 8:
                continue  # sin hacer: queda atrasada
            dia = o.fecha_limite if i % 7 else date(2026, 12, 3)
            hecha = datetime(dia.year, dia.month, dia.day, 16, 0, tzinfo=SCL)
            if dia < o.fecha_limite or (i % 7 == 0 and dia > o.fecha_limite):
                hecha = datetime(2026, 12, 4, 10, 0, tzinfo=SCL)  # hecha tarde
            o.estado, o.primera_hecha_en, o.hecha_en = Ocurrencia.HECHA, hecha, hecha
            o.hecha_por = o.colaborador.usuario
            if i % 11 == 4 and o.cargo_revisa_id:  # ya revisada por quien corresponde
                o.estado, o.revisada_en, o.primera_revision_en = Ocurrencia.REVISADA, hecha, hecha
            o.save()
        # Un par de tareas bloqueadas, para mostrar el estado y su motivo (ejemplo, no son datos reales).
        for o in Ocurrencia.objects.filter(periodo__mes=12, estado=Ocurrencia.PENDIENTE, colaborador__isnull=False, fecha_limite__lte=date(2026, 12, 3)).order_by("id")[:2]:
            o.estado, o.motivo_bloqueo = Ocurrencia.BLOQUEADA, "Falta la información del proveedor (ejemplo)."
            o.save()
