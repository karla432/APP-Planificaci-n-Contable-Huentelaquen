"""Fábricas de datos de prueba (sin personas reales)."""
from datetime import date

from nucleo.models import Anio, Asignacion, Cargo, Colaborador, Feriado, Proceso, Tarea


def cargo(nombre, externo=False):
    return Cargo.objects.get_or_create(nombre=nombre, defaults={"es_externo": externo})[0]


def persona(nombre, cargo_, desde=date(2026, 1, 1), hasta=None):
    c = Colaborador.objects.get_or_create(nombre=nombre)[0]
    Asignacion.objects.create(cargo=cargo_, colaborador=c, desde=desde, hasta=hasta)
    return c


def tarea(codigo, ejecuta, regla_tipo, revisa=None, **regla):
    proceso = Proceso.objects.get_or_create(nombre="Proceso de prueba")[0]
    campos = {f"regla_{k}": v for k, v in regla.items()}
    return Tarea.objects.create(
        codigo=codigo, clave_estable=codigo.ljust(64, "x"), proceso=proceso, tarea_principal="Tarea " + codigo,
        subtarea="Subtarea " + codigo, cargo_ejecuta=ejecuta, cargo_revisa=revisa, regla_tipo=regla_tipo, **campos,
    )


def anio_abierto(anio=2026, feriados=(date(2026, 12, 8), date(2026, 12, 25))):
    a = Anio.objects.create(anio=anio, estado="abierto")
    for f in feriados:
        Feriado.objects.create(fecha=f, nombre="Feriado de prueba", confirmado=True)
    return a
