# 00 · Decisiones, parámetros pendientes y puertas

Versión: F1-v1 · 30-10-2026 · Estado: borrador para G1.

## 1. Decisiones de Karla (respuestas a F0, 30-10-2026)

| ID | Decisión | Efecto en el diseño |
|---|---|---|
| DEC-01 | Equipo inicial de 4 colaboradores: **Gerente AyF**, **Jefa de Control y Gestión**, **Contadora Senior**, **Analista Contable**. En las maquetas, «Encargada de Ingresos» se reemplaza por «Analista Contable». | 4 cuentas funcionales + 1 técnica. El Excel dice «Asistente Contable» (33 tareas): se importa como alias de Analista Contable (**confirmar, P5**). |
| DEC-02 | Repositorio nuevo: `karla432/APP-Planificaci-n-Contable-Huentelaquen`. | Creado por Karla; este repositorio es la base. |
| DEC-03 | El stack lo elige Legión (los roles recomiendan, la dueña del producto decide). | ADR-001 en `01_arquitectura_adr.md`. |
| DEC-04 | Se construye desde ya. Listo el **martes 03-11-2026** para probar; las personas registran desde el **jueves 05-11-2026**. | Alcance recortado a un núcleo (sección 3 de `01_arquitectura_adr.md`). |
| DEC-05 | **D7 y D10 son día calendario del mes.** Si cae en día inhábil, se **corre al siguiente día hábil** (ej.: 7 en sábado → lunes 9). | Reemplaza mi propuesta inicial («día hábil anterior»). Ver P2 sobre cómo se mueve el D10. |
| DEC-06 | Los responsables externos no aparecen en el cuadro de cumplimiento. **La Jefa de Control y Gestión marca «Recibido»** en vez de «Hecha» para esas tareas. | Tipo de marca `RECIBIDA`; se mide aparte (ver P3). |
| DEC-07 | Rafael es **externo**. | Sus 3 tareas (Ventas Santiago) siguen el flujo de DEC-06. |
| DEC-08 | **La revisora es siempre la Jefa de Control y Gestión.** | Sobrescribe la columna `Revisa` del Excel. Excepción por segregación de funciones: ver P1. |
| DEC-09 | **Sin tiempos en v1.** Más adelante los colaboradores registran minutos y se compara horas-hombre presupuestadas vs reales. | Los campos `minutos_estimados` y `minutos_reales` existen pero están apagados. No hay carga vs capacidad en v1. |
| DEC-10 | Permisos de la Jefa: edita procesos y tareas; calendario, parámetros, usuarios y apertura/cierre de períodos quedan para Gerente y administrador. | Matriz de `03_kpi_roles_sod.md`. |
| DEC-11 | Feriados: se cargan desde una librería y Karla confirma la lista de cada año. | Sin fechas de feriados escritas a mano en el código. |
| DEC-12 | Despliegue parecido al Arqueo, en el servidor **OpenCloud**; despliega y mejora siempre **Eugenio**. | `05_despliegue_respaldo.md`. |
| DEC-13 | Nombre: **Planificación Contable Huentelauquén**. | En pantalla uso la ortografía de la empresa (Huentelauquén); el repositorio queda como lo creaste. |
| DEC-14 | Confirmado «está bien tu entendimiento»: D7/D10 calendario; jornada L–J 9 h y viernes 4 h (40 h); las diarias vencen al fin del día hábil; semanales en feriado pasan al siguiente día hábil. | Parámetros marcados «confirmado por Karla». |

### Decididas por Legión por delegación de Karla (pregunta 7). Son parámetros editables, marcados «propuesta pendiente de confirmar»

| Parámetro | Valor inicial | Razón (R12) |
|---|---|---|
| Umbral ámbar del semáforo | 90 % | Con 27 tareas, 1 atraso = 96,3 % (verde), 2 = 92,6 % (ámbar), 3 = 88,9 % (rojo): el umbral separa «un tropiezo» de «un patrón». |
| Plazo de revisión | 1 día hábil desde la marca `hecha` | Evita que la revisión del D7 se acumule contra el D10. |
| Mínimo de tareas para colorear el semáforo | 10 en el período | El Gerente AyF tiene 2 tareas: un atraso sería 50 %. Bajo el mínimo se muestra «n = 2, muestra insuficiente», sin color. |

## 2. Preguntas abiertas que necesito antes de G1 (máximo 6)

| ID | Pregunta | Mi propuesta si no hay respuesta |
|---|---|---|
| P1 | La Jefa ejecuta 27 tareas y no puede revisarse a sí misma. ¿Quién las revisa? En el Excel hoy las revisa la Contadora Senior (17), el Gerente (4) o nadie (6). | El **Gerente AyF** revisa las 27 tareas de la Jefa. La Jefa revisa todo lo demás, incluidas las 2 del Gerente. |
| P2 | Cuando el D7 se corre, ¿el D10 se corre aparte (sigue su propio día 10) o conserva la distancia con el D7? Hay un choque posible: si el 7 es viernes feriado, el D7 pasa al lunes 10 y coincide con el D10. | El D10 se evalúa por su cuenta (día 10 → siguiente hábil). Si D10 ≤ D7 corrido, el D10 pasa al día hábil siguiente al D7. Parámetro `min_dias_habiles_D7_D10 = 1`. |
| P3 | Las tareas «Recibido» de externos (6 tareas), ¿cuentan en el KPI de la Jefa o se miden aparte como «insumos por área»? | Aparte, no entran en el KPI de nadie. |
| P4 | **Día 13 (Previred)**: el 13-12-2026 es **domingo**. ¿Se corre al hábil anterior (viernes 11) o al siguiente (lunes 14)? La Contadora Senior debe verificarlo con la norma vigente. El primer Día 13 de la app (13-11-2026) es viernes. | Parámetro sin valor fijo («pendiente de confirmar»). La app avisa antes del 13-12 si sigue sin confirmar. |
| P5 | ¿«Asistente Contable» (Excel) es el mismo cargo que «Analista Contable»? | Sí, alias. |
| P6 | El repo nuevo está vacío. ¿Autorizas el primer commit a `main`, o sigo trabajando en la rama `claude/peaceful-ride-ysf0iw` y tú haces el merge? | Rama de trabajo; no toco `main`. |
| P7 | ¿Desde qué fecha cuenta el KPI? El 05-11 es jueves; el 02, 03 y 04 de noviembre ya pasaron o pasarán antes del uso. | El período de noviembre abre con inicio de medición 05-11-2026. Las tareas con vencimiento anterior no se generan. |

## 3. Datos que faltan y no bloquean

- **Impuestos territoriales y patentes** («Cuotas de abril, junio, septiembre y noviembre» y «Enero y julio»): el Excel no trae el día del mes. Noviembre es mes de uso, así que alguien debe indicar el día. Entra al reporte del importador como «requiere revisión».
- Las 4 filas inconsistentes de la sección 2 del encargo siguen igual: el importador las reporta y no las corrige.
- Horas de cierre por día de la semana: parámetro vacío («para uso futuro»).
- Servidor, dominio, SMTP y retención: ver `05_despliegue_respaldo.md`; los define Eugenio.

## 4. Registro de puertas

| Puerta | Artefacto y versión | Estado | Aprobador |
|---|---|---|---|
| G0 | F0 · Nota de comprensión v1 | **Aprobado con condiciones** (respuestas de Karla del 30-10-2026; condiciones = P1 a P7) | Karla Meneses |
| G1 | `docs/f1/` versión F1-v1 | **Pendiente** | Karla Meneses |
| G2 | Build en staging | No solicitada | — |
| G3 | Producción en OpenCloud | No solicitada. Requiere aprobación escrita de Karla, aprobación de Eugenio y restauración de respaldo probada | — |

Aprobar G1 no autoriza producción ni cargar datos reales en el servidor.
