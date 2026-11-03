"""Días hábiles y fechas de entrega del cierre (DH08, DH09 y DH10). Lógica pura: no toca la base de datos.

Día hábil = lunes a viernes que no sea feriado. Las fechas son fechas de negocio (America/Santiago), sin hora.
Solo deben pasarse feriados CONFIRMADOS (ver `nucleo.models.Feriado`).
"""
import calendar
from datetime import date, timedelta
from typing import Iterable


# Jornada por día de la semana (0 = lunes). Karla (01-11-2026): lunes a jueves 9 h y viernes 5 h (41 h a la semana). Antes el viernes era de 4 h (DEC-14).
JORNADA_HORAS = {0: 9, 1: 9, 2: 9, 3: 9, 4: 5}


class Calendario:
    def __init__(self, feriados: Iterable[date]):
        self._feriados = frozenset(feriados)

    def es_feriado(self, f: date) -> bool:
        return f in self._feriados

    def es_habil(self, f: date) -> bool:
        return f.weekday() <= 4 and f not in self._feriados

    def siguiente_habil(self, f: date) -> date:
        while not self.es_habil(f):
            f += timedelta(days=1)
        return f

    def anterior_habil(self, f: date) -> date:
        while not self.es_habil(f):
            f -= timedelta(days=1)
        return f

    def dias_habiles_del_mes(self, anio: int, mes: int) -> list[date]:
        ultimo = calendar.monthrange(anio, mes)[1]
        return [d for d in (date(anio, mes, n) for n in range(1, ultimo + 1)) if self.es_habil(d)]

    def dia_habil_n(self, anio: int, mes: int, n: int) -> date:
        """El n-ésimo día hábil del mes (n = 1 es el primero). n = 0 (DH00) es el último día hábil del mes anterior."""
        if n == 0:
            return self.anterior_habil(date(anio, mes, 1) - timedelta(days=1))
        habiles = self.dias_habiles_del_mes(anio, mes)
        if not 1 <= n <= len(habiles):
            raise ValueError(f"El mes {mes:02d}-{anio} no tiene un día hábil número {n}.")
        return habiles[n - 1]

    def sumar_dias_habiles(self, f: date, n: int) -> date:
        """La fecha que queda n días hábiles después de `f` (n = 0 devuelve `f`)."""
        while n > 0:
            f += timedelta(days=1)
            if self.es_habil(f):
                n -= 1
        return f

    def dias_habiles_entre(self, desde: date, hasta: date) -> int:
        """Días hábiles después de `desde` y hasta `hasta` inclusive (desde no cuenta)."""
        cuenta, f = 0, desde
        while f < hasta:
            f += timedelta(days=1)
            if self.es_habil(f):
                cuenta += 1
        return cuenta


def hitos_de_entrega(cal: Calendario, anio: int, mes: int) -> dict[int, date]:
    """Las tres fechas del cierre del mes `mes`: son **días hábiles** DH08, DH09 y DH10 (Karla, 03-11-2026, según la Planificación 2.0).

    - DH08: análisis hecho y reportes listos, **en la tarde**;
    - DH09: se entrega al Gerente General (revisión);
    - DH10: se entrega al Directorio.

    Reemplaza la regla del 01-11-2026 (días 8, 9 y 10 del mes).
    """
    return {8: cal.dia_habil_n(anio, mes, 8), 9: cal.dia_habil_n(anio, mes, 9), 10: cal.dia_habil_n(anio, mes, 10)}


def ventana_del_cierre(cal: Calendario, anio: int, mes: int) -> tuple[date, date]:
    """«Semana del cierre» (las dos semanas de cierre): del primer día hábil (DH01) al día de entrega al Directorio (DH10)."""
    return cal.dia_habil_n(anio, mes, 1), cal.dia_habil_n(anio, mes, 10)
