"""Parámetros de cumplimiento. Los valores iniciales de Legión quedan «pendiente de confirmar» hasta que Karla los confirme."""
from nucleo.models import Parametro
from nucleo.servicios import auditoria
from nucleo.servicios.errores import ErrorDeNegocio

# clave: (valor inicial, estado, nota)
INICIALES = {
    "meta_cumplimiento": ("95", "confirmado", "Meta de cumplimiento a tiempo por colaborador (%), fijada por Karla."),
    "umbral_ambar": ("90", "pendiente_confirmar", "Bajo este % el semáforo pasa a rojo. Propuesta de Legión."),
    "plazo_revision_dias_habiles": ("1", "pendiente_confirmar", "Días hábiles para revisar una tarea hecha. Propuesta de Legión."),
    "minimo_muestra_semaforo": ("10", "pendiente_confirmar", "Tareas vencidas mínimas para colorear el semáforo. Propuesta de Legión."),
    "min_dias_habiles_d7_d10": ("1", "pendiente_confirmar", "Días hábiles mínimos entre los días 8, 9 y 10 del cierre cuando alguno se corre por caer en día inhábil (supuesto de Legión, 01-11-2026)."),
    "horas_disponibles_mes": ("160", "pendiente_confirmar", "Horas al mes que una persona dedica a Huentelauquén (valor por defecto de la planificación)."),
    "dias_habiles_mes": ("21", "pendiente_confirmar", "Días hábiles de un mes típico, para repartir la carga por día."),
    "pct_horas_revision": ("25", "pendiente_confirmar", "Horas de revisión = este % de las horas de ejecución de la tarea revisada (planificación)."),
    "carga_ambar": ("90", "pendiente_confirmar", "Desde este % de la capacidad la carga pasa a ámbar."),
    "carga_rojo": ("110", "pendiente_confirmar", "Sobre este % de la capacidad la carga pasa a rojo."),
    "tiempo_obligatorio": ("0", "confirmado", "1 = exigir minutos al marcar «hecha». Apagado en v1 (DEC-09)."),
}


def _obtener(clave: str) -> tuple[str, str]:
    if clave not in INICIALES:
        raise ErrorDeNegocio(f"Parámetro desconocido: {clave}.")
    p = Parametro.objects.filter(clave=clave).first()
    return (p.valor, p.estado_dato) if p else (INICIALES[clave][0], INICIALES[clave][1])


def entero(clave: str) -> int:
    return int(_obtener(clave)[0])


def estado(clave: str) -> str:
    return _obtener(clave)[1]


def guardar(clave: str, valor: str, usuario, confirmado: bool = False) -> Parametro:
    antes = _obtener(clave)
    p, _ = Parametro.objects.update_or_create(
        clave=clave, defaults={"valor": str(valor), "estado_dato": "confirmado" if confirmado else "pendiente_confirmar", "nota": INICIALES[clave][2]},
    )
    auditoria.registrar("parametro.editado", usuario=usuario, entidad="Parametro", entidad_id=clave,
                        antes={"valor": antes[0], "estado": antes[1]}, despues={"valor": p.valor, "estado": p.estado_dato})
    return p
