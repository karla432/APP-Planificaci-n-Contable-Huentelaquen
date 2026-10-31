# 02 · Modelo de datos y motor de recurrencia

Versión: F1-v1 · 30-10-2026. Todo valor supuesto o estimado lleva `estado_dato = pendiente_confirmar` y se ve así en pantalla.

## 1. Modelo de datos

**Cambios respecto a la primera versión (construcción, 30-10-2026):** la regla de recurrencia vive aplanada en la tabla `Tarea` (una regla por tarea) en vez de una tabla aparte; `Jornada` y `Ausencia` se difieren a la versión con capacidad semanal (en v1 no hay tiempos ni capacidad, DEC-09).

Los instantes se guardan en UTC. Las fechas de negocio (`fecha_limite`, feriados, ausencias) son fechas sin hora, en `America/Santiago`. No hay borrado físico: se desactiva.

| Tabla | Campos principales | Notas |
|---|---|---|
| `Cargo` | nombre, `es_externo`, activo | Internos: Gerente AyF, Jefa Control y Gestión, Contador Senior, Analista Contable. Externos: RR.HH., Gerencia/Directorio, Bodega, Jefaturas de área, Jefatura Lechería, Rafael |
| `Colaborador` | usuario, nombre, correo, activo | Solo nombre, correo y cargo. Sin datos médicos |
| `Asignacion` | cargo, colaborador, desde, hasta | Vigencia: subrogancias y reemplazos |
| `Proceso` | nombre, activo | 34 en el Excel |
| `Tarea` | `codigo` (TAR-0001…), proceso, tarea_principal, subtarea, `cargo_ejecuta`, `cargo_revisa`, regla, referencia_normativa, `minutos_estimados` (nulo), `clave_estable` (única), activa, `requiere_revision` | La clave es el hash de proceso + tarea + subtarea normalizados, para reimportar sin duplicar |
| `TareaPredecesora` | tarea, predecesora | Se modela ya; las alertas son de v2 |
| `ReglaRecurrencia` | tipo, parametros (JSON), franja, `ajuste_inhabil` (`siguiente`/`anterior`), `estado_dato` | Ver sección 2 |
| `Anio` | año, estado (`borrador`/`abierto`/`cerrado`) | |
| `Feriado` | fecha, nombre, tipo (`legal`/`irrenunciable`/`decretado`/`regional`), `confirmado`, `confirmado_por`, `confirmado_en` | Cargado desde librería; solo cuenta cuando está confirmado |
| `Jornada` | cargo o colaborador, día de la semana, horas, hora_cierre (nulo), desde, hasta | L–J 9 h y viernes 4 h, confirmado (DEC-14) |
| `Ausencia` | colaborador, fecha, fracción (1 o 0,5), tipo (`vacaciones`/`permiso`/`otra`) | Sin detalle médico |
| `Periodo` | año, mes, estado (`borrador`/`abierto`/`cerrado`), `inicio_medicion`, `kpi_foto` (JSON), cerrado_por/en | El período M tiene las diarias y semanales del mes M y el cierre del mes M−1 |
| `Ocurrencia` | tarea, periodo, `fecha_limite`, `cargo_ejecuta_copia`, `colaborador_copia`, `cargo_revisa_copia`, `regla_copia` (JSON), estado, `hecha_en` (UTC, solo servidor), `hecha_por`, `tipo_marca` (`HECHA`/`RECIBIDA`), `revisada_en`, `revisada_por`, `minutos_reales` (nulo), `por_excepcion`, `motivo_excepcion` | Única por (tarea, período, fecha_limite). Copia el responsable y la regla vigentes al generarse |
| `SolicitudNoAplica` | ocurrencia, motivo, solicitante, aprobador, estado | Aprueba alguien distinto del solicitante |
| `Parametro` | clave, valor, `estado_dato`, nota | Meta 95, ámbar 90, plazo de revisión 1, mínimo de muestra 10, `min_dias_habiles_D7_D10`, política de tiempo (apagada) |
| `EventoAuditoria` | momento UTC, usuario, acción, entidad, antes, después, `sello` (hash encadenado) | Triggers impiden `UPDATE` y `DELETE` |

Estados de `Ocurrencia`: `pendiente → hecha → revisada | devuelta (vuelve a pendiente con comentario)`, y `no_aplica` (solo por solicitud aprobada). Para tareas externas, `tipo_marca = RECIBIDA` y la marca la hace la Jefa.

Cambios de tareas: rigen desde el período siguiente (o desde una fecha elegida) y nunca tocan ocurrencias de períodos cerrados.

## 2. Motor de recurrencia

### Funciones base (calendario)

```
es_habil(f)            = f.weekday() <= 4 y f no es feriado confirmado
siguiente_habil(f)     = f si es_habil(f), si no siguiente_habil(f + 1 día)
anterior_habil(f)      = f si es_habil(f), si no anterior_habil(f − 1 día)
dia_habil_n(M, n)      = el n-ésimo día hábil del mes M
hito(M, d)             = siguiente_habil(fecha(M.año, M.mes, d))     # D7 con d=7, D10 con d=10
D10 final              = si hito(M,10) <= hito(M,7): siguiente_habil(hito(M,7) + 1)   # propuesta P2
```

Un año no abierto o con feriados sin confirmar **bloquea** la apertura de sus meses.

### Tipos de regla

| Tipo | Parámetros | Cuándo del Excel (cantidad) | Fecha límite |
|---|---|---|---|
| `DIARIA_HABIL` | — | «Todos los días hábiles» (23) | Cada día hábil del mes, desde `inicio_medicion` |
| `SEMANAL` | día de la semana, franja opcional | Lunes (3), Martes mañana (3) y tarde (2), Jueves (1), Viernes (9), Miércoles (6) | Ese día de cada semana del mes; si es feriado, `siguiente_habil` (DEC-14) |
| `CIERRE_DIA_HABIL` | n (1 a 4) | Día hábil 1 (10), 2 (14), 3 (45), 4 (36) | `dia_habil_n(M, n)`, para el cierre de M−1 |
| `CIERRE_HITO` | d (7 o 10) | D7 (18), D10 (8) | `hito(M, d)` con las reglas de D7/D10 (DEC-05) |
| `DIA_FIJO` | día del mes, ajuste | Día 13 (1) | Día 13 con `ajuste_inhabil`; **valor pendiente, P4** |
| `MESES` | lista de meses, día | «Cuotas de abril, junio, septiembre y noviembre», «Enero y julio» | Solo si el día está definido; si falta, la fila queda «requiere revisión» |
| `EVENTO` | — | «Al dar de alta un activo nuevo», «Al recibir el subsidio» | Se crea a mano; sin vencimiento fijo hasta que se asigna |

La fecha de 1.ª vez del Excel **no** calcula nada: solo se compara con la fecha que sale de la regla, para detectar reglas mal convertidas (ej.: «Lunes» ↔ 02-11-2026; «Día hábil 1» ↔ 01-12-2026; «Día 13» ↔ 13-11-2026).

### Ejemplos (solo supongo el 08-12-2026 como feriado, según el encargo; los demás feriados los confirma Karla)

| Caso | Entrada | Resultado |
|---|---|---|
| D7 en día hábil | D7 de diciembre 2026: lunes 07-12 | 07-12-2026 |
| D10 en día hábil | D10 de diciembre 2026: jueves 10-12 | 10-12-2026 |
| D7 en sábado (el ejemplo de Karla) | Día 7 = sábado | Lunes 9 |
| D7 en domingo | Día 7 = domingo | Lunes 8 |
| D7 en viernes feriado | Día 7 = viernes feriado | Lunes 10; choca con el D10 → regla P2 |
| Día hábil entre D7 y D10 con feriado | 08-12-2026 es martes feriado | Hábiles de diciembre: 1, 2, 3, 4, 7, 9, 10 |
| Día 13 en domingo | 13-12-2026 | Sin valor fijo hasta resolver P4 |
| Semanal en feriado | «Lunes» y el lunes es feriado | Martes (siguiente hábil) |
| Cambio de horario de verano | Marca a las 23:30 hora de Chile en la noche del cambio | La fecha de negocio no se mueve; el vencimiento es por fecha, no por hora |

### Abrir mes (asistente con vista previa)

1. Verifica que el año esté `abierto` y los feriados confirmados.
2. Genera la vista previa: ocurrencias por tarea y fecha, más avisos (tareas sin responsable vigente, sin regla válida, con responsable ausente, «requiere revisión»).
3. Al confirmar, genera en una transacción. **Idempotente:** la clave única impide duplicar. Si se abre dos veces, la segunda no crea nada.
4. Cada ocurrencia copia responsable y regla. Cambios posteriores no reescriben el pasado.
5. Queda en auditoría.

**Cierre del período:** bloquea ediciones y guarda la foto inmutable de los KPI. Reabrir exige rol Gerente y un motivo, y queda en auditoría.

**Primer mes (noviembre 2026):** diarias y semanales de noviembre desde el `inicio_medicion` (propuesta 05-11-2026, P7); el cierre de octubre **no** se sigue en la app; el cierre de noviembre ocurre en diciembre.
