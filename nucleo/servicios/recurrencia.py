"""Motor de recurrencia: regla + período → fechas límite. Lógica pura, sin base de datos.

Un período M reúne las tareas diarias y semanales del mes M y el cierre del mes M−1, que vence en los primeros
días del mes M (Día hábil 1 a 4, D7, D10).
"""
import calendar
from dataclasses import dataclass
from datetime import date

from nucleo.servicios.calendario import Calendario, hitos_de_entrega

TIPOS = ("DIARIA_HABIL", "SEMANAL", "CIERRE_DIA_HABIL", "CIERRE_HITO", "DIA_FIJO", "FIN_DE_MES", "MESES", "EVENTO")
AJUSTES = ("siguiente", "anterior")


class ReglaInvalida(ValueError):
    """La regla tiene un tipo o valor que el motor no reconoce."""


class ReglaIncompleta(ValueError):
    """A la regla le falta un dato para calcular la fecha (la fila queda «requiere revisión»)."""


@dataclass(frozen=True)
class Regla:
    tipo: str
    dia_semana: int | None = None  # 0 = lunes … 4 = viernes (SEMANAL)
    n: int | None = None  # n-ésimo día hábil (CIERRE_DIA_HABIL; 0 = último hábil del mes anterior) o DH08, DH09 o DH10 (CIERRE_HITO)
    dia: int | None = None  # día del mes (DIA_FIJO, MESES)
    meses: tuple[int, ...] = ()  # MESES
    ajuste: str = "siguiente"  # qué hacer si cae en día inhábil


def _ajustar(cal: Calendario, f: date, ajuste: str) -> date:
    return cal.siguiente_habil(f) if ajuste == "siguiente" else cal.anterior_habil(f)


def _fecha_del_mes(anio: int, mes: int, dia: int) -> date:
    try:
        return date(anio, mes, dia)
    except ValueError:
        raise ReglaInvalida(f"El día {dia} no existe en {mes:02d}-{anio}.") from None


def fechas_limite(
    regla: Regla,
    anio: int,
    mes: int,
    cal: Calendario,
    inicio_medicion: date | None = None,
) -> list[date]:
    if regla.tipo not in TIPOS:
        raise ReglaInvalida(f"Tipo de regla desconocido: {regla.tipo!r}.")
    if regla.ajuste not in AJUSTES:
        raise ReglaInvalida(f"Ajuste desconocido: {regla.ajuste!r}.")

    if regla.tipo == "DIARIA_HABIL":
        fechas = cal.dias_habiles_del_mes(anio, mes)
    elif regla.tipo == "SEMANAL":
        if regla.dia_semana is None:
            raise ReglaIncompleta("Falta el día de la semana.")
        ultimo = calendar.monthrange(anio, mes)[1]
        fechas = [
            cal.siguiente_habil(d)  # semanal en feriado: siguiente día hábil (DEC-14)
            for d in (date(anio, mes, n) for n in range(1, ultimo + 1))
            if d.weekday() == regla.dia_semana
        ]
    elif regla.tipo == "CIERRE_DIA_HABIL":
        if regla.n is None:
            raise ReglaIncompleta("Falta el número de día hábil.")
        if not 0 <= regla.n <= 31:
            raise ReglaInvalida("El día hábil del cierre debe estar entre 0 (último hábil del mes anterior) y 31.")
        fechas = [cal.dia_habil_n(anio, mes, regla.n)]
    elif regla.tipo == "CIERRE_HITO":
        if regla.n not in (8, 9, 10):
            raise ReglaInvalida("El hito de cierre debe ser el día hábil 8 (reportes listos), el 9 (Gerente General) o el 10 (Directorio).")
        fechas = [hitos_de_entrega(cal, anio, mes)[regla.n]]
    elif regla.tipo == "DIA_FIJO":
        if regla.dia is None:
            raise ReglaIncompleta("Falta el día del mes.")
        fechas = [_ajustar(cal, _fecha_del_mes(anio, mes, regla.dia), regla.ajuste)]
    elif regla.tipo == "FIN_DE_MES":
        fechas = [_ajustar(cal, date(anio, mes, calendar.monthrange(anio, mes)[1]), regla.ajuste)]
    elif regla.tipo == "MESES":
        if mes not in regla.meses:
            fechas = []
        elif regla.dia is None:
            raise ReglaIncompleta("Faltan el día del mes en que vence.")
        else:
            fechas = [_ajustar(cal, _fecha_del_mes(anio, mes, regla.dia), regla.ajuste)]
    else:  # EVENTO: se crea a mano, sin vencimiento fijo
        fechas = []

    if inicio_medicion is not None:
        fechas = [f for f in fechas if f >= inicio_medicion]
    return fechas
