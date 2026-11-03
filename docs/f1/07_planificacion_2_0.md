# Planificación 2.0 (03-11-2026)

Karla rehizo la planificación en un Excel de tres hojas. Esta nota explica cómo la carga la app y qué reglas cambian. Las decisiones están en `00_decisiones_y_gates.md` (DEC-35 a DEC-39).

## Qué hoja manda
| Hoja | Qué trae | Qué hace la app |
|---|---|---|
| Maestro | El listado original (188 tareas) | Nada: es respaldo |
| Diario-Semanal | 60 tareas diarias y semanales con horas por día de la semana, modo en semanas de cierre y qué pasa al terminar | Se carga |
| Mensual | 146 tareas del cierre con horas por día hábil (DH00 a DH10), predecesoras, tipo de control y justificación | Se carga |

## Cómo cargarla
Mantenedor → Tareas → Cargar Excel → elegir `Planificacion_2.0_contabilidad.xlsx` (está en `docs/datos/`). La app muestra primero qué va a pasar (tareas nuevas, modificadas, desactivadas, procesos renombrados o nuevos, tareas que cambian de código) y no guarda nada hasta confirmar. Cargar dos veces el mismo archivo no cambia nada la segunda vez.

## Reglas que cambian
- **DH08, DH09 y DH10 son días hábiles** (reportes listos en la tarde, Gerente General, Directorio). **DH00** es el último día hábil del mes anterior. Las semanas del cierre van de DH01 a DH10.
- **La revisión va dentro de las horas de quien ejecuta**: no suma carga al revisor.
- **Proceso 00 «Control del cierre»** (hitos y controles). El cargo ahora es **Analista Contable**.
- **Techo de planificación** (qué parte de la jornada se planifica; el resto es reserva): 90 % de DH00 a DH06, 80 % DH07, 75 % DH08, 85 % DH09 y 95 % DH10.
- Las fechas del archivo (30-10 al 13-11) son de noviembre de 2026: no se leen. La app calcula las de cada mes con su calendario.

## Cómo se reconoce cada tarea
La identidad sigue siendo proceso + tarea + subtarea. Si no coincide, la app prueba en este orden: el proceso renombrado; la misma tarea y subtarea en otro proceso; el mismo proceso y la misma subtarea en otra tarea; el mismo código con la subtarea casi igual (texto corregido). Si hay duda, la fila es nueva y la antigua se desactiva, y tú lo ves antes de confirmar.

## Comprobación hecha
Con el archivo cargado, la matriz de la app reproduce **día por día** la tabla de carga de la hoja Mensual para las cuatro personas (Gerente 43,15 h; Jefa 55,70 h; Contador 64,45 h; Analista 55,90 h entre DH00 y DH10) y cumple todas las predecesoras (224 vínculos en 133 tareas). Está en `pruebas/test_plan2.py`.

## Lo que no se probó
Nada se ejecutó en Windows. El archivo se leyó por sus valores (no por sus fórmulas ni colores).
