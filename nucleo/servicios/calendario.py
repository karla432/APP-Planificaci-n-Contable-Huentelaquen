"""Días hábiles y fechas de entrega del cierre (días 8, 9 y 10). Lógica pura: no toca la base de datos.

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
        """El n-ésimo día hábil del mes (n = 1 es el primero)."""
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


def _no_antes_de(cal: Calendario, base: date, anterior: date, min_dias_habiles_entre: int) -> date:
    """El día hábil siguiente a `base` (o `base` si ya es hábil), pero al menos `min_dias_habiles_entre` días hábiles después de `anterior`."""
    return max(cal.siguiente_habil(base), cal.sumar_dias_habiles(anterior, min_dias_habiles_entre))


def hitos_de_entrega(cal: Calendario, anio: int, mes: int, min_dias_habiles_entre: int = 1) -> dict[int, date]:
    """Las tres fechas del cierre del mes `mes` (Karla, 01-11-2026): son **días del mes**, no días hábiles.

    - día 8: análisis hecho y reportes listos, **en la tarde**;
    - día 9: se entrega al Gerente General (revisión);
    - día 10: se entrega al Directorio.

    Si uno cae en día inhábil, el cumplimiento se corre al **día hábil siguiente**. Para que cada paso ocurra después del anterior, entre
    uno y otro hay al menos `min_dias_habiles_entre` días hábiles (parámetro `min_dias_habiles_d7_d10`; supuesto de Legión, editable).
    """
    d8 = cal.siguiente_habil(date(anio, mes, 8))
    d9 = _no_antes_de(cal, date(anio, mes, 9), d8, min_dias_habiles_entre)
    d10 = _no_antes_de(cal, date(anio, mes, 10), d9, min_dias_habiles_entre)
    return {8: d8, 9: d9, 10: d10}


def ventana_del_cierre(cal: Calendario, anio: int, mes: int, min_dias_habiles_entre: int = 1) -> tuple[date, date]:
    """De qué día a qué día es «la semana del cierre»: del primer día hábil del mes al día 8 (reportes listos)."""
    return cal.dia_habil_n(anio, mes, 1), hitos_de_entrega(cal, anio, mes, min_dias_habiles_entre)[8]
