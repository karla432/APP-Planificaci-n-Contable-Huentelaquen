# 01 · Arquitectura, ADR-001 y plan de construcción

Versión: F1-v1 · 30-10-2026.
Modalidad de revisión: **perspectivas simuladas por un único modelo; la independencia no está garantizada.** Los roles no firman puertas; decide Karla.

## 1. ADR-001 · Stack

**Pregunta decidible.** ¿Qué stack permite tener un checklist seguro, usable por 4 personas el 05-11-2026, desplegable por Eugenio en el servidor OpenCloud y mantenible después?

**Restricciones (Karla).** Parecido a la app de Arqueo de Caja; servidor propio; despliega Eugenio; listo para probar el 03-11-2026.

**Expediente común (evidencia).**
- EVD-1: el Arqueo usa Django, plantillas del servidor, SQLite (modo WAL), gunicorn, nginx y systemd (`despliegue/arqueo.service`, `nginx-arqueo.conf`, `manage.sh`).
- EVD-2: el Arqueo ya resolvió doble factor TOTP, bloqueo por intentos, bitácora con triggers que impiden editar y borrar, respaldos y variables de entorno fuera del repo (`README_DESPLIEGUE.md`). Se revisará el código real en F2 antes de reutilizarlo.
- EVD-3: las maquetas aprobadas usan tarjetas, barras de progreso horizontales y tablas. No usan gráficos que necesiten una librería.
- EVD-4: equipo de 4 colaboradores; volumen aproximado de 186 tareas y de 100 a 200 ocurrencias por mes.

### Fichas iniciales

| Rol | Propuesta | Supuestos | Riesgo principal | Qué cambiaría su conclusión |
|---|---|---|---|---|
| R14 Arquitecto | Django con plantillas del servidor y un poco de JS; capa de servicios separada de las vistas para exponer una API después | 4 a 10 usuarios; la API no se usa en v1 | Acoplar reglas a las vistas | Integración con Odoo o el Arqueo antes de fin de año |
| R22 Operaciones | Mismo esquema de despliegue que el Arqueo; SQLite con WAL y respaldo de archivo | Eugenio ya opera el patrón | Un solo escritor en la base | Más de ~10 usuarios simultáneos |
| R23 Ciberseguridad | PostgreSQL con un rol de aplicación sin `UPDATE`/`DELETE` sobre la bitácora; si no, SQLite con triggers y bitácora sellada | La inmutabilidad se acepta como «evidencia de manipulación» y no como garantía | Quien acceda al archivo de la base puede quitar triggers | Auditoría externa o dato regulado |
| R24 Calidad | Lo que reduzca superficie: Django + pytest-django, como el Arqueo | — | Reglas de calendario mal probadas | Fallo en D7/D10 o feriados |
| R15–R16 UX/UI | Plantillas con CSS propio y tokens de marca; barras CSS; HTMX opcional, servido como archivo local | Pantallas de las maquetas | Rediseño de escritorio de Hoy/Semana/Mes | Más interacción de la prevista |
| R12 Control de gestión | Indicadores calculados en el servidor desde una fuente única (ocurrencias + eventos) | Sin tiempos en v1 | KPI con n pequeño | — |

### Revisión cruzada

| Objeción | Autor → Revisor | Impacto | Respuesta | Estado |
|---|---|---|---|---|
| OBJ-1: SQLite no garantiza inmutabilidad de la bitácora | R22 → R23 | Control antifraude más débil que el exigido en el encargo (§9) | Bitácora con **sello encadenado** y comando de verificación como el Arqueo; el archivo de la base con permisos del usuario del servicio; respaldo diario cifrado fuera del servidor. Riesgo residual documentado (RC-04). | **Aceptada con condiciones**; la dueña la acepta o exige PostgreSQL |
| OBJ-2: sin DRF/OpenAPI no hay API versionada para integrar después | R14 → R24 | Retraso de la integración con Arqueo/Odoo (fuera de alcance v1) | Servicios de dominio aislados; DRF se agrega en v2 | Aceptada: **difiere** |
| OBJ-3: React ofrece más interactividad | R15 → R14 | Costo de construir y de operar un frontend aparte en 4 días | Las maquetas no lo requieren; cada marca es un formulario `POST` | Refutada con EVD-3 |

### Comparación

| Alternativa | Valor | Costo total | Control | Mantenibilidad | Reversibilidad | Evidencia faltante |
|---|---|---|---|---|---|---|
| A. Django + DRF + React + PostgreSQL (propuesta del encargo) | Alto a largo plazo | Alto: dos aplicaciones y un servicio más que operar | Alto | Media: requiere conocer React | Media | No hay quien mantenga el frontend |
| **B. Django monolito con plantillas + SQLite/WAL (como el Arqueo)** | Suficiente para v1 | Bajo | Medio: inmutabilidad por triggers y sello | Alta: mismo patrón que el Arqueo y Eugenio | Alta: el ORM de Django permite migrar a PostgreSQL | Probar el reuso de 2FA y bitácora |
| C. Como B con PostgreSQL 16 | Suficiente | Medio: otro servicio que respaldar y operar | Alto: rol sin `UPDATE`/`DELETE` | Alta | Alta | ¿Eugenio ya opera PostgreSQL en OpenCloud? |

### Posición final por rol

- R14: apoya B, condicionado a la capa de servicios.
- R22: apoya B.
- R23: **apoya C; acepta B condicionado a OBJ-1.** Disenso preservado.
- R24: apoya B.
- R15–R16: apoya B.
- R12: no evaluado (no afecta su definición).

### Decisión recomendada (a validar por Karla en G1)

**Alternativa B.** Django (versión estable vigente en el Arqueo) con plantillas y CSS propio; SQLite con WAL; gunicorn + nginx + systemd; pytest-django.
**Disparadores para pasar a C:** más de 10 usuarios, integración con Odoo o el Arqueo, o una auditoría externa que exija permisos de base por rol.
**Diferido a v2:** DRF/OpenAPI, React, correo, Excel/PDF.
Esto **se aparta de lo propuesto en el encargo** (Django + DRF + React + PostgreSQL 16). Karla delegó la elección y esta es la recomendación, pero el apartamiento queda explícito para que la dueña lo apruebe en G1.

## 2. Arquitectura

```
Navegador ── HTTPS ──> nginx (TLS, estáticos) ──> gunicorn ──> Django
                                                        │
        vistas (solo HTTP, permisos) ──> servicios de dominio ──> modelos ──> SQLite (WAL)
                                        ├─ calendario: días hábiles, feriados confirmados
                                        ├─ recurrencia: reglas → fecha límite
                                        ├─ periodos: abrir/cerrar mes, foto de KPI
                                        ├─ ejecución: hecha / recibida / devuelta / no aplica
                                        ├─ kpi: cumplimiento a tiempo, completitud, revisión
                                        ├─ importador: Excel → vista previa → confirmar
                                        └─ auditoría: bitácora append-only y sellada
```

- **Todo permiso se valida en el servidor**, en la capa de servicios (no solo en la vista). La interfaz esconde botones, pero no es el control.
- **Hora de la marca**: la fija el servidor (`timezone.now()` en UTC). No existe formulario ni campo editable. La fecha de negocio se calcula en `America/Santiago`.
- **Sin modo sin conexión.** Marcar requiere servidor.
- **Sin CDN**: fuentes (Carlito como alternativa métrica de Calibri) y JS se sirven desde el propio servidor, para poder usar CSP estricta.
- Repositorio (propuesta): `config/`, `nucleo/` con `models`, `servicios/`, `vistas/`, `templates/`, `static/`, `pruebas/`, `despliegue/`, `docs/`. Nombres en español como en el Arqueo.

## 3. Plan de construcción hacia el 05-11-2026

**Entra en la v1 (lo mínimo para que 4 personas registren su cumplimiento):**
1. Ingreso con correo y contraseña, bloqueo por intentos, perfiles, **2FA para Gerente y administrador**.
2. Cargos, colaboradores, asignaciones con vigencia, procesos y tareas (alta y edición, sin borrado físico, con historial).
3. Calendario: años, feriados (cargados desde librería, **confirmados por Karla**), jornada por día de la semana.
4. Motor de recurrencia y **Abrir mes** con vista previa e idempotencia (noviembre 2026).
5. Importador del Excel con vista previa y reporte de validación.
6. Pantallas Hoy / Semana / Mes por persona (escritorio primero), con avance de todo el equipo en solo lectura.
7. Hecha / Recibida, revisar, devolver, solicitar y aprobar «no aplica».
8. Panel de la Gerencia: ruta del cierre, avance por proceso, atrasadas, cumplimiento por colaborador con la línea del 95 %.
9. Auditoría sellada, respaldo y restauración probada, guía de despliegue y guía de usuario corta.

**Queda para después del 05-11** (se diseña el modelo, no se construye): tiempos y horas-hombre (DEC-09); carga vs capacidad y riesgo de hito en horas; predecesoras y cuellos de botella; avisos por correo; exportación a Excel y PDF; asistente de apertura anual (el año se abre con el mantenedor); API.

**Calendario (depende de que las puertas se resuelvan a tiempo):**

| Día | Hito | Lo que necesito de ti |
|---|---|---|
| Vie 30-10 | Diseño F1 | **G1** y respuestas P1 a P7 |
| Sáb 31-10 y dom 01-11 | Núcleo, motor y apertura de mes; importador | Revisar feriados cargados de 2026 (se confirman antes de abrir noviembre) |
| Lun 02-11 | Ejecución, revisión y panel | Prueba de pantallas con datos de ejemplo |
| Mar 03-11 | Pruebas, endurecimiento y entrega a staging/OpenCloud | Eugenio disponible; **G2** |
| Mié 04-11 | Carga de personas y tareas reales; capacitación corta | **G3 por escrito** y aprobación de Eugenio |
| Jue 05-11 | Primer día de uso | — |

Riesgos del plan: cualquier puerta que se demore corre todo; el reuso de 2FA y bitácora del Arqueo puede costar más de lo estimado; el servidor aún no está definido (Eugenio). Si el 03-11 no hay pruebas verdes, el 05-11 se usa solo lo que pasó pruebas y se avisa qué queda fuera.

## 4. Pantallas (rediseño de escritorio)

Lenguaje visual de las maquetas: tarjetas con sombra sutil y borde redondeado, sistema de 8 px, rojo `#ED0035` como único acento, estados con texto o ícono además del color.

| Pantalla | Distribución en escritorio | Gráficos y justificación |
|---|---|---|
| **Hoy** | Columna principal con las tareas del día agrupadas (vencen hoy, atrasadas, próximas), cada una con su botón «Hecha» o «Recibida»; columna derecha con avance de hoy y del equipo; selector de persona arriba | Una barra de avance del día. Basta: muestra cuánto falta |
| **Semana** | 5 recuadros (lunes a viernes), uno por día hábil; el feriado aparece explícito, con 0 h y sin tareas | Sin gráficos: es un calendario de tareas |
| **Mes** | Ruta del cierre horizontal (Día 1 a 4, D7, D10) y debajo la tabla de tareas del mes con filtros | Una barra por hito; ya está en la maqueta |
| **Panel Gerencia** | Como `01_panel_gerente.png`: ruta del cierre, 3 indicadores (avance, atrasadas, cumplimiento del equipo), avance por proceso, riesgos de hoy, cumplimiento por colaborador con línea del 95 % | **Solo barras horizontales**, sin donas ni apilados multicolor. La barra con línea de meta responde la pregunta central: «¿quién está bajo el 95 %?». Persona, proceso y tabla quedan enlazados por filtros |
| **Equipo** | Lectura para todos: avance por persona | Barras horizontales |
| **Mantenedores, Calendario, Apertura de mes, Auditoría** | Tablas y formularios sobrios | Sin gráficos |

Pantallas pequeñas: las columnas se apilan; objetivos táctiles ≥ 44 px; contraste AA. No habrá app instalable.

Regla corregida respecto a la maqueta: el contador «faltan N días hábiles para el D10» sale del motor de calendario y descuenta los feriados. El 04-12-2026 serían 3 (lunes 7, miércoles 9 y jueves 10), no 4.

Para G1 apruebas este diseño en texto. Para G2 verás las pantallas reales, con capturas, en staging.
