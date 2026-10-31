# 03 · KPI, roles y permisos, segregación de funciones

Versión: F1-v1 · 30-10-2026. Responsable de las definiciones de KPI: Karla Meneses (dueña); diseño: R12. Cada indicador se muestra en pantalla con una nota de cómo se calcula.

## 1. Indicadores

Fuente única: tablas `Ocurrencia` y `EventoAuditoria`. Se calculan en el servidor. Una persona = un colaborador con las ocurrencias que tenía asignadas al generarse (`colaborador_copia`).

| Indicador | Fórmula | Excluye | v1 |
|---|---|---|---|
| **Cumplimiento a tiempo** (oficial, por persona, período y proceso) | Ocurrencias cuya **primera** marca `hecha` fue en o antes de `fecha_limite` ÷ ocurrencias con `fecha_limite` vencida (hechas o no) | `no_aplica` aprobadas; tareas de cargos externos; ocurrencias anteriores a `inicio_medicion` | Sí |
| Completitud | `hecha` (a cualquier hora) ÷ vencidas | Igual | Sí |
| Cumplimiento de revisión (de quien revisa) | Revisiones hechas dentro del plazo ÷ revisiones debidas | — | Sí |
| Tasa de devolución | Devueltas ÷ hechas. No cambia el «a tiempo» original | — | Sí |
| Tasa de «no aplica» | `no_aplica` aprobadas ÷ ocurrencias de la persona | — | Sí |
| Insumos por área (externos) | Ocurrencias `RECIBIDA` a tiempo ÷ vencidas, por cargo externo | No entra en el KPI de nadie (P3) | Sí |
| Riesgo de hito (D7 y D10) | Tareas **pendientes** del hito al día de hoy, por persona; con días hábiles restantes del motor de calendario | Sin horas (DEC-09) | Solo conteo |
| Carga vs capacidad semanal | Horas registradas y comprometidas ÷ horas disponibles | — | **No** (necesita tiempos) |
| Cuellos de botella por predecesoras | Predecesora vencida y no hecha que frena a otra | — | **No** (v2) |

Reglas:
- Una tarea hecha tarde nunca suma como «a tiempo».
- Una tarea `devuelta` vuelve a `pendiente`, pero la primera marca `hecha` es la que cuenta para el «a tiempo». Una segunda `hecha` solo cuenta para completitud y para la tasa de devolución.
- La hora de `hecha` es del servidor. Una marca fuera de plazo por excepción solo la registra el Gerente, con motivo, y aparece marcada en auditoría.
- **Semáforo:** verde ≥ 95 %; ámbar ≥ 90 % y < 95 % (valor de Legión, pendiente de confirmar); rojo < 90 %. Siempre con texto («Cumple», «Bajo la meta», «En riesgo») junto al color. Con menos de 10 tareas vencidas en el período se muestra «n = X, muestra insuficiente» sin color.
- «Sin datos» se muestra como «sin datos». No se calcula nada inventado.
- Al cerrar el período se guarda la foto de los KPI. Después no cambia, aunque cambie la configuración.

## 2. Roles y permisos (validados en el servidor)

| Rol | Quién | Resumen |
|---|---|---|
| `ADMIN_SISTEMA` | Eugenio | Usuarios, permisos y calendario; no marca ni revisa tareas; 2FA obligatorio |
| `GERENTE` | Karla | Todo lo funcional, reabre períodos, aprueba excepciones; 2FA obligatorio |
| `JEFATURA` | Jefa de Control y Gestión | Revisa, marca «Recibido», aprueba «no aplica», edita procesos y tareas |
| `COLABORADOR` | Contador Senior, Analista Contable | Marca solo lo suyo; ve el avance de los demás en solo lectura |
| `LECTURA` | Quien se designe | Solo consulta |

| Acción | ADMIN | GERENTE | JEFATURA | COLAB. | LECTURA |
|---|---|---|---|---|---|
| Ver avance de todo el equipo | Sí | Sí | Sí | Sí | Sí |
| Marcar `hecha` en tareas propias | No | Sí (las suyas) | Sí (las suyas) | Sí | No |
| Marcar `hecha` en tareas ajenas | No | No | No | No | No |
| Revisar / devolver | No | Solo tareas de la Jefa | Sí, menos las suyas | No | No |
| Marcar «Recibido» (externos) | No | No | Sí | No | No |
| Solicitar «no aplica» | No | Sí | Sí | Sí | No |
| Aprobar «no aplica» | No | Sí, si no lo solicitó | Sí, si no lo solicitó | No | No |
| Marca fuera de plazo por excepción (con motivo) | No | Sí | No | No | No |
| Editar procesos y tareas | No | Sí | Sí | No | No |
| Cargos, personas, asignaciones, ausencias | Sí | Sí | No | No | No |
| Calendario, feriados, jornada, parámetros | Sí | Sí | No | No | No |
| Abrir año o mes, cerrar mes | Sí (abrir) | Sí | No | No | No |
| Reabrir período (con motivo) | No | Sí | No | No | No |
| Importar Excel | Sí | Sí | No | No | No |
| Auditoría | Ver | Ver | No | No | No |
| Cuentas y permisos | Sí | No asigna a sí mismo | No | No | No |

Superusuario o staff de Django **no** otorga permisos de la aplicación (mismo criterio del Arqueo).

## 3. Matriz de segregación de funciones

| Función A | Función B | Control |
|---|---|---|
| Ejecutar una tarea | Revisar esa misma tarea | La revisora es la Jefa; la Jefa nunca revisa lo propio (lo revisa el Gerente, P1). El servidor rechaza `revisada_por == hecha_por` |
| Marcar tareas | Marcar tareas de otra persona | El servidor exige `usuario == colaborador_copia`. Sin excepciones salvo la marca por excepción del Gerente, con motivo |
| Solicitar «no aplica» | Aprobarlo | Distinta persona; se mide la tasa de «no aplica» por persona |
| Fijar la hora de `hecha` | Editarla | Nadie edita; la hora es del servidor |
| Marcar «Recibido» | Ser el externo que entrega | El externo no tiene cuenta; la Jefa deja fecha de recepción visible en auditoría |
| Editar una tarea | Editar ocurrencias ya cerradas | Un cambio rige desde el período siguiente; los períodos cerrados no se tocan |
| Administrar cuentas | Operar el checklist | `ADMIN_SISTEMA` no marca ni revisa |
| Reabrir un período | Ser auditado | Solo el Gerente, con motivo; la acción es visible solo para Gerente y administrador |

**Aviso de control:** el Gerente es a la vez dueña del producto, aprueba excepciones y es una de las cuatro personas medidas. Sus 2 tareas las revisa la Jefa, y una marca por excepción propia queda destacada en auditoría.
