# 04 · Seguridad, riesgos y plan de pruebas

Versión: F1-v1 · 30-10-2026. R23 (Ciberseguridad), R28 (Compliance/Antifraude), R24 (Calidad). Es un diseño propuesto: no afirma cumplimiento legal ni ausencia de fraude. «Diseño propuesto» ≠ «control implementado» ≠ «efectividad comprobada».

## 1. Modelo de amenazas

Activos: marcas de cumplimiento (evidencia ante la Gerencia), configuración de calendario y reglas, cuentas, base de datos, respaldos.

| ID | Amenaza | Vector | Control propuesto |
|---|---|---|---|
| AM-01 | Marcar «hecha» una tarea ajena o falsear la hora | Manipular la solicitud, abusar de la interfaz | Permiso validado en el servidor; hora del servidor; sin campo de hora |
| AM-02 | Autorrevisión | Mismo usuario ejecuta y revisa | Rechazo en el servicio y prueba negativa |
| AM-03 | Mejorar el KPI con «no aplica» | Solicitudes abusivas | Aprobación por otra persona; tasa por persona visible para la Gerencia |
| AM-04 | Cambiar feriados o reglas para evitar un atraso | Edición retroactiva | Ocurrencias copian regla; períodos cerrados inmutables; feriados con `confirmado_por`; todo auditado |
| AM-05 | Fuerza bruta contra cuentas | Intentos repetidos | 5 intentos → bloqueo 15 min; 2FA para Gerente y administrador; contraseñas de 12+ caracteres |
| AM-06 | Robo de sesión | Cookie expuesta | `HttpOnly`, `Secure`, `SameSite`; HTTPS; vence a los 60 min sin actividad |
| AM-07 | Inyección, XSS, CSRF | Entradas, campos de texto libre (motivos, comentarios) | ORM con consultas parametrizadas; autoescape de plantillas; token CSRF; CSP estricta; sin CDN |
| AM-08 | Editar o borrar la bitácora | Acceso a la base | Triggers contra `UPDATE`/`DELETE`; sello encadenado; `verificar_bitacora`; exportación periódica |
| AM-09 | Importar un Excel con instrucciones o fórmulas | Archivo adjunto | El Excel es dato: solo lectura de celdas, sin evaluar fórmulas ni macros; límite de tamaño; vista previa antes de guardar |
| AM-10 | Pérdida de datos | Falla del servidor, error humano | Respaldo diario cifrado y restauración probada antes de producción |
| AM-11 | Exposición de datos personales | Exceso de datos | Solo nombre, correo, cargo y jornada; sin datos médicos; el tipo de ausencia es genérico |
| AM-12 | Secretos en el repositorio | Descuido | Secretos en variables de entorno del servidor; `.env.example` sin valores; análisis de secretos |

## 2. Matriz de riesgos y controles

| ID | Riesgo | Prob. | Impacto | Control | Dueño | Estado |
|---|---|---|---|---|---|---|
| RC-01 | El calendario calcula mal un D7 o D10 | Media | Alto | Pruebas con los casos de `02_modelo_datos_recurrencia.md`; feriados confirmados por Karla antes de abrir mes | Legión (R24) / Karla | Propuesto |
| RC-02 | KPI engañoso con pocas tareas (Gerente: 2) | Alta | Medio | Mínimo de 10 para colorear; se muestra `n` | R12 | Propuesto |
| RC-03 | Dependencia de una persona (Contador Senior: 115 de 186 tareas) y de una revisora (la Jefa, unas 159) | Alta | Alto | Se muestra la concentración en el panel. No se corrige aquí: es una decisión de organización de Karla | Karla | Visible; decisión humana abierta |
| RC-04 | Inmutabilidad débil de la bitácora en SQLite | Baja | Medio | Sello encadenado, permisos del archivo, respaldo fuera del servidor, disparadores para migrar a PostgreSQL | Eugenio / R23 | **Riesgo residual a aceptar por Karla en G1** |
| RC-05 | Plazo del 05-11 presiona el alcance y las pruebas | Alta | Alto | Alcance recortado; solo lo que pasa pruebas entra en uso | Karla / Legión | Abierto |
| RC-06 | Reglas convertidas mal desde el Excel | Media | Medio | Importador marca «requiere revisión» y valida contra `Fecha 1.ª vez` | R04 | Propuesto |
| RC-07 | Una sola persona despliega (Eugenio) | Media | Medio | Guía de despliegue y runbook escritos; acceso de respaldo definido por Karla | Karla / Eugenio | Abierto |
| RC-08 | Servidor sin respaldo probado | Media | Alto | Prueba de restauración antes de G3 | Eugenio | Propuesto |

## 3. Plan de pruebas (obligatorias de R24)

Pruebas automatizadas con pytest-django. Cada una se ejecuta y queda con evidencia (salida de `pytest`) en el repo.

| Área | Casos |
|---|---|
| Días hábiles y feriados | Semana con feriado en lunes, en viernes y en día intermedio; D7 y D10 en sábado, domingo y feriado; choque D7/D10 (P2); 08-12-2026 entre D7 y D10; cambio de horario de verano |
| Apertura de año y mes | Idempotencia; vista previa; tareas sin responsable o sin regla; año no abierto bloquea; copia de responsable y regla |
| KPI | Hecha a tiempo; hecha tarde; devuelta y vuelta a hacer; `no_aplica` aprobada y rechazada; tarea externa fuera del KPI; persona con ausencia; muestra insuficiente |
| Seguridad (negativas) | Colaborador marca tarea ajena; autorrevisión; colaborador entra a mantenedores y a auditoría; manipular la hora; `UPDATE`/`DELETE` sobre la bitácora; fuerza bruta; XSS en motivos y comentarios; CSRF; inyección en filtros; 2FA exigido a Gerente y administrador |
| Importación del Excel | 186 tareas y 34 procesos; reporte de las 4 filas inconsistentes y de las tareas con cargo externo; filas con día faltante (impuestos territoriales); reimportación sin duplicados; altas, cambios y bajas en la vista previa |
| Respaldo | Respaldar, restaurar en una base nueva y comparar conteos y sellos de la bitácora |
| Auditoría | El sello encadenado detecta una fila alterada |

Entrega de cada incremento: pruebas verdes + captura de las pantallas + documentación actualizada. Commits pequeños.
