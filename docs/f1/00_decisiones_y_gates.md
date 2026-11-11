# 00 · Decisiones, parámetros pendientes y puertas

Versión: F1-v1 · 30-10-2026 · Estado: borrador para G1.

## 1. Decisiones de Karla (respuestas a F0, 30-10-2026)

| ID | Decisión | Efecto en el diseño |
|---|---|---|
| DEC-01 | Equipo inicial de 4 colaboradores: **Gerente AyF**, **Jefa de Control y Gestión**, **Contadora Senior**, **Analista Contable**. En las maquetas, «Encargada de Ingresos» se reemplaza por «Analista Contable». | 4 cuentas funcionales + 1 técnica. El Excel dice «Analista Contable» (33 tareas): se importa como alias de Analista Contable (**confirmar, P5**). |
| DEC-02 | Repositorio nuevo: `karla432/APP-Planificaci-n-Contable-Huentelaquen`. | Creado por Karla; este repositorio es la base. |
| DEC-03 | El stack lo elige Legión (los roles recomiendan, la dueña del producto decide). | ADR-001 en `01_arquitectura_adr.md`. |
| DEC-04 | Se construye desde ya. Listo el **martes 03-11-2026** para probar; las personas registran desde el **jueves 05-11-2026**. | Alcance recortado a un núcleo (sección 3 de `01_arquitectura_adr.md`). |
| DEC-05 | *(Reemplazada el 31-10-2026 por DEC-15.)* **D7 y D10 son día calendario del mes.** Si cae en día inhábil, se **corre al siguiente día hábil** (ej.: 7 en sábado → lunes 9). | Reemplaza mi propuesta inicial («día hábil anterior»). Ver P2 sobre cómo se mueve el D10. |
| DEC-06 | Los responsables externos no aparecen en el cuadro de cumplimiento. **La Jefa de Control y Gestión marca «Recibido»** en vez de «Hecha» para esas tareas. | Tipo de marca `RECIBIDA`; se mide aparte (ver P3). |
| DEC-07 | Rafael es **externo**. | Sus 3 tareas (Ventas Santiago) siguen el flujo de DEC-06. |
| DEC-08 | *(Reemplazada el 31-10-2026 por DEC-17.)* **La revisora es siempre la Jefa de Control y Gestión.** | Sobrescribe la columna `Revisa` del Excel. Excepción por segregación de funciones: ver P1. |
| DEC-09 | *(Reemplazada el 31-10-2026 por DEC-18.)* **Sin tiempos en v1.** Más adelante los colaboradores registran minutos y se compara horas-hombre presupuestadas vs reales. | Los campos `minutos_estimados` y `minutos_reales` existen pero están apagados. No hay carga vs capacidad en v1. |
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
| P3 | Las tareas «Recibido» de externos (9 tareas de 6 cargos externos), ¿cuentan en el KPI de la Jefa o se miden aparte como «insumos por área»? | Aparte, no entran en el KPI de nadie. |
| P4 | **Día 13 (Previred)**: el 13-12-2026 es **domingo**. ¿Se corre al hábil anterior (viernes 11) o al siguiente (lunes 14)? La Contadora Senior debe verificarlo con la norma vigente. El primer Día 13 de la app (13-11-2026) es viernes. | Parámetro sin valor fijo («pendiente de confirmar»). La app avisa antes del 13-12 si sigue sin confirmar. |
| P5 | ¿«Analista Contable» (Excel) es el mismo cargo que «Analista Contable»? | Sí, alias. |
| P6 | El repo nuevo está vacío. ¿Autorizas el primer commit a `main`, o sigo trabajando en la rama `claude/peaceful-ride-ysf0iw` y tú haces el merge? | Rama de trabajo; no toco `main`. |
| P7 | ¿Desde qué fecha cuenta el KPI? El 05-11 es jueves; el 02, 03 y 04 de noviembre ya pasaron o pasarán antes del uso. | El período de noviembre abre con inicio de medición 05-11-2026. Las tareas con vencimiento anterior no se generan. |

### 2b. Respuestas de Karla del 30-10-2026 (tarde)

| ID | Respuesta | Efecto |
|---|---|---|
| P1 | Revisa el **Gerente AyF** las 27 tareas de la Jefa | Implementado en el importador (`cargo_revisor`) |
| P2 | Sí, como propuse | D10 por su cuenta; si choca con el D7 corrido pasa al hábil siguiente; parámetro `min_dias_habiles_D7_D10 = 1` |
| P3 | No entran al KPI de nadie | Los «Recibido» se miden aparte como insumos por área |
| P4 | El viernes (11-12-2026) | Día 13 con ajuste «anterior». Sigue marcado «pendiente de confirmar» hasta que la Contadora Senior verifique la norma de Previred |
| P5 | Es el mismo cargo | «Analista Contable» del Excel se importa como «Analista Contable» |
| P6 | Sí, puedo hacer commits | Commits en la rama `claude/peaceful-ride-ysf0iw` del repo nuevo; no toco `main` salvo que se indique |
| P7 | Desde el 05-11-2026 | `inicio_medicion` del período de noviembre |

### 2c. Hallazgos del importador sobre el Excel (30-10-2026): pregunta nueva P8

La validación con `Fecha 1.ª vez` encontró **5 filas cuya fecha no calza con su regla**. No las corrijo: la app usa lo que dice «Cuándo».

| Fila del Excel | Tarea | «Cuándo» | 1.ª vez en el Excel | Qué haría la app |
|---|---|---|---|---|
| 39 | Fondos por rendir: listar fondos abiertos… | Semanal · Martes (tarde) | lunes 02-11-2026 | Martes (03-11, 10-11, …) |
| 178 | Reportería día 7: Costo en Destino | D7 | martes 08-12-2026 | Vence el D7 (lunes 07-12-2026) |
| 179 | Reportería día 7: Costo por Producto | D7 | miércoles 09-12-2026 | Vence el D7 |
| 180 | Reportería día 7: Ventas Semanales | D7 | jueves 10-12-2026 | Vence el D7 |
| 181 | Reportería día 7: Torre Control Proyecto Los Lilenes | D7 | viernes 11-12-2026 | Vence el D7 |

**P8:** ¿Es correcto el «Cuándo» (martes, D7) o la fecha? Las filas 178 a 181 tienen fechas escalonadas después del D7: si de verdad se entregan después, no deberían figurar como D7. Mi propuesta si no hay respuesta: se usa «Cuándo».

### 2d. Cargos y orden (31-10-2026)

Karla definió el orden de los cargos del equipo: **1. Gerente AyF · 2. Jefa de Control y Gestión · 3. Contadora Senior · 4. Analista Contable**; los responsables externos van después.
**Revierte P5:** el cargo se llama **«Analista Contable»** (como en el Excel), no «Analista Contable». Las listas, selectores y cuadros de cumplimiento siguen ese orden. En las pantallas uso los nombres del Excel («Contadora Senior», «Jefa Gestión y Control»); si prefieres «Contador Senior» o «Jefa de Control», se cambia en un solo lugar.

### 2e. Plan final del 31-10-2026 (Excel «Planificacion_Mensual_Huentelauquen_Revisada»)

Karla entregó la planificación final, en el orden en que se procesa, con el tiempo estimado de cada tarea. **El Excel manda**; la app ya no mapea a 6 áreas ni toca lo que dice el Excel.

| ID | Decisión | Efecto en la app |
|---|---|---|
| DEC-15 | *(Reemplazada el 01-11-2026 por DEC-26: los días 8, 9 y 10 son días del mes.)* **Cierre en días hábiles 1 a 8 con todos los procesos; día 9 se revisa con el Gerente General; día 10 se liberan los informes al Directorio.** Con todas las tareas no se llega al D7. | Reemplaza DEC-05. Regla `CIERRE_DIA_HABIL` (n de 1 a 10). El «D7» del Excel pasa al **día hábil 8** y el «D10» al día hábil 10 (supuesto, ver abajo). El panel muestra la ruta Día 1 a 10. |
| DEC-16 | **Estado «Bloqueada»** (con motivo) además de pendiente, hecha, revisada, devuelta y no aplica. | Una tarea bloqueada no cuenta como hecha; sigue contando como pendiente atrasada si vence. |
| DEC-17 | **Quien revisa es el cargo que dice el Excel** (puede no haber). Los «Recibido» de externos los marca el cargo que dice «Revisa» en el Excel; si está en blanco, la Jefa. | Reemplaza DEC-08. |
| DEC-18 | **Tiempos estimados por tarea** (minutos × ejecuciones al mes). La revisión se carga al revisor (desde DEC-34: minutos de revisión por tarea, 15 por defecto; antes 25 % del tiempo). Capacidad de referencia: 160 h al mes. Semáforo de carga: menos de 90 % verde, 90 a 110 % ámbar, más de 110 % rojo. | Reemplaza DEC-09. Todo se muestra como «Estimado»; los umbrales quedan «pendiente de confirmar». |
| DEC-19 | **Se usan los 34 procesos del Excel**, sin áreas. Los códigos `TAR-nnnn` los asigna la app siguiendo el orden del Excel. | Mantenedor de Procesos sin agrupación por área. |
| DEC-20 | **Cargos** en el orden 1 Gerente AyF, 2 Jefa de Control, 3 Contador Senior, 4 Analista Contable; externos después. Los nombres **«Jefa de Control»** y **«Contador Senior»** son los definitivos (Karla, 31-10-2026: son dos cargos distintos). El Excel dice «Jefa Gestión y Control» y «Contadora Senior»: el importador los traduce y la migración 0009 renombra los que ya existían. | Ver 2d. |

**Confirmado por Karla el 31-10-2026:**
1. El «D7» del Excel significa **día hábil 8** y el «D10», día hábil 10. ✔
2. Se crea la tarea **«Revisión del cierre con Gerente General»**, día hábil 9, a cargo del Gerente AyF, en el proceso «Revisión día 9» (queda entre «Reportería día 7» y «Cierre día 10»). Sin tiempo estimado ni revisor hasta que se definan. El importador la agrega solo (35 procesos y 195 tareas en total). ✔

**Supuestos que siguen pendientes de confirmar:**
3. «Vendedor Stgo» y «Jefe Bodega» se tratan como externos. (Quién recibe lo de los externos sin «Revisa» ya está confirmado: la Jefa de Control.)
4. El Excel trae la **fila 61 duplicada** de la 51: el importador la informa y no la duplica (194 tareas de 195 filas).
5. **Riesgo R28:** 127 tareas no tienen revisor en el Excel. Ya figura en tu auditoría (R07 y R08); la app lo muestra como «sin revisión» y no lo corrige.

**Confirmado por Karla el 31-10-2026 (segunda ronda):**
- Las tareas de externos que el Excel deja sin «Revisa» las recibe la **Jefa de Control**. ✔
- La revisión del día 9 se deja **sin tiempo estimado** por ahora (Karla respondió «ok con el tiempo del día 9», sin indicar una cifra). Si más adelante quiere que cuente en la carga del equipo, se le asigna un tiempo desde el Mantenedor de tareas.

### 2f. Mejoras pedidas por Karla el 31-10-2026 (después de ver la app)

| ID | Decisión | Efecto en la app |
|---|---|---|
| DEC-21 | **Los procesos van en el orden del Excel, no en orden alfabético.** | Cada proceso tiene un `orden` (el de su primera aparición en el Excel) y todas las listas lo siguen. Se puede cambiar desde Excel (ver DEC-24). |
| DEC-22 | **Las personas anotan las horas reales** que ocuparon en cada tarea. | Campo opcional «Horas reales» al marcar hecha y «Registrar horas reales» en el detalle (solo quien ejecuta, mientras el mes esté abierto; cada cambio queda en la bitácora). Se escribe 1,5 o 1:30. «Carga del equipo» compara estimado contra real por persona, solo con las tareas que tienen horas reales. |
| DEC-23 | *(Reemplazada el mismo día por DEC-25.)* **Código de tarea = PRO-TAR-SUB.** | Ejemplo: `PRO-02-TAR-01-SUB-05` = proceso 2 · tarea principal 1 · subtarea 5. Se asigna una sola vez y no cambia aunque se reordene o se edite. Reemplaza `TAR-0001`; la migración 0010 convierte lo que ya existía. |
| DEC-24 | **Descarga y carga masiva en Excel** de Tareas y de Procesos. | Mantenedor → Tareas: «Descargar Excel» y «Cargar Excel» (primero vista previa, luego confirmación; lo que falta en el archivo se desactiva, nunca se borra, y pide confirmación expresa). Mantenedor → Procesos: descarga y carga de orden, activo y procesos nuevos. Solo Gerente y Jefatura. Lo descargado se puede volver a cargar sin cambios. |

**Límites a tener presentes:** la carga masiva rechaza cargos que no existen (para no crear uno por un error de tipeo), archivos de más de 5 MB o de más de 5.000 filas, y no ejecuta fórmulas. El «día hábil siguiente» de un día fijo no se puede escribir en el Excel (se cambia en el Mantenedor). Cambiar el texto de Proceso, Tarea principal o Subtarea en el Excel crea una tarea nueva y desactiva la anterior (la vista previa lo muestra).

| ID | Decisión | Efecto en la app |
|---|---|---|
| DEC-25 | **Código jerárquico `OO-PPP.TT.SSS` en tres niveles** (proceso · tarea · subtarea): orden de ejecución, sigla de 3 letras, correlativo de tarea y de subtarea. Karla: «no me gustó cómo quedó el código». | Ver `06_estructura_y_codigos.md`. El orden es un campo aparte; reordenar actualiza los códigos de todo el árbol en una transacción y guarda el historial. Dependencias entre procesos con etapas y paralelismo. Campos de planificación en los tres niveles. Catálogo base de 11 procesos opcional. |

**Supuestos de Legión para confirmar:** (1) las siglas propuestas para los 35 procesos del Excel (por ejemplo VEN, COM, TES, ACT, CON); (2) las dependencias del catálogo base; (3) las dependencias entre los procesos de Hacienda no se definieron (no las inventé): todos figuran en la etapa 1 hasta que se indiquen.

### 2g. QA de Karla y reglas del cierre (01-11-2026)

| ID | Decisión | Efecto en la app |
|---|---|---|
| DEC-26 | **El cierre se entrega los días 8, 9 y 10 de cada mes** (días del mes, no días hábiles): el **8, en la tarde, ya están el análisis y los reportes**; el **9** se entrega al Gerente General; el **10** al Directorio. Si un día cae en día inhábil, **el cumplimiento se corre al día hábil siguiente**. Reemplaza DEC-15 (días hábiles 8, 9 y 10). | Regla `CIERRE_HITO` con n = 8, 9 o 10. Los días hábiles del cierre van del 1 al 7 y, si uno cae después del día 8, vence el día 8. «D7» del Excel pasa al día 8; «Día hábil 8, 9 y 10» y «D10» pasan a los días 8, 9 y 10. El panel, el cronograma y Abrir mes usan las fechas corridas. |
| DEC-27 | **Jornada: lunes a jueves 9 h y viernes 5 h** (41 h a la semana; antes el viernes era de 4 h). **Gerente AyF: máximo 80 h al mes** para Huentelauquén. | `JORNADA_HORAS` y `Cargo.horas_mes_max` (80 para el Gerente AyF, también al crear el cargo desde el Excel). La matriz avisa si el Gerente pasa de 80 h. |
| DEC-28 | **Semana del cierre** (del primer día hábil al día 8): los tres cargos de cierre se enfocan 100 % en el cierre; **la Analista Contable da continuidad** (ingresa las compras y saca los pagos, y el Contador Senior solo revisa). | Cada tarea tiene «En la semana del cierre»: igual, **pausar** o **reasignar** a otro cargo (con su revisor). Se aplica al abrir el mes, se ve en Abrir mes y viaja en el Excel (columnas «Semana del cierre», «Responsable en el cierre», «Revisa en el cierre»). |
| DEC-29 | **Matriz del cierre**: horas de cada cargo por día contra su jornada, como está hoy y como quedaría con una **propuesta de equilibrio** entre los cuatro cargos. Descargable en Excel para revisarla **antes** de entregarla. | Informes → Matriz del cierre (Gerente y Jefatura) y descarga `matriz_del_cierre_AAAA-MM.xlsx`. La propuesta **no se aplica sola**: la hoja «Planificación» del Excel la trae aplicada y se carga desde Mantenedor → Tareas → Cargar Excel después de revisarla. |
| DEC-30 | **Documentos o evidencia adjuntos a los comentarios** de una tarea; los ve quien ejecuta, a quien se reporta (quien revisa), el Gerente y la Jefatura. | PDF, imágenes, Excel, Word, CSV y texto, hasta 10 MB, con revisión de contenido y huella SHA-256 en la bitácora. Archivos en `evidencias/` (fuera del repositorio; incluir en el respaldo). |
| DEC-31 | **2027 y 2028 cargados de fábrica** con sus feriados confirmados y el calendario abierto. | Migración 0014 con los feriados de la librería de Chile. Revisar la lista en Abrir mes: un feriado decretado a última hora se agrega o corrige ahí. |
| DEC-32 | **Mejoras de pantalla del QA**: filas de tareas compactas (horas reales y botones pequeños a la derecha); panel con días y números que se pinchan y lista de atrasadas; «Requiere atención» por responsable; avance por proceso y cronograma ordenados por código; cronograma por cierre, semana o mes; «Cumplimiento por colaborador» solo en su menú; ficha del proceso con lo esencial primero y lo opcional plegado. | Ver `docs/f1/06_estructura_y_codigos.md` y las pantallas. |
| DEC-33 | **La propuesta de la matriz sigue la lógica de cascada de Karla** (01-11-2026): las tareas del cierre se hacen **de menor a mayor, en el orden de los procesos, ocupando los días desde el 1**; **lo último que se procesa es el costo en destino** (el último día de proceso, el «día 7») y **en paralelo** se hace el **análisis de cuentas**, repartido entre el Contador Senior, la Jefa de Control y la Analista Contable; el **día 8 solo se procesa el paquete de reportes**, que prepara el **Gerente AyF con la skill en un máximo de 3 horas**. | Antes el motor solo movía tareas hacia días posteriores; ahora ordena desde el día 1. El paquete de reportes (proceso «Reportería día 7») baja a 3 h en total; lo que va el día 9 y el 10 no se mueve. La pantalla y el Excel traen un **diagnóstico de control de gestión** (demanda contra capacidad, quién está más exigido, dónde se van las horas y qué porcentaje de las tareas del cierre cae en días que caben en la jornada). |
| DEC-34 | **La revisión es un tiempo real por tarea, no un porcentaje** (Karla, 02-11-2026: «la analista se demora 2 horas y el Contador Senior revisa en 15 minutos»). Cada tarea tiene «minutos de revisión» (Mantenedor y columna «Minutos de revisión» del Excel); si está vacío se usan **15 minutos** (parámetro `minutos_revision`, confirmado). 0 = la revisión no toma tiempo. | Reemplaza el 25 % de DEC-18 (parámetro `pct_horas_revision`, que se elimina). La revisión se carga al revisor el mismo día, por cada vez que se hace la tarea; una tarea sin tiempo de ejecución estimado no carga revisión. Una planilla Excel antigua (sin la columna) no borra los minutos ya guardados. Efecto en noviembre: la revisión hasta el día 8 pasa de 30 h a 35 h (porque hay 84 revisiones de tareas diarias de 15 min), no baja. |
| DEC-35 | **DH08, DH09 y DH10 son días hábiles** (Karla, 03-11-2026, «1. días hábiles»). Noviembre de 2026: 11, 12 y 13. Las semanas del cierre van de **DH01 a DH10**; **DH00** es el último día hábil del mes anterior. «Día hábil N» acepta de 0 a 31 y rangos («Día hábil 4 a 5»). | Reemplaza DEC-26/DEC-33 (días 8, 9 y 10 del mes) y el parámetro `min_dias_habiles_d7_d10`, que se elimina. Ya no existe el tope en el día 8: el DH11 al DH15 son fechas válidas. |
| DEC-36 | **La revisión va dentro de las horas de quien ejecuta** (Karla, 03-11-2026, «2. dejalo dentro de la hora de quien ejecuta»). El parámetro `minutos_revision` vale **0**. | Reemplaza el valor de 15 minutos de DEC-34. El campo «minutos de revisión» por tarea se mantiene por si algún día una revisión es un trabajo aparte. |
| DEC-37 | **La Planificación 2.0 es el plan vigente.** Mandan las hojas Diario-Semanal y Mensual; Maestro es solo respaldo y no se lee (Karla, 03-11-2026, «5. Ok»). Cada tarea trae predecesoras, horas por día (DH00 a DH10 o lunes a viernes), modo en semanas de cierre (Mantiene, Pausa, Fuera del equipo contable), qué pasa al terminar el cierre, tipo de control, qué cambió y por qué. Las fechas del archivo no se leen: la app las calcula con el calendario del mes. | La carga está en `servicios/plan2.py` y se usa desde Mantenedor → Tareas → Cargar Excel (reconoce el archivo de tres hojas). La matriz del cierre muestra primero este plan, con sus hitos, dependencias y techo de planificación; la propuesta de equilibrio quedó como opción aparte. |
| DEC-38 | **Si el código de una tarea mezcla procesos, manda el nombre del proceso** (Karla, 03-11-2026, «3. si dale»): 08-COM.01.002, 10-HON.02.001 y 33-RPT.03.002 pasan a 17-CCO, 11-CHO y 34-RGG (queda el código anterior en el historial). El número y la sigla de cada proceso son los del código que más veces lo acompaña. **Las 8 tareas que el plan ya no trae se desactivan** (no se borran): las 4 que Karla confirmó (21-REM.04.003, 30-CYP.02.006, 31-ACU.03.001, 35-CDF.01.006 — esta última ya existía en el plan con otro código) más 21-REM.04.002, 27-CON.02.001, 35-CDF.01.001, 35-CDF.01.002 y 35-CDF.01.003, que el plan reemplazó por tareas distintas con el mismo código. | Supuestos de Legión a confirmar: (a) «Cierre contable general» (27-CON.02.001 del archivo) se creó como proceso nuevo 36-CCG, porque tiene nombre propio; (b) las tareas nuevas reciben el código que les corresponde en la app, que puede no coincidir con el del archivo cuando el archivo reutilizó un código; las predecesoras se resuelven por el código del archivo, así que no se pierden. |
| DEC-39 | **El cargo se llama «Analista Contable»** (antes «Asistente Contable») y «Jefa Control» del archivo es «Jefa de Control». | Migración 0016 renombra el cargo existente, con sus tareas y personas. |
| DEC-40 | **Respuestas de Karla a las confirmaciones de la Planificación 2.0** (03-11-2026): (1) se desactivan las 8 tareas que el plan ya no trae; (2) la app asigna el código que corresponda, aunque difiera del archivo; (3) «Cierre contable general» es un proceso propio (36-CCG); (4) se usan las duraciones del archivo y **las tareas de 9 minutos pasan a 10 minutos**; (5) el hito 00-CTL.03.001 es del **DH04** y su texto se corrigió a «(DH04)» en `docs/datos/Planificacion_2.0_contabilidad.xlsx`. | La regla de 9 a 10 minutos está en `plan2.MINUTOS_AJUSTADOS`. Si Karla vuelve a cargar su Excel, las tareas siguen quedando en 10 minutos (la app aplica la regla al leer); si quiere verlo también en su Excel, debe cambiar el 0,15 por 0,17 horas. |

**Supuestos de Legión para confirmar:** (1) entre el día 8, el 9 y el 10 hay **al menos un día hábil de distancia** cuando alguno se corre (parámetro `min_dias_habiles_d7_d10`, «pendiente de confirmar»): por ejemplo, en noviembre de 2026 el 8 es domingo, así que los reportes listos son el lunes 09, el Gerente General el martes 10 y el Directorio el miércoles 11; (2) los procesos que cubre la Analista son **Compras, Pagos Banco Estado y Pagos Banco de Chile**; (3) los tres cargos de cierre **pausan** el resto de su operación semanal en esa semana; (4) las horas siguen siendo **estimaciones**: la mayoría de Legión y 24 de la Gerente AyF; (5) el «día 7» (último día de proceso) es el día hábil del 7 del mes o el siguiente, sin pasar del día 8: en noviembre de 2026 hay 6 días hábiles (2 al 9 de noviembre), en diciembre 5 y en enero de 2027 4; (6) el paquete del día 8 pasa de 4 h a 3 h en total repartiendo la reducción en proporción.

**Hallazgo importante de la matriz (noviembre de 2026, con las horas actuales):** el trabajo hasta el día 8 suma unas **269 h** y el equipo solo tiene **200 h** de jornada hasta ese día; aun equilibrando, faltan unas 69 h. Hay que bajar horas estimadas, mover tareas más allá del día 8 o sumar apoyo. Es una decisión de Karla.

## 3. Datos que faltan y no bloquean

- **Impuestos territoriales y patentes** («Cuotas de abril, junio, septiembre y noviembre» y «Enero y julio»): el Excel no trae el día del mes. Noviembre es mes de uso, así que alguien debe indicar el día. Entra al reporte del importador como «requiere revisión».
- Las 4 filas inconsistentes de la sección 2 del encargo siguen igual: el importador las reporta y no las corrige.
- Horas de cierre por día de la semana: parámetro vacío («para uso futuro»).
- Servidor, dominio, SMTP y retención: ver `05_despliegue_respaldo.md`; los define Eugenio.

## 4. Registro de puertas

| Puerta | Artefacto y versión | Estado | Aprobador |
|---|---|---|---|
| G0 | F0 · Nota de comprensión v1 | **Aprobado con condiciones** (respuestas de Karla del 30-10-2026; condiciones = P1 a P7) | Karla Meneses |
| G1 | `docs/f1/` versión F1-v1 | **Aprobado con condiciones**, interpretado a partir de las respuestas de Karla a P1–P7 (30-10-2026). Karla no escribió literalmente «G1 aprobado»: si no era su intención, debe avisar y se detiene la construcción. Condiciones: parámetros marcados «pendiente de confirmar» y riesgo residual RC-04 (SQLite) | Karla Meneses |
| G2 | Build en staging | No solicitada | — |
| G3 | Producción en OpenCloud | No solicitada. Requiere aprobación escrita de Karla, aprobación de Eugenio y restauración de respaldo probada | — |

Aprobar G1 no autoriza producción ni cargar datos reales en el servidor.
