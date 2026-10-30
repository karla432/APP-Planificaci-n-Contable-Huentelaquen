"""Cómo se muestran los indicadores (textos y clases); siempre con palabra además del color."""
from nucleo.servicios import parametros

ETIQUETAS_SEMAFORO = {
    "verde": ("Cumple", "ok"), "ambar": ("Bajo la meta", "warn"), "rojo": ("En riesgo", "red"),
    "muestra_insuficiente": ("Muestra insuficiente (menos de {minimo} tareas vencidas)", "grey"), "sin_datos": ("Sin datos", "grey"),
}


def etiqueta_semaforo(estado: str) -> tuple[str, str]:
    texto, clase = ETIQUETAS_SEMAFORO[estado]
    return texto.format(minimo=parametros.entero("minimo_muestra_semaforo")), clase


def dias_habiles_texto(n: int) -> str:
    return "1 día hábil" if n == 1 else f"{n} días hábiles"
