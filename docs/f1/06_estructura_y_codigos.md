# 06 · Estructura de tres niveles y códigos OO-PPP.TT.SSS

Versión: 31-10-2026 · Pedido por Karla ("no me gustó cómo quedó el código"). Reemplaza el código `PRO-01-TAR-01-SUB-01` de DEC-23.

## Qué hay
| Nivel | Qué es | Código | Ejemplo |
|---|---|---|---|
| 1 | **Proceso** | `OO-PPP` | `02-VEN` |
| 2 | **Tarea** | `OO-PPP.TT` | `02-VEN.01` |
| 3 | **Subtarea** | `OO-PPP.TT.SSS` | `02-VEN.01.003` |

- **OO** = orden de ejecución del proceso (dos dígitos) · **PPP** = sigla de tres letras · **TT** = correlativo de la tarea dentro del proceso · **SSS** = correlativo de la subtarea dentro de la tarea.
- Cada nivel tiene su código **único** (restricción en la base de datos) y la relación con su nivel superior es una clave foránea protegida: no se puede borrar un proceso con tareas ni una tarea con subtareas.

## Decisiones técnicas (y por qué)
1. **Tres modelos, uno ya existía.** En el código, `Proceso` (nivel 1), `TareaPrincipal` (nivel 2, nuevo) y `Tarea` (nivel 3). `Tarea` es lo que antes era la fila plana «tarea principal + subtarea»: lleva la regla de recurrencia, el responsable y lo que se ejecuta cada mes, así que **ocurrencias, KPI, revisiones y bitácora no cambiaron**. En pantalla se llama «Subtarea». Se mantuvo el nombre `Tarea` en el código para no reescribir todo lo que cuelga de él.
2. **El orden es un campo aparte** (`Proceso.orden`, único) y la sigla es otro (`Proceso.sigla`, única). La identidad de un proceso es su clave (`pk`) y su sigla; el prefijo OO del código solo sigue al orden.
3. **Reordenar es una operación controlada** (`estructura.reordenar_procesos`): recibe la lista completa, valida las dependencias, libera el rango de orden (+1000) para no chocar con la restricción de unicidad, asigna 1..n y en la misma transacción reescribe el código de todo el árbol. Si algo falla, no cambia nada.
4. **Trazabilidad:** cada vez que un código cambia (reordenar, cambiar sigla, mover una subtarea de tarea) el anterior queda en `CambioDeCodigo` y la pantalla de Planificación lo sigue encontrando; además queda un evento sellado en la bitácora (`proceso.reordenado`, etc.).
5. **Los códigos se generan solos** (`codigos.py`, dentro de `save()`): nadie los escribe. Una subtarea que cambia de tarea toma el siguiente correlativo de la nueva; **el hueco que deja no se reutiliza**. Un código con otra forma (por ejemplo los de las pruebas) no se toca.
6. **Límites:** hasta 99 procesos (OO tiene dos dígitos), 99 tareas por proceso y 999 subtareas por tarea. Se validan y se informan con un mensaje claro.
7. **Dependencias entre procesos** (`DependenciaProceso`): sin dependencia a sí mismo, sin ciclos y **solo hacia un proceso que va antes en el orden**; al reordenar no se permite romper una dependencia. Las **etapas** se calculan: la 1 no depende de nadie; cada una siguiente, de algo de las anteriores; los procesos de una misma etapa **pueden ejecutarse en paralelo**.
8. **Campos de planificación** en los tres niveles: responsable, estado (pendiente, en curso, completado, bloqueado), fecha de inicio, fecha de término y observaciones. En la subtarea, el responsable es el cargo que la ejecuta. La fecha de término no puede ser anterior a la de inicio (formulario, servicio y restricción de la base de datos). **Estos campos son de planificación; no reemplazan el estado de cada ejecución mensual** (pendiente/hecha/revisada…), que sigue siendo la fuente del KPI.
9. **Desactivar no borra.** Desactivar un proceso desactiva sus tareas y subtareas (dejan de generarse desde el mes siguiente); reactivar no reactiva lo de abajo salvo que se pida («con sus tareas y subtareas»). No se puede activar algo cuyo superior está desactivado.
10. **No se asume que el orden es el mismo para todas las empresas:** el orden y las dependencias son datos editables de cada instalación; el catálogo base solo es una propuesta de partida.

## Tus procesos y el catálogo base
- Los **35 procesos del Excel de Hacienda** recibieron una sigla propuesta (editable): por ejemplo `VEN` = «Ventas Sala de Ventas», `COM` = «Compras», `TES` = «Tesorería», `ACT` = «Activos fijos», `CON` = «Contabilidad». Quedan en el orden del Excel. Lista completa en `nucleo/siglas.py`.
- El **catálogo base de 11 procesos** (PLA, VEN, CXC, COM, CXP, TES, INV, ACT, CON, IMP, CIE) está disponible con el botón «Cargar el catálogo base» (Mantenedor → Procesos). Agrega al final los que no existan, con las dependencias propuestas (editables). **Las dependencias propuestas son una sugerencia de Legión, pendiente de confirmar.** Para una instalación nueva, `python manage.py cargar_ejemplo_planificacion` (solo desarrollo, solo con la base sin procesos) carga además el ejemplo de Ventas: 3 tareas y 8 subtareas.

## Dónde está
- Modelos: `nucleo/models.py` · migración `0011_tres_niveles_y_codigos` (convierte lo existente: siglas, orden contiguo, tareas y códigos; ocurrencias intactas).
- Códigos: `nucleo/servicios/codigos.py` · estructura (crear, editar, reordenar, dependencias, etapas, catálogo): `nucleo/servicios/estructura.py` · árbol/tabla/filtros: `nucleo/servicios/vista_planificacion.py`.
- Pantallas: Planificación → «Árbol y tabla» (todos; exportar a Excel: Gerente y Jefatura); Mantenedor → Procesos (orden ▲▼, dependencias, tareas, catálogo, Excel) y su ficha.
- Pruebas: `test_estructura.py` (códigos, reordenar, dependencias, relaciones, historial), `test_vistas_estructura.py` (pantallas, filtros, exportación) y los ajustes en importador/Excel masivo.

## Límites conocidos
- Probado con SQLite y en Linux; la migración se verificó sobre la base de ejemplo anterior (35 procesos, 79 tareas, 195 subtareas, 754 ocurrencias intactas), no sobre datos reales.
- Las sigla propuestas para tus procesos hay que revisarlas; cambiarlas es seguro (el código se reescribe y queda el historial).
