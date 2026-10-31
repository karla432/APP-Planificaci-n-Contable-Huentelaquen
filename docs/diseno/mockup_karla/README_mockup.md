# Handoff: Control de Planificación del Cierre Contable — Hacienda Huentelauquén

## Overview
Aplicación web de escritorio para planificar, ejecutar y controlar el cierre contable mensual (y los cierres trimestral, anual y de temporada) del departamento de Contabilidad de Hacienda Huentelauquén, una empresa agrícola (paltos) y productora de alimentos (lechería, quesería, planta de empanadas). Permite asignar tareas por día hábil, seguir su avance, aprobar con evidencia, controlar la carga del equipo y los vencimientos tributarios, y medir el cumplimiento.

## About the Design Files
Los archivos de este paquete son **referencias de diseño hechas en HTML**: prototipos que muestran el aspecto y el comportamiento esperados, no código de producción para copiar directamente. La tarea es **recrear estos diseños en el entorno del codebase de destino** (React, Vue, etc.) usando sus patrones y librerías. Si todavía no existe un codebase, se recomienda **React + TypeScript (Vite)** con un backend que se integre con **Odoo 18** (vía XML-RPC/JSON-RPC) para las referencias de asientos, diarios y adjuntos.

Para ver un prototipo, abre el `.dc.html` en un navegador servido por HTTP (por ejemplo `npx serve .`). Toda la lógica está en la clase `Component` dentro del `<script data-dc-script>` del archivo, y los datos de muestra están en las constantes al inicio de esa clase (`T0`, `DEPS`, `CHK`, `VENC`, `TPL`, `P`, `AREAS`).

- `Planificacion Contable Huentelauquen.dc.html` → **versión principal** con la identidad de Huentelauquén.
- `Planificacion Contable (Broadsheet).dc.html` → la misma app con el estilo base anterior; sirve solo como referencia.

## Fidelity
**Alta fidelidad (hi-fi)** en estructura, contenido, flujo y estados. Los colores y la tipografía siguen la identidad de Huentelauquén (ver Design Tokens). Si el codebase ya tiene un sistema de componentes, úsalo y conserva la paleta y la tipografía de la marca.

## Roles
Hay un selector de rol en el encabezado (solo en el prototipo; en producción el rol vendrá del login).
| Rol | Usuario demo | Menú visible | Permisos |
|---|---|---|---|
| Jefatura | Karla Muñoz, Jefa de Contabilidad | Todo (7 secciones) | Todo: iniciar, enviar a revisión, aprobar, devolver, reabrir, generar cierres, editar plantillas |
| Analista | Valentina Soto, Analista de Costos | Panel, Tablero, Cronograma, Vencimientos, Reportes | Actúa solo sobre sus propias tareas; no aprueba |
| Gerencia | Andrés Vega, Gerente de Adm. y Finanzas | Panel, Cronograma, Vencimientos, Reportes | Solo lectura; aprueba únicamente las tareas cuyo responsable es la Jefatura |

## Modelo de datos (sugerido)
- **Cierre**: período (2026-10), plantilla, fecha de inicio, día hábil meta (8), estado.
- **Tarea**: id, título, área, responsable, revisor, día hábil de inicio, día hábil límite, estado, horas estimadas, referencia Odoo (diario, cuenta o asiento), descripción, dependencias[], checklist[], evidencias[], comentarios[] (historial).
- **Estados**: `pend` Pendiente → `curso` En curso ⇄ `bloq` Bloqueada → `rev` En revisión → `apr` Aprobada (o vuelve a `curso` si se devuelve). Además, **Atrasada** es un estado *derivado*: estado ≠ `apr` y día límite < día hábil de hoy.
- **Persona**: nombre, cargo y horas diarias disponibles para el cierre (capacidad).
- **Vencimiento**: obligación, período, fecha, responsable y tarea vinculada (opcional).
- **Plantilla**: nombre, recurrencia, tareas (título, área, día hábil, rol responsable, evidencia requerida).
- **Áreas**: Tesorería, Tributario, Remuneraciones, Costos e inventarios, Activo fijo y agrícola, Reportes de gestión.
- **Días hábiles**: el día hábil 1 (D1) es el primer día hábil del mes siguiente al período. Excluye fines de semana y feriados de Chile.

## Screens / Views

### Layout general
- **Menú lateral** (variante por defecto): 250 px de ancho, sticky, con la marca ("HACIENDA" en un kicker rojo + "Huentelauquén" en Cambria de 24 px), 7 ítems con ícono de 20 px y padding de 9×10 px, y el pie "Cierre de octubre 2026 · Meta: día hábil 8".
- **Variante "Superior"**: la marca va en línea en el header y la navegación pasa a una fila de chips bajo el header.
- **Main**: max-width 1320 px y padding de 30 px arriba / clamp(20px, 4vw, 48px) a los lados / 100 px abajo.
- **Header**: contexto ("Cierre de octubre 2026 · Hoy … · Día hábil 3 de 8"), selector de rol (segmentado) y avatar con iniciales (34 px, círculo).
- Cada pantalla abre con un kicker (12 px, mayúsculas, tracking .1em, negrita, rojo #ED0035) seguido de un **H1 que es una frase con conclusión**, no un título genérico. Ejemplo: "Día hábil 3 de 8: el cierre va 4 puntos bajo el plan."

### 1. Panel del cierre
- Muestra el porcentaje aprobado en una cifra grande (Cambria 140 px, bordó), con el texto "de las tareas aprobadas · el plan esperaba X% a hoy". Al lado van 5 indicadores: Aprobadas, En revisión, En curso, Pendientes y Atrasadas o bloqueadas (este último en rojo).
- Debajo, una grilla `auto-fit minmax(320px,1fr)` con tres columnas:
  - **Avance por área**: barra de 4 px más el texto "aprobadas/total".
  - **Requiere tu atención**: para la Jefatura, tareas atrasadas o bloqueadas y las que están por aprobar; para el Analista, "Mis tareas abiertas"; para Gerencia, "Riesgos del cierre". Cada fila abre el detalle.
  - **Próximos vencimientos**: los 3 más cercanos y el enlace al calendario tributario.
- **Variante "Por día hábil"**: lista agrupada de D1 a D8, con una columna de día a la izquierda (150 px) y las filas Tarea / Responsable / Estado.

### 2. Cronograma
- Gantt por días hábiles: una columna de nombre de 260 px más 10 columnas (D1 a D10). La columna de hoy lleva un fondo tenue.
- Las tareas van agrupadas por área. Cada barra va del día de inicio al día límite, mide 24 px de alto y muestra las iniciales del responsable. El color de la barra indica el estado y la leyenda está arriba.
- Con un ancho mínimo de 1040 px, la vista hace scroll horizontal.

### 3. Tablero (Kanban)
- Cuatro columnas: Pendiente, En curso (incluye las bloqueadas), En revisión y Aprobada. Usa una grilla `auto-fit minmax(240px,1fr)`.
- Filtros: chips por área y, para el Analista, el segmentado "Mis tareas / Todo el equipo".
- Cada tarjeta muestra el área (kicker), el título, un tag de Atrasada o Bloqueada si corresponde, el responsable y "Vence Dn". Las marcadas aparecen primero y luego se ordenan por día.

### 4. Detalle de tarea (drawer lateral derecho, 620 px, con backdrop)
- Contenido: kicker con área e id, el título como H2, estado y flag, y una grilla de 2 columnas con Responsable, Revisa y aprueba, Inicio, Fecha límite, Estimado y Referencia Odoo. Luego la descripción, las dependencias (cada una enlaza a su tarea), el checklist, la evidencia (con el botón Adjuntar), los comentarios e historial, y un textarea para comentar.
- Barra de acciones fija abajo, que cambia según el estado y el rol:
  - Pendiente → **Iniciar tarea**.
  - En curso → **Marcar bloqueada** y **Enviar a revisión**. Enviar a revisión se habilita solo con el checklist 100% y al menos 1 evidencia.
  - Bloqueada → **Retomar tarea**.
  - En revisión (solo Jefatura) → **Devolver** y **Aprobar**.
  - Aprobada (solo Jefatura) → **Reabrir**.
- Cada transición agrega una línea al historial. El checklist y los adjuntos solo se pueden editar en curso o bloqueada, y solo por quien puede actuar sobre la tarea.

### 5. Carga del equipo
- Una tabla por persona con: Persona (nombre y cargo), Abiertas ("n de total"), Horas contra capacidad (barra de 6 px y el texto "X h de Y h disponibles · Z%"), Atrasadas y Siguiente tarea (enlace).
- Capacidad = horas diarias × días hábiles que faltan (de hoy a la meta, inclusive). Si la persona está sobre su capacidad, la barra y el texto van en rojo. El H1 nombra a la persona más sobrecargada.

### 6. Vencimientos tributarios
- Cifra grande con los días que faltan para el próximo vencimiento y un H1 de contexto.
- Grupos Noviembre 2026, Diciembre 2026 y Año tributario 2027. Cada fila muestra fecha, obligación y período, responsable, estado (si tiene tarea vinculada, el de la tarea) y "En n días · ver tarea".
- Obligaciones: Previred, LRE (DT), F29, contribuciones de bienes raíces agrícolas, patente municipal, DJ anuales (1887, 1879, 1847, 1926) y F22. **Las fechas deben validarse contra el calendario oficial del SII** y calcularse, no dejarse fijas.

### 7. Reportes y KPIs
- Cuatro KPIs: día hábil de cierre, % de tareas a tiempo, tareas devueltas y días de atraso promedio.
- Gráfico de barras "Día hábil de cierre" de los últimos 6 meses, con una línea discontinua en la meta D8. Las barras sobre la meta van en rojo y el mes estimado en tono claro.
- "Causas de atraso" en barras horizontales y una tabla "Cumplimiento por área" (A tiempo, Devueltas, Atraso promedio). Un área bajo 80% se marca en rojo.

### 8. Plantillas de cierre (solo Jefatura)
- A la izquierda (260 px), la lista de plantillas: Cierre mensual, Cierre trimestral, Cierre anual y renta, y Cierre de temporada de paltas, más el botón "Nueva plantilla".
- A la derecha, el nombre y una nota de la plantilla, y los botones "Agregar tarea" y "Generar cierre…" (en el prototipo solo muestran un toast). Debajo va la tabla Tarea / Área / Día / Responsable (rol) / Evidencia.
- "Generar" crea un Cierre con todas sus tareas, asignadas y con fechas calculadas desde el día hábil.

## Tareas recurrentes incluidas (cierre mensual, 24)
- **Tesorería**: conciliación bancaria Banco de Chile (CLP/USD) y BancoEstado, cotejo Transbank vs. Odoo, rendiciones de fondos del campo, diferencia de cambio de clientes de exportación, conciliación de CxC con cadenas y distribuidores.
- **Tributario**: cotejo Libro de Compras vs. RCV del SII, facturas por recibir (cuenta 2102002), Libro de Ventas y existencias en tránsito, propuesta de F29.
- **Remuneraciones**: centralización por centro de costo, cuadratura Previred, provisión de vacaciones y finiquitos de temporeros.
- **Costos**: inventario de insumos agrícolas, inventario de quesos en maduración, recepción de leche vs. facturas, normalización de costo de Quesería y de Empanadas, prorrateo de costos indirectos.
- **Activo fijo y agrícola**: capitalización de paltos en formación, depreciación, devengo de intereses de créditos y diferencia de cambio.
- **Reportes de gestión**: estado de resultados por área productiva, indicadores para Directorio.

Las dependencias están en la constante `DEPS`. Por ejemplo, el F29 depende de los cotejos de compras y ventas, y el EERR depende del prorrateo, la capitalización y la depreciación.

## Interactions & Behavior
- **Navegación**: SPA sin recarga. Una pantalla que el rol no puede ver redirige al Panel.
- **Abrir tarea**: cualquier fila, tarjeta o barra abre el drawer, que se cierra con el backdrop o con la X. Se recomienda agregar la tecla Esc.
- **Hover**: las filas clicables toman el fondo `accent-100`. Las tarjetas y las barras del Gantt toman `shadow-md`.
- **Toast**: abajo al centro, se cierra solo a los 3,2 s.
- **Foco**: `outline: 2px solid` con el color de acento y `outline-offset: 2px`.
- **Responsive**: está pensado para escritorio (≥1280 px). Las tablas anchas hacen scroll horizontal dentro de su contenedor.

## State Management
- Globales: `role` (del usuario autenticado), `screen` (ruta) y el cierre activo.
- Por tarea: estado, checklist[], evidencias[] y comentarios[].
- UI: `sel` (tarea abierta en el drawer), `draft` (comentario), filtros del tablero (`mine`, `area`), `tpl` (plantilla seleccionada) y `toast`.
- Valores derivados: atrasada, % real vs. % plan, carga por persona, contadores y la lista "Requiere atención".
- Backend: CRUD de tareas, transiciones con auditoría (quién y cuándo), subida de archivos (o vínculo a `ir.attachment` de Odoo), calendario de feriados y generación de cierres desde plantillas.

## Design Tokens (identidad Huentelauquén)
- **Bordó primario** #8C0026: títulos, cifras, botones primarios y barras de avance. Hover y pressed: #74001F / #6E001E.
- **Rojo de marca** #ED0035: kickers y alertas (atrasada/bloqueada), con #C9002D para texto de alerta y #FBD0DA como fondo de barra atrasada.
- **Tintes de bordó**: 100 #FBEFF1, 200 #F2DCDB, 300 #E4B5BF, 400 #C96A80.
- **Texto** #3A3A3A. **Secundario** #6B6B6B. **Divisores y fondos de barra** #E8E8E8. **Superficie de tarjeta** #FAFAFA. **Fondo** #FFFFFF.
- **Tipografía**: títulos y cifras en **Cambria** (fallback Georgia, serif) a 700; cuerpo e interfaz en **Calibri** (fallback Carlito, Segoe UI, sans-serif).
- **Escala**: cifra hero 140 px, H1 según el sistema (~44 px), indicadores 44–48 px, cuerpo 14–15 px, metadatos 12–13 px, kicker 12 px en mayúsculas con tracking .1em.
- **Radios**: 2–4 px. **Sombras**: sm/md/lg suaves (md para hover y lg para el drawer y el toast).
- **Espaciado**: aireado. Las secciones se separan con 48–72 px de espacio en blanco, sin cajas.

## Assets
- Íconos: **Phosphor Icons, peso duotone** (`@phosphor-icons/web@2.1.1`): gauge, calendar-dots, kanban, users-three, stamp, chart-bar, copy, circle-dashed, circle-half, prohibit, eye, check-circle, file-text, paperclip, plus, lightning, arrow-right y x.
- **Logo**: el prototipo usa la marca en texto. En producción va el logo oficial de Hacienda Huentelauquén.
- Los nombres de las personas son ficticios.

## Files
- `Planificacion Contable Huentelauquen.dc.html`: prototipo principal (plantilla y lógica en un solo archivo).
- `Planificacion Contable (Broadsheet).dc.html`: variante con el estilo base.
- `support.js` y `_ds/…`: runtime y estilos base que necesitan los prototipos para abrirse en el navegador. No forman parte de la implementación.
- `screenshots/`: capturas de referencia de cada pantalla (01-panel … 08-plantillas), con el rol Jefatura.
