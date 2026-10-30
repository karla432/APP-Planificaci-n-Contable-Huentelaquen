"""La periodicidad de una tarea en palabras que entiende cualquiera."""
from nucleo.servicios.recurrencia import Regla

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _lista(nombres: list[str]) -> str:
    texto = ", ".join(nombres[:-1]) + (" y " if len(nombres) > 1 else "") + nombres[-1]
    return texto[0].upper() + texto[1:]


def describir(regla: Regla | None, franja: str = "") -> str:
    if regla is None or not regla.tipo:
        return "Sin regla: requiere revisión"
    t = regla.tipo
    if t == "DIARIA_HABIL":
        return "Todos los días hábiles"
    if t == "SEMANAL":
        dia = DIAS[regla.dia_semana] if regla.dia_semana is not None else "día sin indicar"
        return f"Cada {dia}" + (f" ({franja})" if franja else "")
    if t == "CIERRE_DIA_HABIL":
        return f"Día hábil {regla.n} del cierre"
    if t == "CIERRE_HITO":
        return "D7 · reporte preliminar" if regla.n == 7 else "D10 · cierre definitivo"
    if t == "DIA_FIJO":
        return f"Día {regla.dia} de cada mes (si es inhábil, el día hábil {regla.ajuste})"
    if t == "MESES":
        meses = _lista([MESES[m - 1] for m in regla.meses]) if regla.meses else "Meses sin indicar"
        return f"{meses} · " + (f"día {regla.dia}" if regla.dia else "falta indicar el día")
    return "Por evento (se crea a mano)"
