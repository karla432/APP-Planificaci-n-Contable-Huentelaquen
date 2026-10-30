"""La fecha de hoy en la zona de negocio (America/Santiago). Un solo punto para poder fijarla en las pruebas.

Solo en desarrollo, `PLANIFICACION_HOY=aaaa-mm-dd` fija la fecha (para mostrar el cierre de diciembre antes de que llegue).
En producción la variable se ignora."""
import os
from datetime import date

from django.conf import settings
from django.utils import timezone


def hoy() -> date:
    fijada = os.environ.get("PLANIFICACION_HOY", "").strip()
    if fijada and not settings.PRODUCCION:
        return date.fromisoformat(fijada)
    return timezone.localdate()
