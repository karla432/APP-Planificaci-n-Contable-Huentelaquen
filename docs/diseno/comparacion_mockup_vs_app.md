# Mockup de Karla vs. la app: qué unificar

Fecha: 31-10-2026. Fuente del mockup: `docs/diseno/mockup_karla/` (8 capturas y su README). Las pantallas 5 a 8 están comparadas con la descripción del README; las capturas 1 a 4 se revisaron una por una.
Criterio de Karla: **no replicar el mockup tal cual**; tomar las mejores piezas y unirlas con lo ya construido.

## 1. Lo que ya coincide (no hay que tocar)

| Tema | Mockup | App |
|---|---|---|
| Identidad | Bordó `#8C0026`, rojo `#ED0035`, Cambria + Calibri | Igual (misma paleta y tipografías que Arqueo) |
| Revisión | Analista ejecuta, Jefatura aprueba o devuelve | Colaborador marca «hecha», la Jefa revisa o devuelve |
| Gerencia | Solo lectura; aprueba solo lo de la Jefatura | Igual (P1): el Gerente revisa las tareas de la Jefa |
| «Atrasada» | Estado derivado (vence y no está aprobada) | Igual: se calcula, no se guarda |
| Días hábiles y feriados | Excluye fines de semana y feriados de Chile | Igual; feriados confirmados por Karla |
| Auditoría | Cada transición queda con quién y cuándo | Bitácora sellada, inmodificable |

## 2. Pantalla por pantalla

| # | Mockup | App hoy | Propuesta |
|---|---|---|---|
| 1 | **Panel del cierre**: titular con conclusión, cifra grande (% aprobado vs plan), 5 indicadores, avance por área, «Requiere tu atención», próximos vencimientos | Panel con ruta del cierre (Día 1 a 4, D7, D10), 3 indicadores, avance por proceso, riesgos y cumplimiento por colaborador | **Unir.** Traer el titular con conclusión, la cifra grande con «el plan esperaba X %» y «Requiere tu atención» por perfil. **Mantener** la ruta del cierre y el cumplimiento por colaborador (el mockup no los tiene y son tu KPI principal) |
| 2 | **Cronograma** tipo Gantt D1 a D10 por área | No existe | **Traer, adaptado.** Nuestras tareas tienen fecha límite pero no día de inicio, así que no hay barras de inicio a fin: se muestra un mapa de proceso × día con la carga de cada día. Si se quiere Gantt real, hay que agregar «día de inicio» a la tarea |
| 3 | **Tablero** de 4 columnas (Pendiente, En curso, En revisión, Aprobada) | No existe | **Traer.** Columnas con nuestros estados: Pendiente, Por revisar, Revisada, Devuelta. «En curso» y «Bloqueada» no existen hoy (decisión 2 abajo) |
| 4 | **Detalle de tarea** (panel lateral): checklist, evidencia, comentarios, historial, dependencias, horas, referencia Odoo, acciones por perfil | No existe: solo la lista con «Marcar hecha» y el comentario de devolución | **Traer por partes.** Ahora: datos de la tarea, referencia normativa, historial (viene de la bitácora), comentarios y acciones por perfil. Después: dependencias. **Con decisión tuya:** checklist y evidencia adjunta (3) y horas (DEC-09) |
| 5 | **Carga del equipo**: horas contra capacidad | No existe | **Versión sin horas ahora** (abiertas y atrasadas por persona). Horas contra capacidad cuando los colaboradores registren tiempos (DEC-09) |
| 6 | **Vencimientos tributarios**: Previred, F29, DJ, F22, patentes | Solo reglas sueltas (Día 13, meses específicos) | **Traer.** Catálogo de vencimientos con fechas **calculadas**, no fijas. Cada fecha debe validarla la Contador Senior contra el SII (también el Día 13 de Previred, que cae domingo el 13-12-2026) |
| 7 | **Reportes y KPIs**: día hábil de cierre de los últimos 6 meses, % a tiempo, devueltas, atraso promedio, causas de atraso, cumplimiento por área | Cumplimiento por colaborador, de revisión y por insumos externos, con tasa de devolución | **Unir.** Agregar cumplimiento **por proceso/área** y atraso promedio ahora; el histórico de 6 meses sale solo cuando haya meses cerrados; «causa de atraso» como campo opcional al marcar una tarea tarde |
| 8 | **Plantillas de cierre** y «Generar cierre» | Mantenedor de tareas y reglas, pero **sin pantalla para abrir el mes** | **Traer ya: «Cierre mensual → Abrir mes»** con vista previa, avisos de tareas sin responsable y botón de confirmar. Es lo que hace falta para empezar de verdad. Las plantillas por tipo de cierre (trimestral, anual, temporada) quedan para después |

## 3. Diferencias de reglas que hay que unificar

1. **Meta del cierre.** El mockup usa «meta día hábil 8». La app usa lo que tú definiste: **D7 preliminar y D10 definitivo**, día calendario 7 y 10, corridos al siguiente día hábil. Propongo **mantener D7 y D10** y retirar el D8 del mockup.
2. **Estados.** El mockup tiene Pendiente, En curso, Bloqueada, En revisión y Aprobada. La app tiene Pendiente, Hecha, Revisada, Devuelta y No aplica. Equivalencia: *En revisión* = Hecha; *Aprobada* = Revisada.
3. **Áreas.** El mockup agrupa en 6 áreas (Tesorería, Tributario, Remuneraciones, Costos e inventarios, Activo fijo y agrícola, Reportes de gestión). El Excel tiene **34 procesos**. Hay que decidir a qué área pertenece cada proceso para poder filtrar y medir por área.
4. **Personas y roles.** Los nombres del mockup son ficticios y su jerarquía difiere de la real: allí la «Jefatura» es la Jefa de Contabilidad y la «Gerencia» es solo lectura. En la app real: Gerente AyF, Jefa de Control y Gestión, Contador Senior y Asistente Contable. **Se usan los reales.**
5. **Tareas.** El mockup trae 24 tareas de ejemplo. La fuente de verdad es el Excel (186 tareas); las del mockup solo ilustran.
6. **Íconos.** El mockup usa Phosphor Icons desde internet. En la app irían copiados al servidor (la política de seguridad no permite cargar de internet).

## 4. Estilo visual: una decisión tuya

| | Mockup | App hoy (como Arqueo) |
|---|---|---|
| Menú | Blanco, con íconos, ítem activo en rosado | Barra lateral **burdeos**, ítem activo con borde rojo |
| Fondo y bloques | Blanco, sin cajas, mucho espacio | Gris claro con tarjetas de borde fino |
| Titulares | Frase con conclusión, Cambria grande | Título corto en Cambria |
| Cifras | Muy grandes (hasta 140 px) | Grandes (2,4 rem) |

Recomendación: **conservar la barra burdeos de Arqueo** (la pediste) y **traer del mockup los titulares con conclusión, las cifras grandes y el panel lateral de detalle**.

## 5. Orden que recomiendo para traer las piezas

1. Cierre mensual → **Abrir mes** (necesario para operar).
2. **Panel** con titular, cifra grande y «Requiere tu atención».
3. **Tablero** de estados.
4. **Detalle de tarea** (historial, comentarios, acciones).
5. **Calendario tributario** (vencimientos).
6. **Cronograma** por día.
7. **Reportes**: por proceso/área y causas de atraso.
8. **Carga del equipo** (primero sin horas).

## 6. Decisiones que necesito de Karla

1. **Estilo del menú:** ¿burdeos como Arqueo (recomendado) o blanco como el mockup?
2. **Estados:** ¿agregamos «En curso» y «Bloqueada»? Recomiendo **solo «Bloqueada»**, con motivo: avisa un riesgo real; «En curso» agrega un clic sin valor de control.
3. **Evidencia y checklist por tarea:** ¿ahora o después de salir a producción? Los archivos adjuntos exigen controles de seguridad (tipos permitidos, tamaño, dónde se guardan) y el checklist agrega un paso por tarea. Recomiendo **después**.
4. **Áreas:** ¿me dejas proponerte a qué área va cada uno de los 34 procesos, para que lo corrijas?
5. **Cargos:** se mantienen los nombres del Excel («Contador Senior», «Jefa de Control», «Asistente Contable»). ¿O prefieres «Contador Senior» y «Jefa de Control» como escribiste?
