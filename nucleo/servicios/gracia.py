"""Gracia de arranque (Karla, 17-11-2026): la medición empieza el 01-11, pero el equipo recién empieza a registrar lo que hizo y, **durante 3 semanas**, lo anterior
al inicio de uso no se considera atrasado.

- `inicio_operacion` (AAAAMMDD) es el primer día en que el equipo usa la app; `dias_de_gracia` (por defecto 21) cuánto dura la gracia. 0 en `inicio_operacion` = sin gracia.
- Las tareas con fecha límite anterior al inicio de uso **conservan su fecha del plan**, pero solo cuentan como atrasadas desde el fin de la gracia (`vence_el`).
  Si se registran dentro de la gracia, cuentan como hechas a tiempo. Pasada la gracia, las que sigan pendientes se ven atrasadas como cualquier otra.
"""
from datetime import date, timedelta

from django.db.models import F

from nucleo.models import Ocurrencia
from nucleo.servicios import auditoria, parametros


def inicio_de_operacion() -> date | None:
    n = parametros.entero("inicio_operacion")
    return date(n // 10000, n // 100 % 100, n % 100) if n else None


def gracia_hasta() -> date | None:
    inicio = inicio_de_operacion()
    return inicio + timedelta(days=parametros.entero("dias_de_gracia")) if inicio else None


def vence_el_para(fecha_limite: date) -> date:
    """Desde cuándo cuenta como atrasada una tarea con esa fecha límite."""
    inicio, hasta = inicio_de_operacion(), gracia_hasta()
    return hasta if inicio and fecha_limite < inicio else fecha_limite


def en_gracia(hoy: date) -> bool:
    hasta = gracia_hasta()
    return bool(hasta and hoy <= hasta)


def configurar(inicio: date | None, dias: int = 21, usuario=None) -> int:
    """Fija la gracia y la aplica a las tareas que ya existen. Devuelve cuántas quedan con gracia."""
    if dias < 0 or dias > 90:
        raise ValueError("Los días de gracia deben estar entre 0 y 90.")
    parametros.guardar("inicio_operacion", str(inicio.year * 10000 + inicio.month * 100 + inicio.day) if inicio else "0", usuario, confirmado=True)
    parametros.guardar("dias_de_gracia", str(dias), usuario, confirmado=True)
    Ocurrencia.objects.exclude(vence_el=F("fecha_limite")).update(vence_el=F("fecha_limite"))
    cuantas = 0
    if inicio:
        cuantas = Ocurrencia.objects.filter(fecha_limite__lt=inicio).update(vence_el=gracia_hasta())
    auditoria.registrar("gracia.configurada", usuario=usuario, entidad="Parametro", despues={"inicio_operacion": str(inicio) if inicio else None, "dias_de_gracia": dias, "tareas": cuantas})
    return cuantas
