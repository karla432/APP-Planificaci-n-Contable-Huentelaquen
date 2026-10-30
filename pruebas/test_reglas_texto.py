"""La periodicidad en palabras que entiende cualquiera (para el mantenedor y el check list por cargo)."""
import pytest

from nucleo.servicios.recurrencia import Regla
from nucleo.servicios.reglas_texto import describir


@pytest.mark.parametrize(
    "regla,franja,esperado",
    [
        (Regla("DIARIA_HABIL"), "", "Todos los días hábiles"),
        (Regla("SEMANAL", dia_semana=0), "", "Cada lunes"),
        (Regla("SEMANAL", dia_semana=1), "tarde", "Cada martes (tarde)"),
        (Regla("SEMANAL", dia_semana=2), "", "Cada miércoles"),
        (Regla("CIERRE_DIA_HABIL", n=3), "", "Día hábil 3 del cierre"),
        (Regla("CIERRE_HITO", n=7), "", "D7 · reporte preliminar"),
        (Regla("CIERRE_HITO", n=10), "", "D10 · cierre definitivo"),
        (Regla("DIA_FIJO", dia=13, ajuste="anterior"), "", "Día 13 de cada mes (si es inhábil, el día hábil anterior)"),
        (Regla("DIA_FIJO", dia=13, ajuste="siguiente"), "", "Día 13 de cada mes (si es inhábil, el día hábil siguiente)"),
        (Regla("MESES", meses=(1, 7)), "", "Enero y julio · falta indicar el día"),
        (Regla("MESES", meses=(4, 6, 9, 11), dia=20), "", "Abril, junio, septiembre y noviembre · día 20"),
        (Regla("EVENTO"), "", "Por evento (se crea a mano)"),
        (None, "", "Sin regla: requiere revisión"),
    ],
)
def test_describe_cada_regla_en_palabras(regla, franja, esperado):
    assert describir(regla, franja) == esperado
