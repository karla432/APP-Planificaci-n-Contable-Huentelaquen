"""Días hábiles y hitos de cierre. Lógica pura: no toca la base de datos.

Día hábil = lunes a viernes que no sea feriado. Las fechas son fechas de negocio (America/Santiago), sin hora.
Solo deben pasarse feriados CONFIRMADOS (ver `nucleo.models.Feriado`).
"""
import calendar
from datetime import date, timedelta
from typing import Iterable


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


def hitos_de_cierre(cal: Calendario, anio: int, mes: int, min_dias_habiles_entre: int = 1) -> tuple[date, date]:
    """(D7, D10) del mes `mes` (cierre del mes anterior).

    D7 y D10 son día calendario 7 y 10; si caen en día inhábil pasan al siguiente día hábil (DEC-05).
    Si el D10 corrido no queda después del D7 corrido, pasa al día hábil siguiente al D7 (P2, aprobada por Karla).
    `min_dias_habiles_entre` es el parámetro `min_dias_habiles_D7_D10`: días hábiles mínimos entre ambos hitos.
    """
    d7 = cal.siguiente_habil(date(anio, mes, 7))
    d10 = cal.siguiente_habil(date(anio, mes, 10))
    if cal.dias_habiles_entre(d7, d10) < min_dias_habiles_entre or d10 <= d7:
        d10 = d7
        for _ in range(min_dias_habiles_entre):
            d10 = cal.siguiente_habil(d10 + timedelta(days=1))
    return d7, d10
