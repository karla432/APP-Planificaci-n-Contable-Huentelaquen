"""Feriados de Chile: propuesta desde una librería + confirmación anual de Karla (DEC-11).

Nunca se escriben fechas de feriados a mano en el código. Solo los feriados **confirmados** cuentan para el calendario.
"""
import holidays
from django.db import transaction
from django.utils import timezone

from nucleo.models import Anio, Feriado
from nucleo.servicios import auditoria
from nucleo.servicios.calendario import Calendario
from nucleo.servicios.errores import ErrorDeNegocio


def cargar_propuesta(anio: int) -> int:
    """Crea (sin confirmar) los feriados que la librería propone para el año. No toca los que ya existen."""
    propuesta = holidays.country_holidays("CL", years=anio, language="es")
    existentes = set(Feriado.objects.filter(fecha__year=anio).values_list("fecha", flat=True))
    nuevos = [Feriado(fecha=f, nombre=nombre, tipo="legal", origen="librería") for f, nombre in sorted(propuesta.items()) if f not in existentes]
    Feriado.objects.bulk_create(nuevos)
    return len(nuevos)


def calendario_confirmado() -> Calendario:
    return Calendario(Feriado.objects.filter(confirmado=True).values_list("fecha", flat=True))


@transaction.atomic
def agregar_o_editar(fecha, nombre: str, tipo: str, usuario) -> Feriado:
    """Alta o edición manual (feriados decretados a última hora, regionales). Queda sin confirmar."""
    antes = Feriado.objects.filter(fecha=fecha).values("nombre", "tipo", "confirmado").first()
    f, _ = Feriado.objects.update_or_create(fecha=fecha, defaults={"nombre": nombre, "tipo": tipo, "origen": "manual", "confirmado": False, "confirmado_por": None, "confirmado_en": None})
    auditoria.registrar("feriado.editado", usuario=usuario, entidad="Feriado", entidad_id=f.pk, antes=antes, despues={"fecha": str(fecha), "nombre": nombre, "tipo": tipo})
    return f


@transaction.atomic
def confirmar_anio(anio: int, usuario) -> int:
    n = Feriado.objects.filter(fecha__year=anio, confirmado=False).update(confirmado=True, confirmado_por=usuario, confirmado_en=timezone.now())
    auditoria.registrar("feriados.confirmados", usuario=usuario, entidad="Anio", entidad_id=anio, despues={"confirmados": n})
    return n


@transaction.atomic
def abrir_anio(anio: int, usuario) -> Anio:
    del_anio = Feriado.objects.filter(fecha__year=anio)
    if not del_anio.exists():
        raise ErrorDeNegocio(f"El año {anio} no tiene feriados cargados: cárgalos y confírmalos antes de abrirlo.")
    pendientes = del_anio.filter(confirmado=False).count()
    if pendientes:
        raise ErrorDeNegocio(f"Hay {pendientes} feriado(s) de {anio} sin confirmar: confirma la lista antes de abrir el año.")
    a, _ = Anio.objects.update_or_create(anio=anio, defaults={"estado": "abierto"})
    auditoria.registrar("anio.abierto", usuario=usuario, entidad="Anio", entidad_id=anio)
    return a
