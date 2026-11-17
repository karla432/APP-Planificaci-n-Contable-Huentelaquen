---
title: "Documentación técnica · Planificación Contable Huentelauquén"
subtitle: "Aplicación Django 6 + SQLite con páginas renderizadas en el servidor"
date: "17-11-2026"
lang: es-CL
---

**Para quién es este documento.** Para quien despliega y mantiene la aplicación en un servidor y para futuros desarrolladores o consultores Odoo-ERP que llegan sin contexto previo. Todo lo que se afirma aquí se verificó contra el código del repositorio (rama `claude/peaceful-ride-ysf0iw`, commit base `9ff4535`) y contra los documentos de `docs/`. Lo que no se pudo confirmar o no se ha probado figura de forma explícita en la sección 13.

**Convenciones.** Los archivos se citan como `ruta/archivo.py` y las funciones por su nombre (sin números de línea, que cambian). Las personas se nombran por su cargo o por los usuarios de ejemplo (`gerente`, `jefa`, `contadora`, `asistente`). «La dueña del producto» es la Gerente de Administración y Finanzas, que aprueba las decisiones; «el administrador del servidor» es quien despliega y opera. Ninguna clave, correo ni dato real vive en el repositorio ni en este documento.

**Qué se ejecutó para escribirlo.** Se corrió la suite completa (726 pruebas, todas pasan, 2 min 15 s), `manage.py check --deploy` con variables de producción de prueba (una sola advertencia, `security.W021`) y varios experimentos desechables sobre una base temporal para confirmar los hallazgos de la sección 13.2. Nada se ejecutó en Windows ni en un servidor real.

# 1. Qué es y qué problema resuelve

## 1.1 Qué es

**Planificación Contable Huentelauquén** es una aplicación web interna del área de Administración y Finanzas de Hacienda Huentelauquén. Planifica, reparte y controla las tareas contables recurrentes del equipo (diarias, semanales, del cierre mensual y por meses específicos) y mide el cumplimiento a tiempo de cada persona.

Se usa desde el navegador en un computador. No hay aplicación móvil, no hay API pública y no hay integración con Odoo ni con otro sistema: los datos entran y salen por Excel.

## 1.2 Problema que resuelve

Antes de la aplicación, el trabajo del cierre contable vivía en un listado Excel de tareas (el «Listado maestro»). Ese formato no dice quién debe hacer qué cada día hábil, no calcula las fechas límite con feriados, no registra cuándo se hizo cada cosa ni permite ver el atraso. La aplicación convierte cada tarea en **ocurrencias** con fecha límite calculada por un calendario de días hábiles de Chile, deja que cada persona registre lo que hizo (con la hora puesta por el servidor), exige revisión por otra persona y calcula el cumplimiento a tiempo con una meta del 95 %.

Objetivo de negocio (de `docs/encargo/PROMPT_CLAUDE_CODE.md`): llegar a los hitos del cierre (reportes listos en el DH08, entrega al Gerente General en el DH09 y al Directorio en el DH10) con cada colaborador sobre la meta de cumplimiento.

## 1.3 Usuarios y roles

| Rol (grupo de Django) | Quién es en la práctica (según el diseño) | Resumen de lo que puede hacer |
|---|---|---|
| `GERENTE` | Gerente AyF | Todo lo funcional; abre meses; gestiona usuarios; segundo factor obligatorio |
| `JEFATURA` | Jefa de Control | Edita procesos y tareas, ve la matriz del cierre, ejecuta y revisa tareas |
| `COLABORADOR` | Personas con los cargos Contador Senior, Analista Contable o Contador (el rol de cada cuenta lo elige quien la crea) | Marca lo suyo; ve el avance de los demás en solo lectura |
| `LECTURA` | Quien se designe | Solo consulta |
| `ADMIN_SISTEMA` | Administrador del servidor | Abre meses y gestiona usuarios; no marca ni revisa tareas; segundo factor obligatorio |

La matriz completa de permisos, verificada contra el código, está en la sección 6.2.

## 1.4 Alcance actual (lo implementado y con pruebas)

- Calendario de días hábiles de Chile con feriados propuestos por una librería y confirmados por una persona (DH00 a DH10, hitos del cierre, jornada).
- Motor de recurrencia con ocho tipos de regla y **Abrir mes**, que genera las ocurrencias del período con vista previa.
- Check List por persona (Mi día, Mi semana, Mi mes) y por cargo; detalle de cada tarea con historial, comentarios y adjuntos.
- Ejecución: marcar hecha, bloquear y retomar, revisar y devolver, marcar «Recibido» (tareas de responsables externos), registrar horas reales y **cambiar quién ejecuta** una tarea.
- Informes: Panel del cierre, Tablero, Cronograma, Cumplimiento por colaborador, Carga del equipo y **Matriz del cierre**.
- Estructura de tres niveles (proceso, tarea, subtarea) con códigos `OO-PPP.TT.SSS`, dependencias entre procesos y árbol/tabla con exportación.
- Mantenedor de Tareas, Procesos y Usuarios; descarga y carga masiva en Excel; descarga del **Plan vigente** y carga de la **Planificación 2.0**.
- Seguridad: claves de 12 o más caracteres, bloqueo por intentos, segundo factor TOTP para Gerente y administrador, bitácora sellada, adjuntos con control de acceso.
- Comandos de operación: crear usuarios, recuperar acceso, respaldar, verificar respaldo y bitácora, cargar el plan, configurar la gracia de arranque.
- Kit de despliegue en `deploy/` (sin probar en un servidor real).

## 1.5 Fuera de alcance o no implementado

Estos puntos figuran en los documentos de diseño (`docs/f1/`) pero **no existen en el código**:

- Cierre de período con foto inmutable de los KPI y reapertura con motivo (el campo `Periodo.kpi_foto` existe y ningún código lo usa).
- Pantalla de Auditoría (la bitácora se escribe y se verifica por comando, pero no hay pantalla para leerla).
- Pantallas de Parámetros y de Cargos (los parámetros se cambian con comandos o en el shell de Django; los cargos nacen del Excel o de migraciones).
- Pantallas para **solicitar y aprobar «no aplica»** y para la **marca por excepción** del Gerente: las funciones existen en `nucleo/servicios/ejecucion.py` y tienen pruebas, pero ninguna vista ni ruta las llama.
- Envío de correo, API REST, integración con Odoo o con el Arqueo de Caja, exportación a PDF.
- Una forma de crear ocurrencias «por evento» a mano (las tareas de regla `EVENTO` no generan nada).

## 1.6 Estado a la fecha

| Dato | Valor |
|---|---|
| Fecha del documento | 17-11-2026 |
| Pruebas automáticas | 726, todas pasan (ver sección 9) |
| Producción | **No aprobada ni hecha.** Exige la aprobación escrita de la dueña del producto (puerta G3) y del administrador del servidor, y la lista de aceptación de `docs/f1/08_guia_de_despliegue.md` (sección 7) con evidencia |
| Datos reales | Ninguno cargado en ningún servidor. Los datos de trabajo son de ejemplo |
| Fecha de comienzo de la medición acordada | 01-11-2026, con gracia de arranque hasta el 22-11-2026 (sección 4.4) |

# 2. Arquitectura y stack

## 2.1 Stack y versiones

Versiones exactas de `requirements.lock.txt` (es lo que debe instalar el servidor):

| Paquete | Versión | Para qué |
|---|---|---|
| Django | 6.1.1 | Framework web, ORM, autenticación, migraciones |
| gunicorn | 26.2.0 | Servidor de aplicación WSGI en producción |
| holidays | 0.107 | Propuesta de feriados de Chile (`holidays.country_holidays("CL")`) |
| openpyxl | 3.1.5 | Lectura y escritura de Excel (`.xlsx`) |
| PyOTP | 2.10.0 | Segundo factor TOTP (RFC 6238) |
| pytest | 9.2.0 | Pruebas |
| pytest-django | 4.14.0 | Integración de pytest con Django |
| tzdata | 2026.6 | Base de zonas horarias (necesaria en Windows) |

Notas de verificación:

- `requirements.txt` (sin versiones, lo usa `iniciar_local.bat`) agrega `qrcode`, que **no** está en `requirements.lock.txt`. Sin esa librería el segundo factor funciona, pero la pantalla no muestra el código QR y la clave se escribe a mano (`nucleo/servicios/segundo_factor.py`, función `qr_svg`).
- La suite se corrió con Python 3.13.17 (el del entorno virtual `.venv`). El repositorio no fija la versión de Python; Django 6.1 exige Python 3.12 o superior.
- Base de datos: SQLite con modo WAL, `transaction_mode IMMEDIATE`, `timeout 20` y `PRAGMA foreign_keys=ON` (`config/settings.py`, clave `DATABASES`). No se usa PostgreSQL.
- Interfaz: plantillas de Django y un CSS propio (`nucleo/static/nucleo/app.css`, 180 líneas). Sin JavaScript de terceros ni CDN.
- No hay `.env` ni `python-dotenv`: la configuración se lee de variables de entorno del proceso (en producción, `EnvironmentFile=` de systemd).

## 2.2 Arquitectura

```text
Navegador ──HTTPS──> nginx (TLS, /static/, límite 12 MB) ──> gunicorn (2 procesos) ──> Django

Dentro de Django, cada solicitud pasa por:

  Middleware: Security → Session → Common → Csrf → Authentication
              → SegundoFactorMiddleware → Messages → XFrameOptions
        │
        ▼
  nucleo/urls.py ──> vistas (nucleo/views*.py)       solo HTTP, rol y formularios
        │
        ▼
  nucleo/servicios/*.py                               reglas de negocio y permisos
        │
        ▼
  nucleo/models.py ──> SQLite (WAL)                   + carpeta de adjuntos (evidencias/)
```

Reglas de la arquitectura (confirmadas en el código):

1. **Las vistas no contienen reglas de negocio.** Reciben la solicitud, comprueban el rol cuando corresponde y llaman a un servicio.
2. **Los permisos de negocio se validan en los servicios**, no solo en la interfaz: `ejecucion.py`, `mantenedor.py`, `estructura.py`, `excel_masivo.py` y `evidencias.py` lanzan `PermisoDenegado` o `ErrorDeNegocio` (`nucleo/servicios/errores.py`). Excepciones: `periodos.py` y `feriados.py` (Abrir mes) no revisan rol; el control está solo en el decorador `con_roles` de `nucleo/views_apertura.py`.
3. **Cómo se muestran los errores.** `ErrorDeNegocio` se convierte en un mensaje en pantalla (`messages.error`); `PermisoDenegado` en una respuesta 403 (`prohibido.html` en el Mantenedor, texto plano en `ocurrencia_accion`).
4. **La hora de una marca la fija el servidor** (`timezone.now()`); ninguna función acepta una hora desde el formulario.
5. **No hay borrado físico.** Se desactiva (`activo` o `activa`). Las claves foráneas importantes son `PROTECT`.
6. **Todo cambio relevante queda en la bitácora sellada** (`nucleo/servicios/auditoria.py`, función `registrar`).

## 2.3 Estructura de carpetas

### Raíz del repositorio

| Archivo o carpeta | Para qué sirve |
|---|---|
| `manage.py`, `config/` | Punto de entrada de Django y configuración (ver abajo) |
| `nucleo/` | Única aplicación Django: modelos, vistas, servicios, plantillas |
| `pruebas/` | Suite de pruebas (pytest) |
| `deploy/` | Kit de despliegue en el servidor (sin probar en un servidor real) |
| `docs/` | Documentación, decisiones, datos de entrada y maquetas |
| `requirements.txt`, `requirements.lock.txt` | Dependencias sin fijar (desarrollo) y fijadas (servidor) |
| `pytest.ini`, `conftest.py` | Configuración de pruebas (`DJANGO_SETTINGS_MODULE=config.settings`, `testpaths=pruebas`; `conftest.py` fija entorno de desarrollo y un hash de claves rápido solo para pruebas) |
| `iniciar_local.bat`, `iniciar_local.sh`, `levantar_local.py`, `cambiar_clave.bat`, `LEEME.txt` | Puesta en marcha local con datos de ejemplo (sección 8.6) |
| `CLAUDE.md` | Método de trabajo con la dueña del producto |
| `README.md` | Resumen del proyecto (su tabla de estado quedó atrasada; ver 13.2) |
| `.env.example` | Ejemplo de variables de producción (sin valores) |
| `paginas.json`, `.vista_previa/`, `.claude/launch.json` | Material auxiliar de vista previa y lanzador del entorno de escritorio; la aplicación no los usa |
| `.entorno_desarrollo`, `.clave_secreta_local`, `db.sqlite3`, `db_local.sqlite3`, `evidencias/`, `staticfiles/` | Archivos locales. Están en `.gitignore` y no deben llegar al servidor por el repositorio |

### `config/`

| Archivo | Para qué sirve |
|---|---|
| `settings.py` | Toda la configuración: entorno, secretos, hosts, cookies y cabeceras, base de datos, validadores de clave, rutas de adjuntos y estáticos |
| `entorno.py` | `resolver_entorno` (desarrollo o producción) y `acceso_rapido_permitido` (modo sin clave; falla cerrada en producción) |
| `urls.py` | Monta `/admin/` y las rutas de `nucleo.urls` |
| `wsgi.py` | Punto de entrada de gunicorn (`config.wsgi:application`) |

### `nucleo/` (módulos de primer nivel)

| Módulo | Para qué sirve |
|---|---|
| `models.py` | Todas las entidades (sección 3) |
| `permisos.py` | Roles (`ROLES`, `QUE_MARCAN`), `rol_de`, `colaborador_de`, `cargos_vigentes_de` |
| `autenticacion.py` | `RespaldoConBloqueo` (backend que niega el ingreso a cuentas bloqueadas) y `FormularioDeIngreso` |
| `bloqueo_acceso.py` | Bloqueo de 15 minutos tras 5 fallos; usa la tabla `IntentoFallido` |
| `segundo_factor_middleware.py` | Falla cerrada: sin código de segundo factor no se ve nada |
| `senales.py` | Registra inicio y cierre de sesión y cuenta fallos de ingreso (se activa en `apps.py`) |
| `contexto.py` | Variables de plantilla: modo de prueba y qué ve cada rol en el menú |
| `siglas.py` | Siglas de tres letras de los procesos y catálogo base de 11 procesos |
| `urls.py` | Todas las rutas de la aplicación (sección 10) |
| `views.py` | Check List (Mi día, semana, mes), detalle, acciones sobre ocurrencias, adjuntos, acceso rápido |
| `views_informes.py` | Panel, cumplimiento, carga, tablero, cronograma y matriz del cierre |
| `views_apertura.py` | Abrir mes (feriados, año, vista previa, apertura) |
| `views_mantenedor.py` | Mantenedor de Tareas, Procesos y Usuarios; descargas y cargas de Excel; decorador `con_roles` |
| `views_planificacion.py` | Árbol y tabla de la estructura de tres niveles, con exportación |
| `views_checklist_cargos.py` | Check List por cargo y responsable |
| `views_cuenta.py` | Pantalla del segundo factor y aviso de clave cambiada |

### `nucleo/servicios/` (la lógica de negocio)

| Módulo | Qué contiene |
|---|---|
| `calendario.py` | `Calendario` (días hábiles), `JORNADA_HORAS`, `hitos_de_entrega` (DH08 a DH10), `ventana_del_cierre` |
| `recurrencia.py` | `Regla`, `TIPOS`, `fechas_limite` (regla + mes → fechas) |
| `feriados.py` | Propuesta desde la librería, confirmación, alta manual, apertura de año, `calendario_confirmado` |
| `periodos.py` | `vista_previa` y `abrir_mes` (generan las ocurrencias) |
| `gracia.py` | Gracia de arranque (`vence_el_para`, `configurar`) |
| `ejecucion.py` | Marcar, bloquear, revisar, devolver, recibir, reasignar, horas reales, comentar, historial |
| `kpi.py` | Cumplimiento a tiempo, semáforo, revisión, insumos de externos, ruta y avance del cierre |
| `agenda.py` | Qué debe hacer cada persona (atrasado, hoy, próximo, por registrar), semana, mes y «requiere atención» |
| `carga.py` | Carga estimada por cargo, carga del cierre por día y horas reales contra estimadas |
| `matriz.py` | Matriz del cierre: horas por cargo y día contra jornada y techo; propuesta de equilibrio opcional |
| `parametros.py` | Parámetros con valor inicial y estado «confirmado» o «pendiente de confirmar» |
| `importador.py` | Lectura del Excel, conversión de «Periodicidad + Cuándo» en regla, vista previa y aplicación |
| `plan2.py` | Lectura de la Planificación 2.0 y del Excel «Plan vigente»; emparejamiento con las tareas existentes |
| `plan_vigente.py` | Exportación del Excel «Plan vigente» |
| `excel_masivo.py` | Descargas y cargas de Excel (tareas, procesos, planificación, matriz), validación de archivos y archivo en espera |
| `mantenedor.py` | Crear y editar tareas, procesos y usuarios |
| `estructura.py` | Procesos y tareas de nivel 2, orden, dependencias, etapas, catálogo base |
| `codigos.py` | Generación y cascada de códigos `OO-PPP.TT.SSS`, historial de códigos |
| `vista_planificacion.py` | Árbol y tabla con filtros |
| `evidencias.py` | Validación, almacenamiento y permiso de los adjuntos |
| `segundo_factor.py` | TOTP: alta, verificación, reinicio, QR |
| `auditoria.py` | Bitácora con sello encadenado y verificación de la cadena |
| `reglas_texto.py` | La periodicidad en palabras |
| `presentacion.py` | Textos y clases del semáforo |
| `reloj.py` | «Hoy» en la zona de negocio; permite fijar la fecha solo en desarrollo |
| `errores.py` | `ErrorDeNegocio` y `PermisoDenegado` |

### `nucleo/management/commands/`

`crear_usuario`, `recuperar_acceso`, `respaldar`, `verificar_respaldo`, `verificar_bitacora`, `cargar_plan`, `configurar_gracia`, `datos_de_ejemplo`, `cargar_ejemplo_planificacion`. Detalle y ejemplos en la sección 8.

### `nucleo/templates/nucleo/` (37 plantillas) y `nucleo/static/nucleo/`

| Grupo | Plantillas |
|---|---|
| Estructura común | `base.html` (diseño y menú lateral), parciales `_estado.html`, `_fila.html`, `_listado_tareas.html`, `_cumplimiento_tabla.html`, `_selector_mes.html`, `_plan_campos.html` |
| Ingreso y cuenta | `login.html`, `acceso_rapido.html`, `segundo_factor.html`, `cambiar_clave.html`, `prohibido.html`, `sin_perfil.html` |
| Check List | `checklist_base.html`, `hoy.html`, `semana.html`, `mes.html`, `checklist_cargos.html`, `detalle.html` |
| Informes | `informe_panel.html`, `informe_tablero.html`, `informe_cronograma.html`, `informe_cumplimiento.html`, `informe_carga.html`, `informe_matriz_plan.html` (plan vigente), `informe_matriz.html` (propuesta) |
| Planificación y cierre | `planificacion.html`, `abrir_mes.html` |
| Mantenedor | `mant_tareas.html`, `mant_tarea_form.html`, `mant_tareas_cargar.html`, `mant_procesos.html`, `mant_proceso_detalle.html`, `mant_usuarios.html`, `mant_usuario_form.html` |
| Sin uso | `en_construccion.html` (ninguna ruta la usa) |

`nucleo/static/nucleo/app.css` es la única hoja de estilos.

### `deploy/`

| Archivo | Para qué sirve |
|---|---|
| `planificacion.service` | Unidad systemd: gunicorn en `127.0.0.1:8010`, 2 procesos, usuario `planificacion`, endurecida |
| `nginx-planificacion.conf` | Proxy inverso con TLS (certbot), `/static/` y límite de subida de 12 MB |
| `planificacion.env.example` | Variables de entorno de producción (copiar a `/etc/planificacion/planificacion.env`) |
| `manage.sh` | Ejecuta `manage.py` con el entorno de producción y como el usuario del servicio |
| `actualizar.sh` | Actualización: respaldo, código, dependencias, migraciones, estáticos, reinicio y revisión |
| `respaldo_diario.sh` | Respaldo diario y prueba de restauración mensual (el cifrado y la copia externa quedan por completar) |

Detalle de qué hace cada uno en la sección 8.5.

### `pruebas/` y `docs/`

`pruebas/` tiene 38 archivos `test_*.py` más `ayudas.py` (fábricas de datos sin personas reales); el mapa está en la sección 9.

| Carpeta o archivo de `docs/` | Contenido |
|---|---|
| `TRASPASO.md` | Estado, pendientes y reglas vigentes para una sesión nueva |
| `etapas.md` | Etapas del proyecto y cómo ver la web local |
| `f1/00_decisiones_y_gates.md` | Decisiones DEC-01 a DEC-43, supuestos y puertas |
| `f1/01_arquitectura_adr.md` | Decisión de stack (ADR-001) y plan inicial |
| `f1/02_modelo_datos_recurrencia.md` | Modelo de datos y motor de recurrencia del diseño inicial (hoy hay diferencias; ver 13.2) |
| `f1/03_kpi_roles_sod.md` | Definición de KPI, roles y segregación de funciones (diseño; ver 6.2) |
| `f1/04_seguridad_riesgos_pruebas.md` | Amenazas, riesgos y plan de pruebas |
| `f1/05_despliegue_respaldo.md` | Plan de despliegue y respaldo |
| `f1/06_estructura_y_codigos.md` | Estructura de tres niveles y códigos |
| `f1/07_planificacion_2_0.md` | Cómo se carga y qué cambia con la Planificación 2.0 |
| `f1/08_guia_de_despliegue.md` | Guía operativa para quien despliega |
| `datos/` | Excel de entrada: Planificación 2.0, versión revisada anterior y listado maestro original |
| `diseno/`, `marca/`, `encargo/` | Maquetas aprobadas, logo y encargo original |

## 2.4 Dependencias entre servicios

Lectura rápida de qué módulo de servicios usa a cuál (solo las dependencias que importan para entender el flujo):

| Servicio | Se apoya en |
|---|---|
| `recurrencia` | `calendario` |
| `feriados` | `calendario`, `auditoria` |
| `gracia` | `parametros`, `auditoria` |
| `periodos` | `recurrencia`, `feriados`, `calendario`, `gracia`, `auditoria` |
| `kpi` | `calendario`, `feriados`, `parametros` |
| `agenda` | `kpi`, `gracia`, `feriados`, `permisos` |
| `carga` | `kpi`, `recurrencia`, `feriados`, `parametros` |
| `matriz` | `kpi`, `carga`, `recurrencia`, `feriados`, `calendario`, `parametros` |
| `ejecucion` | `permisos`, `evidencias`, `auditoria` |
| `importador` | `recurrencia`, `calendario`, `estructura`, `siglas`, `auditoria` |
| `plan2` | `importador`, `siglas` |
| `excel_masivo` | `importador`, `estructura`, `mantenedor`, `matriz`, `auditoria` |
| `plan_vigente` | `excel_masivo`, `matriz` |

## 2.5 Zona horaria y fechas

- `TIME_ZONE = "America/Santiago"` y `USE_TZ = True`: los instantes (`primera_hecha_en`, `hecha_en`, momentos de bitácora) se guardan en UTC.
- Las fechas de negocio (`fecha_limite`, `vence_el`, feriados) son `DateField` sin hora.
- «Hoy» se obtiene siempre de `nucleo/servicios/reloj.py` (`hoy`). En desarrollo se puede fijar con `PLANIFICACION_HOY`; en producción esa variable se ignora.
- El KPI «a tiempo» compara el **día local** de la primera marca con la fecha exigible (`kpi._dia_local`), de modo que una marca a las 23:30 hora de Chile cuenta como de ese día.
- Una excepción menor: `crear_usuario` usa `date.today()` (reloj del sistema) y no `reloj.hoy()`.

# 3. Modelo de datos

Todo el modelo vive en `nucleo/models.py`. El diseño inicial (`docs/f1/02_modelo_datos_recurrencia.md`) cambió durante la construcción: lo que sigue describe el código actual.

## 3.1 Diagrama de relaciones

```text
auth.User ──1:1── Colaborador ──1:N── Asignacion ──N:1── Cargo
   │                    │                                  │ ▲ ▲ ▲
   │ (auth.Group =      │                                  │ │ │ └─ Tarea.cargo_cierre, cargo_revisa_cierre
   │  rol de la app)    │                                  │ │ └─── Tarea.cargo_revisa
   │                    │                                  │ └───── Tarea.cargo_ejecuta (y Ocurrencia.cargo_ejecuta/cargo_revisa)
   │                    │
   ├─1:1── SegundoFactor
   │
Proceso ──1:N── TareaPrincipal ──1:N── Tarea  (la «subtarea»)
   │                                     │ ├─ N:M ── Tarea         (predecesoras)
   │ N:M DependenciaProceso              │ │
   │ (proceso depende_de proceso)        │ └─1:N── Ocurrencia ──N:1── Periodo
   │                                     │              │ ├─ N:1 Colaborador (quién la hace)
 CambioDeCodigo (historial)              │              │ ├─ 1:N Evidencia ──N:1── EventoAuditoria
                                         │              │ └─ 1:N SolicitudNoAplica
Anio   Feriado   Parametro   IntentoFallido   EventoAuditoria   (tablas independientes)
```

## 3.2 Entidades principales

### Personas y cargos

| Entidad | Campos clave | Notas |
|---|---|---|
| `Cargo` | `nombre` (único), `es_externo`, `activo`, `horas_mes_max`, `orden` | Cargos internos: Gerente AyF, Jefa de Control, Contador Senior, Analista Contable y Contador. Los externos no tienen cuenta ni capacidad. `horas_mes_max` vale 80 para el Gerente AyF |
| `Colaborador` | `usuario` (1:1 con `auth.User`, opcional), `nombre`, `correo`, `activo` | Solo nombre, correo y cuenta |
| `Asignacion` | `cargo`, `colaborador`, `desde`, `hasta` | Vigencia: un cargo lo ejerce una persona en un rango de fechas (subrogancias y reemplazos). `hasta` vacío = vigente |

### Estructura de la planificación (tres niveles)

| Entidad | Campos clave | Notas |
|---|---|---|
| `Proceso` (nivel 1) | `nombre` (único), `orden` (único), `sigla` (3 letras, única), `codigo` (`OO-PPP`), `activo`, `responsable` | `save()` genera el código y, si cambia, actualiza en cascada tareas y subtareas (`codigos.al_cambiar_el_codigo_del_proceso`) |
| `TareaPrincipal` (nivel 2) | `proceso`, `nombre`, `numero` (TT), `codigo` (`OO-PPP.TT`), `activa`, `responsable` | Única por (proceso, número) y por (proceso, nombre). Máximo 99 por proceso |
| `Tarea` (nivel 3, la «subtarea») | `codigo` (`OO-PPP.TT.SSS`), `padre`, `numero` (SSS), `clave_estable`, `proceso`, `tarea_principal`, `subtarea`, `cargo_ejecuta`, `cargo_revisa`, campos `regla_*`, horas, modo del cierre, predecesoras | Es la unidad que se ejecuta cada mes. Ver el detalle abajo |
| `DependenciaProceso` | `proceso`, `depende_de` | Sin autodependencia y sin ciclos; solo hacia un proceso que va antes en el orden (se valida en `estructura.fijar_dependencias`) |
| `CambioDeCodigo` | `nivel`, `objeto_id`, `codigo_anterior`, `codigo_nuevo`, `motivo`, `usuario` | Un código anterior sigue siendo buscable |

Los tres niveles heredan de la clase abstracta `Planificable`: `estado_plan`, `fecha_inicio`, `fecha_termino` y `observaciones`. Una restricción de base de datos exige que la fecha de término no sea anterior a la de inicio. Estos campos son de planificación y **no** reemplazan el estado de cada ocurrencia, que es la fuente del KPI.

**Campos de `Tarea` por tema:**

| Tema | Campos |
|---|---|
| Identidad | `codigo` (único), `clave_estable` (SHA-256 de proceso, tarea y subtarea normalizados; reconoce la misma tarea al volver a cargar un Excel), `secuencia` (orden de procesamiento) |
| Responsables | `cargo_ejecuta`, `cargo_revisa` (puede ser vacío), `revisa_excel` (lo que decía la columna «Revisa»), `cargo_cierre`, `cargo_revisa_cierre` |
| Regla de recurrencia | `regla_tipo`, `regla_dia_semana`, `regla_n`, `regla_dia`, `regla_meses` (texto con meses separados por coma), `regla_ajuste` (`siguiente` o `anterior`), `regla_franja` (mañana o tarde, informativa), `regla_estado` (confirmado o pendiente), `periodicidad_excel`, `cuando_excel`, `referencia_normativa` |
| Horas | `minutos_estimados` (por ejecución), `minutos_revision`, `ejecuciones_mes`, `fuente_horas` (estimación, gerente, estimada, ajustada) |
| Semanas del cierre (Planificación 2.0) | `modo_cierre` (`igual`, `reasignar`, `pausar`, `fuera`), `al_terminar_cierre`, `dh_inicio`, `horas_dh` (JSON, horas por día hábil), `horas_semana` (JSON, horas por día de la semana, 0 = lunes) |
| Control | `tipo_control`, `cambio_plan`, `justificacion`, `predecesoras` (relación consigo misma), `requiere_revision`, `motivo_revision`, `activa`, `dia_cierre` |

La regla de recurrencia está **aplanada** en la propia `Tarea`: una regla por tarea. El método `Tarea.regla()` la entrega como el objeto `Regla` que consume el motor.

### Calendario y períodos

| Entidad | Campos clave | Notas |
|---|---|---|
| `Anio` | `anio` (único), `estado` (`borrador`, `abierto`, `cerrado`) | Un año debe estar `abierto` para abrir sus meses. Ningún código pone `cerrado` |
| `Feriado` | `fecha` (única), `nombre`, `tipo`, `origen`, `confirmado`, `confirmado_por`, `confirmado_en` | Solo los confirmados cuentan en el calendario |
| `Periodo` | `anio`, `mes` (únicos juntos), `estado` (`abierto`, `cerrado`), `inicio_medicion`, `kpi_foto`, `cerrado_por`, `cerrado_en` | El período M reúne las diarias y semanales del mes M y el cierre del mes M−1, que vence en los primeros días hábiles de M |
| `Parametro` | `clave` (única), `valor`, `estado_dato`, `nota` | Ver 4.12 |

### Ejecución

| Entidad | Campos clave | Notas |
|---|---|---|
| `Ocurrencia` | `tarea`, `periodo`, `fecha_limite`, `vence_el`, `cargo_ejecuta`, `colaborador`, `cargo_revisa`, `regla_copia` (JSON), `estado`, `tipo_marca`, `primera_hecha_en`, `hecha_en`, `hecha_por`, `revisada_en`, `revisada_por`, `primera_revision_en`, `veces_devuelta`, `comentario_devolucion`, `por_excepcion`, `motivo_excepcion`, `minutos_reales`, `minutos_estimados`, `motivo_bloqueo` | Única por (tarea, período, `fecha_limite`). Copia el responsable, el revisor y la regla vigentes al generarse: los cambios posteriores no reescriben el pasado. `vence_el` es la fecha desde la cual cuenta como atrasada (`Ocurrencia.exigible`) |
| `Evidencia` | `ocurrencia`, `evento`, `ruta`, `nombre_original`, `extension`, `tipo_contenido`, `tamano`, `sha256`, `subido_por` | El archivo vive en `EVIDENCIAS_ROOT`, con nombre aleatorio |
| `SolicitudNoAplica` | `ocurrencia`, `motivo`, `solicitante`, `estado`, `resuelta_por` | Existe el modelo y el servicio; no hay pantalla |

### Seguridad y auditoría

| Entidad | Campos clave | Notas |
|---|---|---|
| `EventoAuditoria` | `momento`, `usuario`, `usuario_texto`, `accion`, `entidad`, `entidad_id`, `antes`, `despues`, `motivo`, `sello_anterior`, `sello` | Solo se agrega. Triggers de SQLite impiden `UPDATE` y `DELETE` (migración `0002_auditoria_inmutable`) |
| `IntentoFallido` | `nombre`, `momento`, `origen` | Alimenta el bloqueo temporal. Un intento fallido de segundo factor se guarda con el nombre `2fa:usuario` |
| `SegundoFactor` | `usuario` (1:1), `secreto`, `confirmado`, `visible_en_pantalla`, `ultimo_paso` | El secreto está en la base (ver 6.4) |

Los roles son los cinco grupos de Django (`auth.Group`) que crea la migración `0005_roles`. Ser superusuario o `is_staff` **no** otorga ningún permiso de la aplicación (`nucleo/permisos.py`).

## 3.3 Códigos jerárquicos

| Nivel | Código | Ejemplo | Quién lo genera |
|---|---|---|---|
| Proceso | `OO-PPP` | `02-VEN` | `Proceso.save`: `OO` es el orden de ejecución (campo aparte) y `PPP` la sigla |
| Tarea | `OO-PPP.TT` | `02-VEN.01` | `TareaPrincipal.save`: correlativo dentro del proceso |
| Subtarea | `OO-PPP.TT.SSS` | `02-VEN.01.003` | `Tarea.save` → `codigos.preparar_subtarea`: correlativo dentro de la tarea |

Los códigos nunca los escribe una persona. Si cambia el orden o la sigla de un proceso, el prefijo de todo su árbol se reescribe en la misma transacción y el código anterior queda en `CambioDeCodigo`. Límites: 99 procesos, 99 tareas por proceso y 999 subtareas por tarea. Un código que no tiene esta forma (por ejemplo, los de las pruebas) no se toca (`codigos.es_jerarquico`).

## 3.4 Estados de una ocurrencia y transiciones

Estados (`Ocurrencia.ESTADOS`): `pendiente`, `hecha`, `revisada`, `devuelta`, `no_aplica`, `bloqueada`. El tipo de marca (`tipo_marca`) es `HECHA` o `RECIBIDA` (tareas de responsables externos).

```text
                     marcar_hecha / marcar_recibida
   pendiente ────────────────────────────────────────► hecha ──── revisar ────► revisada (final)
      │  ▲                                               │
      │  │ retomar                                       │ devolver (con comentario)
      │  │                                               ▼
      │  └────────── bloqueada ◄── bloquear ──────── devuelta
      │                  ▲                                │
      └── bloquear ──────┘                                └── marcar_hecha ──► hecha

   Solo servicio, sin pantalla:   pendiente o devuelta ──► no_aplica   (solicitud y resolución)
                                  pendiente o devuelta ──► hecha       (marca por excepción del Gerente)
   Tareas RECIBIDA (externos):    las marca quien recibe; pasan a «hecha» y no se revisan
```

| Transición | Función (`nucleo/servicios/ejecucion.py`) | Quién | Condiciones |
|---|---|---|---|
| pendiente o devuelta → hecha | `marcar_hecha` | Quien ejecuta la tarea (rol `COLABORADOR`, `JEFATURA` o `GERENTE` y `colaborador` igual al de la ocurrencia) | No es `RECIBIDA`; período abierto. Fija `primera_hecha_en` una sola vez (base del KPI) |
| pendiente o devuelta → hecha («recibida») | `marcar_recibida` | Quien tiene el cargo revisor (en la práctica, la Jefa de Control) | Solo tareas `RECIBIDA` |
| pendiente o devuelta → hecha (por excepción) | `marcar_por_excepcion` | Rol `GERENTE`, con motivo | **Sin pantalla**; solo servicio y pruebas |
| pendiente o devuelta → bloqueada | `marcar_bloqueada` | Quien ejecuta | Exige motivo |
| bloqueada → pendiente | `retomar` | Quien ejecuta | |
| hecha → revisada | `revisar` | Quien ejerce el cargo revisor | No puede revisar lo que marcó él mismo (`hecha_por`); no es `RECIBIDA` |
| hecha → devuelta | `devolver` | Igual que revisar | Exige comentario; suma `veces_devuelta` |
| pendiente o devuelta → no_aplica | `solicitar_no_aplica` y `resolver_no_aplica` | Quien ejecuta pide; el Gerente o el revisor (Jefatura) resuelve, nunca quien pidió | **Sin pantalla** |
| (sin cambio de estado) cambiar quién ejecuta | `reasignar` | Cualquier persona del equipo con cuenta y cargo | Estado pendiente, devuelta o bloqueada; ver 4.8 |
| (sin cambio de estado) horas reales | `registrar_horas` | Quien ejecuta | Tarea no `RECIBIDA` ni `no_aplica` |

Un período cerrado bloquea todo (`_exigir_periodo_abierto`), pero **ningún código cierra períodos** (ver 1.5). Una ocurrencia `revisada` es final: no hay transición que salga de ese estado.

## 3.5 Restricciones de integridad

- `Ocurrencia`: restricción única (`tarea`, `periodo`, `fecha_limite`); es lo que hace idempotente a Abrir mes.
- `Proceso.orden`, `Proceso.sigla`, `Proceso.codigo`, `TareaPrincipal.codigo`, `Tarea.codigo` y `Tarea.clave_estable` son únicos.
- Las claves foráneas a cargos, procesos, tareas, ocurrencias y usuarios son `PROTECT`: no se puede borrar algo que tiene historia. Las excepciones son `DependenciaProceso` y `SegundoFactor`, que usan `CASCADE`.
- Bitácora: los dos triggers de SQLite abortan cualquier `UPDATE` o `DELETE` de `nucleo_eventoauditoria`.

## 3.6 Migraciones

| Migración | Qué hace |
|---|---|
| `0001_modelo_inicial` | Modelo base |
| `0002_auditoria_inmutable` | Triggers que impiden modificar o borrar la bitácora |
| `0003_kpi_revision_devoluciones` | Campos de revisión y devoluciones |
| `0004_intentos_fallidos` | Tabla del bloqueo por intentos |
| `0005_roles` | Crea los cinco grupos de rol |
| `0006_orden_de_cargos`, `0007_cargos_ordenados`, `0009_nombres_de_cargos` | Orden y nombres de los cargos |
| `0008_planificacion_horas_orden_bloqueada` | Planificación, horas y estado «bloqueada» |
| `0010_orden_y_codigo_de_procesos`, `0011_tres_niveles_y_codigos` | Orden, siglas y estructura de tres niveles |
| `0012_hitos_del_mes_dedicacion_y_semana_del_cierre` | Hitos, dedicación del Gerente y semana del cierre |
| `0013_evidencias` | Adjuntos |
| `0014_calendario_2027_2028` | Carga feriados confirmados y abre los años 2027 y 2028 (el 2026 **no** se carga aquí) |
| `0015_minutos_revision`, `0017_texto_minutos_revision` | Minutos de revisión por tarea |
| `0016_plan_2_0` | Campos de la Planificación 2.0; renombra «Asistente Contable» a «Analista Contable» |
| `0018_segundo_factor` | Tabla del segundo factor |
| `0019_gracia_de_arranque` | `Ocurrencia.vence_el` y el cargo «Contador» |

Las migraciones `0002`, `0005`, `0007`, `0009`, `0010`, `0011`, `0012`, `0014`, `0016` y `0019` ejecutan `RunPython` o `RunSQL` (escriben datos o triggers además de estructura); la mayoría no es reversible en la práctica (`RunPython.noop`). Tenerlo presente al revertir.

# 4. Reglas de negocio implementadas

Esta sección describe cada regla y dice **dónde vive** (archivo y función). Al final (4.13) hay un índice resumido.

## 4.1 Calendario de días hábiles, DH00 a DH10, hitos y jornada

Archivos: `nucleo/servicios/calendario.py` (lógica pura, sin base de datos) y `nucleo/servicios/feriados.py` (feriados).

| Concepto | Definición | Dónde |
|---|---|---|
| Día hábil | Lunes a viernes que no sea un feriado **confirmado** | `Calendario.es_habil` |
| DHnn | El n-ésimo día hábil del mes (`DH01` es el primero) | `Calendario.dia_habil_n` |
| DH00 | El último día hábil del mes anterior | `Calendario.dia_habil_n` con `n = 0` |
| Hitos del cierre | DH08 = análisis y reportes listos (en la tarde); DH09 = entrega al Gerente General; DH10 = entrega al Directorio. Son **días hábiles** (decisión DEC-35) | `hitos_de_entrega` |
| Semanas del cierre | Del DH01 al DH10 | `ventana_del_cierre` |
| Jornada | Lunes a jueves 9 h y viernes 5 h (41 h semanales) | `JORNADA_HORAS` |
| Tope del Gerente AyF | 80 h al mes para Huentelauquén | `Cargo.horas_mes_max` |

Ejemplo de noviembre de 2026 (sin feriados en la semana): DH01 es el lunes 02-11; DH08, DH09 y DH10 son el 11, 12 y 13 de noviembre. Si el mes no tiene el n-ésimo día hábil pedido, `dia_habil_n` lanza `ValueError` y la apertura del mes lo informa como «regla inválida» de esa tarea.

Otras funciones del calendario: `siguiente_habil`, `anterior_habil`, `dias_habiles_del_mes`, `sumar_dias_habiles` y `dias_habiles_entre` (los días hábiles después de `desde` hasta `hasta` inclusive).

**Feriados** (`nucleo/servicios/feriados.py`):

1. `cargar_propuesta(anio)` pide los feriados de Chile a la librería `holidays` y los crea **sin confirmar**.
2. `agregar_o_editar` permite agregar o corregir uno a mano (por ejemplo un feriado decretado a última hora); queda sin confirmar.
3. `confirmar_anio(anio, usuario)` confirma todos los pendientes del año y registra quién y cuándo.
4. `abrir_anio(anio, usuario)` exige que el año tenga feriados y que ninguno esté sin confirmar; recién entonces se puede abrir un mes.
5. `calendario_confirmado()` es el único calendario que usa el resto del sistema: solo cuenta lo confirmado.

No hay fechas de feriados escritas a mano en el código (decisión DEC-11). Los años 2027 y 2028 vienen cargados, confirmados y abiertos por la migración `0014_calendario_2027_2028`; **2026 no**: se carga y se confirma en la pantalla Abrir mes.

## 4.2 Tipos de regla de recurrencia

Archivo: `nucleo/servicios/recurrencia.py`. La función `fechas_limite(regla, anio, mes, cal, inicio_medicion)` convierte una regla y un mes en la lista de fechas límite. Si se pasa `inicio_medicion`, descarta las fechas anteriores.

`Regla` es un objeto inmutable con `tipo`, `dia_semana`, `n`, `dia`, `meses` y `ajuste` (`siguiente` o `anterior`, qué hacer si la fecha cae en día inhábil).

| Tipo (`TIPOS`) | Parámetros | Fechas que genera en el mes |
|---|---|---|
| `DIARIA_HABIL` | ninguno | Cada día hábil del mes |
| `SEMANAL` | `dia_semana` (0 = lunes … 4 = viernes) | Cada ese día de la semana; si es feriado, pasa al siguiente día hábil |
| `CIERRE_DIA_HABIL` | `n` entre 0 y 31 | El día hábil `n` del mes (`n = 0` es DH00, el último hábil del mes anterior) |
| `CIERRE_HITO` | `n` igual a 8, 9 o 10 | DH08, DH09 o DH10 (`hitos_de_entrega`) |
| `DIA_FIJO` | `dia` (1 a 31), `ajuste` | Ese día del mes; si es inhábil, se ajusta. Un día que no existe en el mes es `ReglaInvalida` |
| `FIN_DE_MES` | `ajuste` | El último día calendario del mes, ajustado |
| `MESES` | `meses` y, o bien `n` (día hábil N), o bien `dia` y `ajuste` | Solo en los meses indicados: el día hábil N, o el día del mes ajustado |
| `EVENTO` | ninguno | Ninguna: no genera ocurrencias (no hay pantalla para crearlas a mano) |

Errores del motor: `ReglaInvalida` (tipo o valor desconocido) y `ReglaIncompleta` (falta un dato, como el día de la semana). Abrir mes los convierte en avisos y no genera la tarea.

Cómo llega una regla a la `Tarea`:

- **Desde Excel:** `nucleo/servicios/importador.py`, función `convertir_regla(periodicidad, cuando, plan2)` interpreta pares como «Diaria + Todos los días hábiles», «Semanal + Lunes», «Mensual (cierre) + Día hábil 3» (también «Día hábil 4 a 5», «Día hábil 13» y «Último día hábil del mes anterior»), «Día hábil 8, 9 o 10» (hito), «Mensual + Día 13» (día fijo, ajuste `anterior`, marcado pendiente de confirmar), «Trimestral + Día hábil N» y «Puntual + Día 20 de abril, junio…». Lo ambiguo queda «requiere revisión» y no se adivina.
- **Desde el Mantenedor:** `nucleo/servicios/mantenedor.py`, función `_validar` (por ejemplo, `CIERRE_DIA_HABIL` acepta `n` de 0 a 7 o de 11 en adelante; el DH08, DH09 y DH10 se eligen con `CIERRE_HITO`).
- **En palabras:** `nucleo/servicios/reglas_texto.py`, función `describir`.

### Campos de `Tarea` que complementan la regla

| Campo | Efecto real en el código | Dónde se usa |
|---|---|---|
| `modo_cierre` = `pausar` | Entre DH01 y DH10 la tarea **no genera** ocurrencias | `periodos.vista_previa`; `matriz.items_de` |
| `modo_cierre` = `reasignar` con `cargo_cierre` | Entre DH01 y DH10 la ejecuta `cargo_cierre` y la revisa `cargo_revisa_cierre` (o el revisor de siempre) | Los mismos |
| `modo_cierre` = `fuera` | No pausa ni reasigna: se trata igual que `igual` en el código (el texto del modelo dice «no consume sus horas del equipo contable»; ver 13.2) | Los mismos |
| `dh_inicio` | Solo informativo en la ficha y la exportación; **no cambia** la fecha límite | Mantenedor, Excel |
| `horas_dh` | Reparte las horas del cierre por día hábil en la **matriz** (no cambia fechas ni ocurrencias) | `matriz.items_de` |
| `horas_semana` | Horas por día de la semana de una tarea diaria, en la **matriz**; un día sin valor no se hace | `matriz.items_de` |
| `predecesoras` | Solo informativas: la matriz avisa si una tarea vence antes que su predecesora. **No se exigen** al ejecutar | `matriz.dependencias_incumplidas`, `hitos_del_plan` |
| `al_terminar_cierre` | Se guarda y se exporta; **ningún código actúa sobre él** | — |

## 4.3 Apertura de mes

Archivo: `nucleo/servicios/periodos.py`. Pantalla: `/cierre/abrir/` (`nucleo/views_apertura.py`). Un **período M** reúne las diarias y semanales del mes M y el cierre del mes M−1, que vence en los primeros días hábiles de M.

`vista_previa(anio, mes, inicio_medicion)` no escribe nada:

1. Exige que el año esté `abierto` (si no, `ErrorDeNegocio`) y que el período no esté cerrado.
2. Toma `inicio_medicion` del período si ya existe; si no, el que se le pasa.
3. Por cada `Tarea` activa:
   - Si ya tiene ocurrencias en el período, la salta (cuenta como «ya existían»).
   - Si `requiere_revision` o no tiene regla, la omite con un aviso.
   - Calcula las fechas con `fechas_limite`; `ReglaIncompleta` y `ReglaInvalida` o `ValueError` se vuelven avisos.
   - Aplica `modo_cierre` entre DH01 y DH10 (pausar o reasignar).
   - Si el cargo es **externo**, genera la ocurrencia sin persona y con `tipo_marca = RECIBIDA`.
   - Si es interno, exige **exactamente una persona con asignación vigente en esa fecha**: ninguna da el aviso `sin_responsable` y varias `varias_personas`. Con cualquier problema **no se genera nada de esa tarea**.

`abrir_mes(anio, mes, usuario, inicio_medicion)` hace lo mismo y además, en una transacción, crea el `Periodo` si no existe, inserta las ocurrencias con `bulk_create` y deja el evento `periodo.abierto` en la bitácora. Cada ocurrencia copia `cargo_ejecuta`, `colaborador`, `cargo_revisa`, `regla_copia`, `minutos_estimados` y calcula `vence_el` con `gracia.vence_el_para`.

**Idempotencia:** volver a abrir el mes no duplica nada (salta las tareas que ya tienen ocurrencias y existe la restricción única de la base). Corregir una tarea con aviso y volver a abrir el mes genera solo lo que faltaba. Un cambio en una tarea **no reescribe** ocurrencias ya generadas: rige para los meses que aún no se abren.

## 4.4 Gracia de arranque (`vence_el`)

Archivo: `nucleo/servicios/gracia.py`. Pedido por la dueña del producto el 17-11-2026 (DEC-43): la medición comienza el 01-11-2026, el equipo registra lo que ya hizo y **durante tres semanas (01-11 al 22-11-2026) nada cuenta como atrasado**.

- Parámetros: `inicio_operacion` (formato AAAAMMDD; `0` = sin gracia) y `dias_de_gracia` (por defecto 21).
- `gracia_hasta()` = inicio + días de gracia (para el 01-11-2026, el 22-11-2026).
- `vence_el_para(fecha_limite)`: si la fecha límite es anterior al fin de la gracia, devuelve el fin de la gracia; si no, la propia fecha.
- Las ocurrencias **conservan su fecha límite del plan**, pero solo cuentan como atrasadas cuando `exigible < hoy`, es decir, desde el 23-11-2026. Registradas dentro de la gracia, cuentan como a tiempo.
- En «Mi día» (`agenda.agenda_de`) lo ya vencido y aún no exigible aparece en el bloque «Por registrar».
- `configurar(inicio, dias, usuario)` guarda los parámetros y recalcula `vence_el` de las ocurrencias existentes; lo invoca el comando `configurar_gracia` (y `cargar_plan --inicio-uso`).

## 4.5 Carga y techo por día

Hay dos cálculos, con propósitos distintos.

**Carga mensual por cargo** (pantalla «Carga del equipo»; `nucleo/servicios/carga.py`, `por_cargo`):

| Magnitud | Fórmula |
|---|---|
| Horas de ejecución al mes | `minutos_estimados / 60` × `ejecuciones_mes`, por tarea activa |
| Horas de revisión | `minutos_revision` de la tarea (o el parámetro `minutos_revision`, hoy 0) × ejecuciones; se cargan a quien revisa. Una tarea sin tiempo de ejecución no carga revisión |
| Capacidad | Parámetro `horas_disponibles_mes` (160); los cargos externos no tienen |
| Semáforo (`semaforo_de_carga`) | Verde bajo `carga_ambar` (90 %), ámbar de 90 % a 110 %, rojo sobre `carga_rojo` (110 %) |
| Carga del cierre por día | `por_dia_de_cierre`: horas de las tareas del cierre que vencen cada día hábil contra la capacidad diaria (160 / 21) menos lo que ocupa la operación diaria |
| Real contra estimado | `real_vs_estimado`: solo tareas hechas con horas reales anotadas |

**Matriz del cierre** (4.7) usa la jornada real de cada día (9 h o 5 h) y el techo de planificación:

| Día | Techo (fracción de la jornada que se planifica) |
|---|---|
| DH00 a DH06 | 90 % |
| DH07 | 80 % |
| DH08 | 75 % |
| DH09 | 85 % |
| DH10 | 95 % |

Definido en `TECHO_POR_DH` (`nucleo/servicios/matriz.py`). Pasar el techo significa usar la reserva (color ámbar); pasar la jornada es sobrecarga (rojo).

## 4.6 KPI de cumplimiento

Archivo: `nucleo/servicios/kpi.py`. Fuente única: las ocurrencias del período.

| Indicador | Definición implementada | Función |
|---|---|---|
| Vencida | `exigible < hoy`, donde `exigible = vence_el` (o la fecha límite). Una tarea vence al final de su día | `por_colaborador` |
| A tiempo | El **día local** de la **primera** marca `hecha` es menor o igual que `exigible`. Hecha tarde nunca suma; una devuelta conserva su resultado original | `_a_tiempo` |
| Cumplimiento a tiempo | `a_tiempo` ÷ `vencidas`, sin contar `no_aplica`. Solo ocurrencias con persona (los externos no entran al KPI de nadie) | `KpiPersona.a_tiempo_pct` |
| Completitud | Ocurrencias vencidas con primera marca ÷ vencidas | `KpiPersona.completitud_pct` |
| Tasa de devolución | Ocurrencias con alguna devolución ÷ ocurrencias con primera marca | `KpiPersona.tasa_devolucion_pct` |
| Tasa de «no aplica» | `no_aplica` ÷ vencidas incluyendo `no_aplica` | `KpiPersona.tasa_no_aplica_pct` |
| Insumos por área (externos) | `RECIBIDA` a tiempo ÷ vencidas, por cargo externo; aparte del KPI de personas | `insumos_por_cargo_externo` |
| Cumplimiento de revisión | Revisiones hechas dentro del plazo ÷ revisiones debidas, por cargo revisor. Plazo: parámetro `plazo_revision_dias_habiles` (1) desde la primera marca | `cumplimiento_de_revision` |
| Persona en todos los meses abiertos | Suma los períodos abiertos | `de_persona` |

**Semáforo** (`kpi.semaforo`, comparación con enteros, sin redondeos): sin vencidas es «sin datos»; menos de `minimo_muestra_semaforo` (10) vencidas es «muestra insuficiente» sin color; `a_tiempo × 100 ≥ meta_cumplimiento × vencidas` (95) es verde; `≥ umbral_ambar` (90) es ámbar; el resto, rojo. Siempre se muestra con palabra además del color (`nucleo/servicios/presentacion.py`).

**Panel del cierre** (solo tareas de regla `CIERRE_DIA_HABIL` o `CIERRE_HITO`, `kpi._cierre`): `ruta_del_cierre` (un hito por día hábil hasta el DH10), `resumen` (avance, atrasadas, vencen hoy, por revisar, equipo a tiempo), `avance_por_proceso` y `tareas_del_cierre` (el listado detrás de cada número).

Nota de criterio: `kpi.resumen` cuenta como atrasadas las ocurrencias `pendiente` y `bloqueada` vencidas; los listados del panel y el tablero cuentan también las `devuelta` vencidas.

## 4.7 Matriz del cierre

Archivos: `nucleo/servicios/matriz.py`, vistas `matriz_del_cierre` y `matriz_exportar` en `nucleo/views_informes.py`, plantillas `informe_matriz_plan.html` y `informe_matriz.html`. Solo Gerente y Jefatura.

- **Contexto** (`contexto(anio, mes)`): calendario confirmado, días de la matriz = DH00 más los días hábiles hasta el DH10, cargos internos activos y tareas activas que no requieren revisión.
- **Carga de una tarea** (`items_de`): genera un `Item` por fecha con las horas de ejecución del cargo que la hace (aplicando pausar o reasignar entre DH01 y DH10, la distribución `horas_dh` y las `horas_semana`) y, si hay minutos de revisión, un `Item` de revisión para quien revisa. Con la revisión en 0 minutos (decisión DEC-36) la revisión no suma carga.
- **Construcción** (`construir`): suma por cargo y día en una `FilaDeCargo` con horas, capacidad (la jornada del día, 0 si no es hábil), total del mes y tope (`horas_mes_max`).
- **Colores en pantalla** (`_clase_de_horas` en `views_informes.py`): rojo si pasa la jornada, ámbar si pasa el techo, verde si hay carga bajo el techo, gris sin carga.
- **Lecturas**: `diagnostico_del_plan` (ocupación de DH01 a DH08, quién está más y menos exigido, quién pasa la jornada o el techo, tope del mes), `hitos_del_plan` (tareas de tipo «Hito» o «Control» y si lo anterior llega a tiempo) y `dependencias_incumplidas`.
- **Propuesta de equilibrio** (`proponer`, `?ver=propuesta`): opcional; recalcula un reparto «en cascada» y **no se aplica sola**. La descarga `matriz_del_cierre_AAAA-MM.xlsx` (`excel_masivo.exportar_matriz`) siempre incluye la propuesta y una hoja «Planificación» con ella aplicada, para revisarla y, si se acepta, cargarla desde el Mantenedor.
- **Comprobación documentada** (`docs/f1/07_planificacion_2_0.md`, `pruebas/test_plan2.py`): con la Planificación 2.0 cargada, la matriz reproduce día por día la tabla de carga del archivo para las cuatro personas y cumple las 224 predecesoras de 133 tareas.

## 4.8 Reasignación de quién ejecuta

Funciones `puede_reasignar`, `candidatos_a_ejecutar` y `reasignar` en `nucleo/servicios/ejecucion.py` (DEC-41). Rutas POST `reasignar` y `tomar` de `/ocurrencias/<pk>/<accion>/`.

- Cualquier persona del equipo con cuenta, cargo y rol `COLABORADOR`, `JEFATURA` o `GERENTE` puede cambiar quién hace una ocurrencia **mientras no esté hecha** (estado pendiente, devuelta o bloqueada), con el período abierto y que no sea `RECIBIDA`.
- La nueva persona debe estar activa y ejercer un cargo interno vigente; el sistema usa el primer cargo por orden. **Quien revisa nunca puede ser quien la hace.**
- Cambia solo **esa ocurrencia**: actualiza `colaborador` y `cargo_ejecuta`. La regla de la tarea no cambia; el cambio permanente se hace en el Mantenedor (Gerente y Jefatura).
- Queda en la bitácora como `ocurrencia.reasignada` con quién la tenía, quién la toma y el motivo.

## 4.9 Revisión y tareas de responsables externos

- Cada tarea tiene un `cargo_revisa` (puede no haber). Lo define el Excel; **no se inventa** para tareas internas. El detalle de la tarea y el Mantenedor muestran «Sin revisor» donde no lo hay.
- Para una tarea de cargo externo, quien «recibe» es el cargo revisor; si el Excel no lo dice, el importador propone a la Jefa de Control (`FilaImport.revisor`).
- `revisar` y `devolver` exigen que la ocurrencia esté `hecha`, que no sea `RECIBIDA`, que quien actúa **no sea quien la marcó** (`hecha_por`) y que ejerza el cargo revisor vigente (`_es_revisor` mira las asignaciones vigentes de hoy).
- Decisión DEC-36: la revisión va **dentro de las horas de quien ejecuta**; el parámetro `minutos_revision` vale 0.

## 4.10 Evidencias (adjuntos)

Archivo: `nucleo/servicios/evidencias.py`; vista `evidencia` en `nucleo/views.py`.

| Aspecto | Regla implementada |
|---|---|
| Tipos aceptados | PDF, PNG, JPG, JPEG, XLSX, DOCX, XLS, DOC, CSV, TXT (`TIPOS`) |
| Tamaño | Hasta 10 MB (`MAX_BYTES`) |
| Contenido | Se compara la firma del archivo con la extensión (por ejemplo `%PDF`); CSV y TXT deben ser texto de verdad |
| Nombre | `nombre_seguro` quita rutas y caracteres de control; el archivo se guarda con nombre aleatorio en `EVIDENCIAS_ROOT/<id de ocurrencia>/` |
| Trazabilidad | Cada adjunto deja nombre, tamaño y huella SHA-256 en el evento `ocurrencia.comentario` de la bitácora |
| Quién lo ve (`puede_ver`) | Gerente y Jefatura; quien ejecuta la tarea; quien ejerce el cargo revisor |
| Entrega | Solo por `/evidencias/<pk>/`, nunca desde nginx. PDF e imágenes se muestran; el resto se descarga. Cabeceras `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox; default-src 'none'…` y `Cache-Control: private, no-store` |
| Seguridad de rutas | `ruta_del_archivo` resuelve la ruta y rechaza cualquier archivo fuera de `EVIDENCIAS_ROOT` |

La carpeta de adjuntos **debe incluirse en el respaldo** (lo hace `respaldar`).

## 4.11 Horas reales y estado bloqueada

- **Horas reales** (`registrar_horas`, `parsear_horas`): quien ejecuta anota las horas con «1,5», «1.5» o «1:30» (más de 0 y hasta 24 h), al marcar hecha o después, mientras el período esté abierto. Cada cambio queda en la bitácora. `carga.real_vs_estimado` las compara con lo estimado.
- **Bloqueada** (`marcar_bloqueada`, `retomar`): quien ejecuta avisa que no puede avanzar y debe dar un motivo. Una tarea bloqueada no cuenta como hecha y sigue contando como pendiente atrasada si vence.

## 4.12 Parámetros

Archivo: `nucleo/servicios/parametros.py` (diccionario `INICIALES`). Si no existe la fila en `Parametro`, rige el valor inicial. **No hay pantalla**: se cambian con `configurar_gracia` (solo la gracia) o desde `manage.py shell` llamando a `parametros.guardar`. Cada cambio queda en la bitácora como `parametro.editado`.

| Clave | Valor inicial | Estado | Efecto |
|---|---|---|---|
| `meta_cumplimiento` | 95 | confirmado | Meta de cumplimiento a tiempo (verde) |
| `umbral_ambar` | 90 | pendiente de confirmar | Bajo este porcentaje el semáforo es rojo |
| `plazo_revision_dias_habiles` | 1 | pendiente de confirmar | Plazo para revisar una tarea hecha |
| `minimo_muestra_semaforo` | 10 | pendiente de confirmar | Mínimo de tareas vencidas para colorear |
| `horas_disponibles_mes` | 160 | pendiente de confirmar | Capacidad mensual por persona en «Carga del equipo» |
| `dias_habiles_mes` | 21 | pendiente de confirmar | Reparto de la carga por día |
| `minutos_revision` | 0 | confirmado | Minutos extra que carga quien revisa (0 = dentro de las horas de quien ejecuta) |
| `inicio_operacion` | 0 | pendiente de confirmar | Primer día de uso (AAAAMMDD); 0 = sin gracia |
| `dias_de_gracia` | 21 | confirmado | Duración de la gracia de arranque |
| `carga_ambar` | 90 | pendiente de confirmar | Desde este porcentaje de capacidad la carga es ámbar |
| `carga_rojo` | 110 | pendiente de confirmar | Sobre este porcentaje la carga es roja |
| `tiempo_obligatorio` | 0 | confirmado | Reservado: exigir minutos al marcar hecha (apagado) |

## 4.13 Índice: dónde vive cada regla

| Regla | Archivo | Función o elemento |
|---|---|---|
| Día hábil, DHnn, DH00 | `nucleo/servicios/calendario.py` | `Calendario.dia_habil_n` |
| Hitos DH08 a DH10 y ventana del cierre | `nucleo/servicios/calendario.py` | `hitos_de_entrega`, `ventana_del_cierre` |
| Jornada | `nucleo/servicios/calendario.py` | `JORNADA_HORAS` |
| Feriados confirmados | `nucleo/servicios/feriados.py` | `calendario_confirmado`, `confirmar_anio`, `abrir_anio` |
| Tipos de regla y fechas | `nucleo/servicios/recurrencia.py` | `TIPOS`, `fechas_limite` |
| Texto a regla | `nucleo/servicios/importador.py` | `convertir_regla` |
| Apertura de mes | `nucleo/servicios/periodos.py` | `vista_previa`, `abrir_mes` |
| Gracia de arranque | `nucleo/servicios/gracia.py` | `vence_el_para`, `configurar` |
| Semana del cierre (pausar, reasignar) | `nucleo/servicios/periodos.py` y `matriz.py` | `vista_previa`, `items_de` |
| Marcar, revisar, devolver, bloquear | `nucleo/servicios/ejecucion.py` | `marcar_hecha`, `revisar`, `devolver`, `marcar_bloqueada` |
| Reasignar quién ejecuta | `nucleo/servicios/ejecucion.py` | `reasignar`, `puede_reasignar` |
| KPI y semáforo | `nucleo/servicios/kpi.py` | `por_colaborador`, `semaforo` |
| Carga y capacidad | `nucleo/servicios/carga.py` | `por_cargo`, `por_dia_de_cierre` |
| Matriz y techo | `nucleo/servicios/matriz.py` | `construir`, `items_de`, `TECHO_POR_DH` |
| Evidencias | `nucleo/servicios/evidencias.py` | `validar`, `guardar`, `puede_ver` |
| Códigos jerárquicos | `nucleo/servicios/codigos.py` | `preparar_subtarea`, `al_cambiar_el_codigo_del_proceso` |
| Orden y dependencias de procesos | `nucleo/servicios/estructura.py` | `reordenar_procesos`, `fijar_dependencias`, `etapas` |
| Bitácora sellada | `nucleo/servicios/auditoria.py` | `registrar`, `verificar_cadena` |

# 5. Carga masiva y plan vigente

## 5.1 Visión general

```text
Excel (.xlsx)
   │  importador.leer_excel  ──► detecta el formato ──► FilaImport (una por tarea)
   ▼
convertir_regla  (Periodicidad + Cuándo → regla)      plan2.completar_regla (reglas ya definidas)
   │
   ▼  plan2.resolver_procesos / emparejar (solo Planificación 2.0 y Plan vigente)
VistaPrevia: altas, cambios, bajas, requieren revisión, procesos y cargos nuevos
   │            (no se guarda nada)
   ▼  confirmación de una persona
importador.aplicar (una transacción)
   │   procesos → altas → cambios → bajas → orden → predecesoras → bitácora «importacion.aplicada»
   ▼
Tarea / Proceso / TareaPrincipal  ──►  Abrir mes genera las Ocurrencias
```

La carga es siempre en **dos pasos**: primero la vista previa y, tras confirmar, la aplicación. El contenido del Excel es **dato, no instrucción**: se leen solo los valores de las celdas (`data_only=True`), nunca fórmulas ni macros.

## 5.2 Formatos que acepta el importador

`importador.leer_excel` mira las hojas del archivo y elige el lector:

| Formato | Cómo se reconoce | Lector |
|---|---|---|
| **Planificación 2.0** | Tiene las hojas `Diario-Semanal` y `Mensual` (`plan2.es_plan2`) | `plan2.leer` |
| **Plan vigente** (el que descarga la app) | Tiene la hoja `Plan vigente` con las columnas `Código`, `Subtarea` y `Predecesoras (códigos)` (`plan2.es_plan_vigente`) | `plan2.leer_plan_vigente` |
| **Listado de 16 columnas** (formato anterior) | Hoja `Planificación`, `Tareas` o la primera hoja | `importador.leer_excel` |

### Planificación 2.0

La hoja `Maestro` es solo respaldo y no se lee. Se leen `Diario-Semanal` (tareas diarias y semanales) y `Mensual` (tareas del cierre). Solo cuentan las filas cuya columna `Código` cumple el patrón `OO-PPP.TT.SSS` (`PATRON_CODIGO`).

| Columna | Hojas | Qué se hace con ella |
|---|---|---|
| `Código` | ambas | Referencia para predecesoras y para el número y la sigla del proceso |
| `Proceso`, `Tarea principal`, `Subtarea` | ambas | Identidad de la tarea (clave estable) |
| `Responsable (ejecuta)`, `Revisa` | ambas | Deben ser **cargos** (se traducen nombres antiguos: «Contadora Senior» a «Contador Senior», «Jefa Control» a «Jefa de Control», «Asistente Contable» a «Analista Contable») |
| `Periodicidad`, `Cuándo` | ambas | Se convierten en regla (`convertir_regla` con `plan2=True`) |
| `Horas por ejecución` | ambas | Pasan a `minutos_estimados`; las de 9 minutos pasan a 10 (`MINUTOS_AJUSTADOS`) |
| `Fuente de horas` | ambas | `Estimada` y `Ajustada` actualizan `fuente_horas`; `Original` no cambia lo que ya hay |
| `Observación` | ambas | `referencia_normativa` |
| `Cambio`, `Justificación del cambio`, `Tipo de control` | ambas (si la hoja las trae) | `cambio_plan`, `justificacion`, `tipo_control` |
| `Predecesoras` | `Mensual` | Lista de códigos del archivo; se convierte en vínculos entre tareas (`fijar_predecesoras`) |
| `Modo en semanas de cierre (DH01–DH10)` | `Diario-Semanal` | `Mantiene` a `igual`, `Pausa` a `pausar`, `Fuera del equipo contable` a `fuera` |
| `Al terminar el cierre` | `Diario-Semanal` | `al_terminar_cierre` (`se pone al día` o `se retoma`) |
| `Lun (h)` a `Vie (h)` | `Diario-Semanal` | `horas_semana`, solo si una tarea diaria no rinde lo mismo todos los días |
| `DH00` a `DH10` | `Mensual` | `horas_dh`, solo si no son todas el día en que vence |

Las columnas de fechas del archivo **no se leen**: la app calcula las fechas con el calendario de cada mes. Reglas especiales de `nucleo/servicios/plan2.py`:

- `MINUTOS_AJUSTADOS`: 9 minutos pasan a 10 (DEC-40).
- `DIA_DE_VENCIMIENTO`: la cuota de contribuciones (`13-PBC.03.001`) vence el día 15 (si es inhábil, el hábil siguiente).
- `MES_DE_LAS_TAREAS_ANUALES`: las dos tareas anuales (`24-IVS.01.003` y `28-PEI.06.002`) son de enero; un «día hábil 30» no existe y se toma como el día 30 del mes (si es inhábil, el hábil anterior).
- Una tarea **trimestral** con «Día hábil N» se genera en marzo, junio, septiembre y diciembre.
- Si el código del archivo mezcla procesos, **manda el nombre del proceso**: `resolver_procesos` asigna a cada proceso el número y la sigla del código que más veces lo acompaña.

### Plan vigente (descarga y recarga)

Descarga: Mantenedor → Tareas → «Descargar planificación vigente» (`plan_vigente.exportar`). Hojas del archivo:

| Hoja | Contenido |
|---|---|
| `Cómo leer` | Instrucciones y reglas vigentes |
| `Plan vigente` | Una fila por tarea activa, con los códigos de la app |
| `Carga por persona y día` | Horas del mes actual de DH00 a DH10 contra jornada y techo (si el calendario no está listo, la hoja lo avisa) |
| `Procesos` | Procesos con código, sigla, orden y conteo de tareas |
| `Desactivadas` | Tareas que ya no se hacen (historial) |

Columnas de `Plan vigente` (`plan_vigente.COLUMNAS`): `Código`, `Proceso` (formato «OO-PPP · nombre»), `Tarea principal`, `Subtarea`, `Responsable (ejecuta)`, `Revisa`, `Periodicidad`, `Cuándo`, `Empieza (día hábil)`, `Horas por ejecución`, `Horas por día hábil (cierre)` (por ejemplo «DH01 0,8 · DH02 1,2»), `Horas por día de la semana` (por ejemplo «Lun 2 · Mar 1»), `En las semanas del cierre`, `Al terminar el cierre`, `Predecesoras (códigos)`, `Tipo de control`, `Cambio respecto del plan anterior`, `Justificación`, `Por revisar`, `Observación (referencia normativa)`.

Al volver a cargarlo, **solo se lee la hoja `Plan vigente`** (`plan2.leer_plan_vigente`). El `Código` identifica la tarea aunque se corrija su texto. La columna `Por revisar` se escribe pero no se lee de vuelta.

### Listado de 16 columnas (formato anterior)

Lo que genera `excel_masivo.exportar_tareas` (hoja `Planificación`, más una hoja `Instrucciones`): `Código`, `Proceso`, `Tarea principal`, `Subtarea`, `Responsable (ejecuta)`, `Revisa`, `Periodicidad`, `Cuándo`, `Observación`, `Día cierre`, `Horas por ejecución`, `Ejecuciones por mes`, `Semana del cierre`, `Responsable en el cierre`, `Revisa en el cierre`, `Minutos de revisión`. La columna `Código` no se lee: una tarea es la misma mientras no cambie `Proceso` + `Tarea principal` + `Subtarea`. Una planilla sin la columna `Minutos de revisión` no borra los minutos ya guardados.

## 5.3 Reglas de emparejamiento con las tareas existentes

La identidad base es `clave_estable` (SHA-256 de proceso, tarea y subtarea normalizados, en `importador._clave`). En la Planificación 2.0 y el Plan vigente, `plan2.emparejar` busca, en este orden:

1. La misma clave (proceso + tarea + subtarea).
2. La misma clave con el proceso ya renombrado.
3. Solo en el Plan vigente: el mismo código de la app.
4. La misma tarea y subtarea, aunque haya cambiado de proceso.
5. El mismo proceso y la misma subtarea, aunque haya cambiado de tarea.
6. El mismo código con la subtarea casi igual (similitud de texto de 0,7 o más, `difflib`): se corrigió el texto.

En los pasos 4 y 5 la pareja debe ser **única de los dos lados**; el paso 6 solo vale si la tarea existente está activa y aún sin pareja. Si hay duda, la fila se trata como nueva y la antigua queda para desactivar, y la persona lo ve en la vista previa antes de confirmar. En el formato de 16 columnas solo rige la clave estable: cambiar el texto de `Proceso`, `Tarea principal` o `Subtarea` crea una tarea nueva y desactiva la anterior.

## 5.4 Qué guarda `aplicar`

`importador.aplicar(vp, usuario, detalle)`, dentro de una transacción:

1. Plan 2.0: `plan2.preparar_procesos` renombra los procesos que cambiaron de nombre y crea los que faltan con su número y sigla.
2. Altas: crea cada `Tarea` (el código se genera solo, ver 3.3); los cargos nuevos se crean con `importador._cargo` (orden y externo según las tablas `ORDEN_CARGOS` y `CARGOS_EXTERNOS`).
3. Cambios: actualiza los campos que difieren. Una tarea que cambia de proceso cambia de código y el anterior queda en el historial.
4. Bajas: las tareas que el archivo ya no trae se **desactivan** (`activa = False`), nunca se borran.
5. Orden de las tareas (`secuencia`) y de los procesos (`estructura.reordenar_procesos`).
6. Plan 2.0: `plan2.fijar_predecesoras`.
7. Evento `importacion.aplicada` con el resumen y, en la carga por pantalla, el nombre y la huella SHA-256 del archivo.

Lo cargado rige desde el próximo mes que se abra; no reescribe ocurrencias ya generadas.

## 5.5 Carga masiva desde la pantalla

Ruta `/mantenedor/tareas/cargar/` (Gerente y Jefatura), implementada en `views_mantenedor.tareas_cargar` y `nucleo/servicios/excel_masivo.py`:

1. **Revisar:** se sube el archivo; `previsualizar_tareas` valida y muestra altas, cambios (hasta 40 filas por lista) y bajas. El archivo queda en espera en una carpeta temporal (`planificacion_cargas` dentro del directorio temporal del sistema) con un nombre aleatorio de 32 hexadecimales; la sesión guarda ese identificador.
2. **Aplicar:** `aplicar_tareas` vuelve a validar. `problemas_para_aplicar` bloquea la carga si falta el responsable, si «Reasignar» no trae responsable en el cierre o si hay cargos desconocidos (solo se aceptan los de `ORDEN_CARGOS` y `CARGOS_EXTERNOS`, para no crear un cargo por un error de tipeo). Si la carga desactiva tareas, exige marcar una confirmación expresa.

Límites de `excel_masivo.validar_archivo` y `_abrir`: solo `.xlsx`, hasta 5 MB, hasta 50 MB descomprimido y hasta 5.000 filas por hoja. Los textos que empiezan con `=`, `+`, `-` o `@` se guardan como texto para que Excel no los interprete como fórmula (`excel_masivo._poner`).

**Procesos:** `/mantenedor/procesos/exportar/` y `/mantenedor/procesos/cargar/` (`excel_masivo.cargar_procesos`). Columnas `Orden`, `Código`, `Sigla`, `Proceso`, `Tareas activas`, `Activo`. Se puede reordenar, activar o desactivar y agregar procesos nuevos; no renombra (un proceso se reconoce por su nombre) y los que faltan en el archivo quedan después de los demás.

## 5.6 Comando `cargar_plan`

Carga el plan desde la consola, sin pantalla (`nucleo/management/commands/cargar_plan.py`; opciones y ejemplo en 8.1). Diferencias con la pantalla:

- Sin `--aplicar` solo muestra la vista previa.
- **Se detiene si el archivo menciona cargos que no existen en la base** (`vp.cargos_nuevos`), salvo que se use `--crear-cargos` (los crea con `importador.aplicar`). En una base recién migrada solo existe el cargo «Contador», así que la primera carga lleva `--crear-cargos` (ver 8.4). Revisar antes la lista «Se crearán N cargos»: si alguno es el nombre de una persona, usar `--cargo "TEXTO=CARGO"`.
- Aplica con `usuario=None` (la bitácora registra «por consola»).
- `--abrir-mes` exige que el año esté abierto (ver 8.4).

# 6. Seguridad

## 6.1 Autenticación y flujo de ingreso

```text
POST /ingresar/  (usuario + clave)
   │
   ├─ FormularioDeIngreso.clean ........ si la cuenta está bloqueada, avisa cuántos minutos faltan
   ├─ RespaldoConBloqueo.authenticate .. cuenta bloqueada: devuelve None, ni con la clave correcta
   │
   ├─ clave incorrecta ──► señal user_login_failed ──► bloqueo_acceso.registrar_fallo
   │                           (5 fallos seguidos = bloqueo de 15 minutos;
   │                            si es una cuenta real queda «sesion.cuenta_bloqueada» en la bitácora)
   │
   └─ clave correcta ───► login ──► señal user_logged_in ──► borra los fallos y deja «sesion.iniciada»
                                          │
                                          ▼
                    SegundoFactorMiddleware (en cada solicitud siguiente)
                      ¿el rol lo exige y la sesión no tiene «segundo_factor_ok»?
                         sí ──► redirige a /cuenta/segundo-factor/?siguiente=...
                         no ──► deja pasar
```

- **Backend único:** `AUTHENTICATION_BACKENDS = ["nucleo.autenticacion.RespaldoConBloqueo"]`. El bloqueo se aplica en el backend, no solo en el formulario, así que protege también `/admin/login/`.
- **Sesión:** cookie `HttpOnly` y `SameSite=Lax`. En producción además `Secure`, vence a los **60 minutos sin actividad** (`SESSION_COOKIE_AGE` con `SESSION_SAVE_EVERY_REQUEST`) y se cierra al cerrar el navegador.
- **Cerrar sesión:** `/salir/` acepta solo `POST` (Django 5 en adelante). El menú lateral usa un formulario; el enlace «Salir» de la pantalla del segundo factor usa `GET` y responde 405 (ver 13.2).
- **Roles:** son grupos de Django (`nucleo/permisos.py`, función `rol_de`). Si una cuenta tuviera varios, gana el de mayor precedencia según el orden `ADMIN_SISTEMA`, `GERENTE`, `JEFATURA`, `COLABORADOR`, `LECTURA`. Una cuenta sin grupo ve la página `sin_perfil.html` (403).
- **Django admin** está montado en `/admin/` (`config/urls.py`) pero la aplicación no registra ningún modelo propio: solo ofrece usuarios y grupos de Django. Las cuentas que crean los comandos y el Mantenedor no son `is_staff`. Ver 13.2.

## 6.2 Roles y permisos (matriz verificada contra el código)

El permiso real se valida en el servidor; la interfaz solo esconde botones (`nucleo/contexto.py`, función `menu`). La matriz de `docs/f1/03_kpi_roles_sod.md` es el diseño inicial y **difiere** del código en varios puntos; esta es la vigente.

| Acción | ADMIN_SISTEMA | GERENTE | JEFATURA | COLABORADOR | LECTURA |
|---|---|---|---|---|---|
| Ver informes (panel, tablero, cronograma, cumplimiento, carga), Check List de cualquier persona y por cargo, árbol de planificación, detalle de tarea | Sí | Sí | Sí | Sí | Sí |
| Ver y descargar la Matriz del cierre | No | Sí | Sí | No | No |
| Exportar la planificación (árbol) a Excel | No | Sí | Sí | No | No |
| Abrir mes: feriados, abrir año, abrir mes | Sí | Sí | No | No | No |
| Mantenedor de Tareas y Procesos (crear, editar, Excel, plan vigente) | No | Sí | Sí | No | No |
| Mantenedor de Usuarios | Sí | Sí | No | No | No |
| Crear o modificar administradores | Sí | No | No | No | No |
| Marcar hecha, bloquear, retomar y anotar horas de **tareas propias** | No | Sí | Sí | Sí | No |
| Comentar y adjuntar documentos | No | Sí | Sí | Sí | No |
| Cambiar quién ejecuta una tarea (reasignar o tomar) | No | Sí | Sí | Sí | No |
| Revisar y devolver | Solo si ejerce el cargo revisor | Solo si ejerce el cargo revisor | Solo si ejerce el cargo revisor | Solo si ejerce el cargo revisor | Solo si ejerce el cargo revisor |
| Marcar «Recibido» (tareas de externos) | Quien ejerce el cargo revisor | Quien ejerce el cargo revisor | Quien ejerce el cargo revisor | Quien ejerce el cargo revisor | Quien ejerce el cargo revisor |
| Ver un adjunto | Solo si ejerce el cargo revisor | Sí | Sí | Quien ejecuta la tarea, o ejerce el cargo revisor | Solo si ejerce el cargo revisor |
| Marca por excepción; solicitar y resolver «no aplica» | Sin pantalla | Servicio, sin pantalla | Servicio, sin pantalla | Servicio, sin pantalla | No |
| Cambiar la propia clave | Sí | Sí | Sí | Sí | Sí |
| Segundo factor obligatorio (en producción) | Sí | Sí | No | No | No |

Notas sobre la matriz:

- «Ejerce el cargo revisor» significa tener una asignación vigente hoy al cargo que figura como `cargo_revisa` de la ocurrencia (`ejecucion._es_revisor`). Los perfiles `ADMIN_SISTEMA` y `LECTURA` normalmente no tienen cargo, de modo que en la práctica no revisan. En el plan vigente quien revisa puede tener perfil `COLABORADOR` (por ejemplo, el Contador Senior).
- Nadie revisa lo que marcó él mismo. Quien revisa nunca puede ser quien ejecuta (también al reasignar).
- La marca por excepción (`marcar_por_excepcion`, solo rol `GERENTE`, con motivo) y el flujo de «no aplica» (`solicitar_no_aplica` y `resolver_no_aplica`: no lo resuelve quien lo pidió; lo resuelve el Gerente o un revisor con perfil `JEFATURA`) existen en el servicio con pruebas, pero ninguna vista los llama.
- Abrir mes (`periodos.py`, `feriados.py`) se protege solo con el decorador `con_roles` de la vista.
- Sin perfil (cuenta sin grupo): las pantallas responden 403; las acciones sobre ocurrencias fallan con «Tu cuenta no tiene un perfil asignado».

## 6.3 Política de claves y bloqueo por intentos

**Claves** (`AUTH_PASSWORD_VALIDATORS` en `config/settings.py`): similitud con los datos del usuario, **largo mínimo de 12 caracteres**, claves comunes y claves solo numéricas. Se exige al crear una cuenta con `crear_usuario`, al cambiarla con `recuperar_acceso` y al usar «Cambiar mi clave» (`/cuenta/clave/`). El hash es el que trae Django por defecto (`PASSWORD_HASHERS` no se modifica; solo `conftest.py` usa MD5 en las pruebas, por velocidad). Las claves nunca van en el comando ni en un archivo: se piden por teclado o por la entrada estándar.

**No se obliga a cambiar la clave en el primer ingreso.** Las cuentas creadas desde el Mantenedor de Usuarios **quedan sin clave** (`mantenedor.crear_usuario` usa `create_user` sin contraseña): no pueden ingresar hasta que el administrador ejecute `recuperar_acceso` (ver 13.2).

**Bloqueo** (`nucleo/bloqueo_acceso.py`):

| Aspecto | Valor |
|---|---|
| Intentos | `MAX_INTENTOS = 5` fallos seguidos contra el mismo usuario |
| Duración | `MINUTOS_DE_BLOQUEO = 15`, contados desde el último fallo; se levanta solo |
| Durante el bloqueo | Ni la clave correcta entra y los intentos no alargan el bloqueo |
| Clave de conteo | El nombre de usuario en minúsculas, exista o no, para no revelar qué cuentas existen |
| Dónde se guarda | Tabla `IntentoFallido` (sobrevive a reinicios y vale para todos los procesos); los fallos de más de un día se borran |
| Éxito | Un ingreso correcto borra el conteo |
| Bitácora | Solo el bloqueo de una cuenta real queda registrado (`sesion.cuenta_bloqueada`) |

## 6.4 Segundo factor (TOTP) y middleware que falla cerrado

Archivos: `nucleo/servicios/segundo_factor.py`, `nucleo/segundo_factor_middleware.py`, `nucleo/views_cuenta.py`, `nucleo/templates/nucleo/segundo_factor.html`.

- **Quién:** `GERENTE` y `ADMIN_SISTEMA` (`ROLES_QUE_LO_EXIGEN`). Se evalúa con `exige(usuario)`: `settings.EXIGE_2FA` y el rol.
- **Cuándo está activo:** `EXIGE_2FA = PRODUCCION or PLANIFICACION_2FA == "1"`. **En producción no se puede apagar**; en desarrollo está apagado salvo que se pida con la variable.
- **Cómo funciona:** el código son 6 dígitos que cambian cada 30 segundos en una aplicación como Google Authenticator o Microsoft Authenticator (RFC 6238, librería PyOTP). `verificar` acepta el paso actual y el anterior o el siguiente (30 segundos de tolerancia a cada lado), **nunca un paso ya usado** (`ultimo_paso`, protege contra repetición) y compara con `hmac.compare_digest`.
- **Bloqueo:** cinco códigos errados seguidos bloquean 15 minutos (el mismo mecanismo, con el nombre `2fa:usuario`), incluso con el código correcto.
- **Falla cerrada:** `SegundoFactorMiddleware` redirige a `/cuenta/segundo-factor/` a toda persona autenticada que deba usarlo y aún no verificó el código en esa sesión. Solo quedan libres esa pantalla, `/salir/` y `/static/`. Esto vale aunque la persona aún no tenga un secreto creado (la pantalla lo crea).
- **El `siguiente` del redireccionamiento** se valida con `url_has_allowed_host_and_scheme`: no puede llevar a otro sitio.
- **Alta:** `crear_usuario` crea el secreto de un Gerente o administrador y muestra **una sola vez** la clave y el enlace `otpauth://` para entregarlos en privado. Si la cuenta nace desde el Mantenedor, la pantalla del segundo factor muestra el secreto en el primer ingreso (`visible_en_pantalla`) hasta que se confirma el primer código.
- **QR:** solo si el servidor tiene la librería `qrcode` instalada (no está en `requirements.lock.txt`); si no, se escribe la clave a mano.
- **Cambio de teléfono:** `recuperar_acceso USUARIO --reiniciar-2fa` borra el secreto para que la persona vuelva a darlo de alta.
- **Bitácora:** `2fa.creado`, `2fa.activado`, `2fa.verificado`, `2fa.fallido` y `2fa.reiniciado`.
- **Límite conocido:** el secreto vive **en la base de datos**, sin cifrar. Quien lea la base o un respaldo puede generar códigos. Por eso la base y los respaldos deben tener permisos 600 o 700 y estar cifrados.

## 6.5 Modo «entrar sin clave» (solo desarrollo) y por qué no existe en producción

Es una comodidad para probar en el computador local (`/acceso-rapido/`). Se garantiza de varias formas independientes:

1. **Producción es el valor por defecto** (`config/entorno.py`, `resolver_entorno`): si no hay variable `PLANIFICACION_ENTORNO` ni archivo `.entorno_desarrollo` en la raíz, el entorno es `produccion`.
2. **Falla cerrada al arrancar:** `acceso_rapido_permitido` solo devuelve verdadero con `PLANIFICACION_SIN_CLAVE=1` **y fuera de producción**. Si alguien lo pide en producción, lanza `ImproperlyConfigured` y la aplicación **se niega a arrancar** (se comprobó ejecutando `manage.py check` con `PLANIFICACION_ENTORNO=produccion` y la variable en 1).
3. **La ruta no existe:** con el modo apagado, `views.acceso_rapido` responde 404 y la pantalla de ingreso no lo menciona.
4. **Otros comandos de desarrollo** (`datos_de_ejemplo`, `cargar_ejemplo_planificacion`) se niegan a correr en producción; `reloj.hoy` ignora `PLANIFICACION_HOY` en producción.

Cobertura de pruebas: `pruebas/test_acceso_rapido.py` (9 pruebas). Precaución: si en un servidor existiera el archivo `.entorno_desarrollo` (por ejemplo, al copiar la carpeta completa de un equipo de desarrollo) y no se definiera `PLANIFICACION_ENTORNO`, el entorno sería de desarrollo. Por eso la plantilla de variables de producción fija `PLANIFICACION_ENTORNO=produccion`.

## 6.6 Bitácora sellada (cadena) y `verificar_bitacora`

Archivo: `nucleo/servicios/auditoria.py`.

- **Qué se registra:** quién (`usuario` y su texto), qué (`accion`), sobre qué (`entidad` y `entidad_id`), el antes y el después (JSON) y un motivo. Familias de eventos: `sesion.*`, `2fa.*`, `acceso.recuperado`, `cuenta.clave_cambiada`, `usuario.*`, `tarea.*`, `tarea_principal.*`, `proceso.*`, `procesos.cargados`, `importacion.aplicada`, `tareas.descargadas`, `plan_vigente.descargado`, `planificacion.exportada`, `matriz.descargada`, `periodo.abierto`, `anio.abierto`, `feriado.editado`, `feriados.confirmados`, `gracia.configurada`, `parametro.editado`, `ocurrencia.*`, `no_aplica.*`, `catalogo.cargado` y `respaldo.hecho`.
- **Solo se agrega:** los triggers de la migración `0002_auditoria_inmutable` abortan cualquier `UPDATE` o `DELETE` sobre `nucleo_eventoauditoria`.
- **Sello encadenado:** cada evento guarda `sello_anterior` y `sello`. El sello es el SHA-256 del JSON canónico de `[momento en UTC, usuario, acción, entidad, entidad_id, antes, después, motivo, sello anterior]`. `registrar` lo calcula dentro de una transacción tomando el último evento.
- **Verificación:** `verificar_cadena()` recorre todos los eventos y devuelve los que no calzan con su contenido o rompen el encadenado. El comando `verificar_bitacora` falla con error si encuentra alguno. `verificar_respaldo` lo ejecuta sobre la base restaurada.
- **Alcance real del control:** los triggers y la cadena sirven como **evidencia de manipulación**, no como garantía. Quien pueda escribir en el archivo de la base puede quitar los triggers y, como el sello es un hash sin clave secreta ni ancla externa, recalcular toda la cadena. Es el riesgo residual RC-04 del diseño (SQLite en lugar de PostgreSQL con un rol sin `UPDATE`/`DELETE`). Se mitiga con permisos del archivo, respaldo fuera del servidor y verificaciones periódicas.
- Cobertura: `pruebas/test_auditoria.py`, que incluye alterar una fila saltándose los triggers y detectarlo.

## 6.7 Evidencias

Ver 4.10. Resumen de seguridad: tipos permitidos y firma verificada, 10 MB, nombre aleatorio fuera del repositorio, sin URL pública (solo `/evidencias/<pk>/` con permiso), ruta confinada a `EVIDENCIAS_ROOT`, cabeceras `nosniff` y `sandbox`, huella SHA-256 en la bitácora, y el contenido nunca se ejecuta.

## 6.8 CSRF, cookies y cabeceras en producción

De `config/settings.py` (siempre activo salvo donde se indica):

| Medida | Valor |
|---|---|
| CSRF | `CsrfViewMiddleware` activo; `CSRF_COOKIE_SAMESITE = "Lax"`; `CSRF_TRUSTED_ORIGINS` desde la variable de entorno |
| Cookie de sesión | `HttpOnly`, `SameSite=Lax` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` (`SECURE_CONTENT_TYPE_NOSNIFF`) |
| `Referrer-Policy` | `same-origin` |
| Solo en producción | `SECURE_SSL_REDIRECT = True`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS = 31536000` con `SECURE_HSTS_INCLUDE_SUBDOMAINS`, sesión de 60 minutos |
| Detrás de un proxy | `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` solo si `DJANGO_PROXY_SSL=1` |
| Arranque | En producción la aplicación **no arranca** sin `DJANGO_SECRET_KEY` ni `DJANGO_ALLOWED_HOSTS` |

Verificación realizada: `manage.py check --deploy` con variables de producción de prueba deja **una sola advertencia**, `security.W021` (falta `SECURE_HSTS_PRELOAD`), que el proyecto decidió dejar hasta que el dominio sea definitivo.

Lo que **no** está configurado, aunque el diseño inicial lo proponía: una política `Content-Security-Policy` global (solo la llevan las respuestas de adjuntos), `Permissions-Policy`, ni configuración de `LOGGING` (la salida de gunicorn va al journal de systemd; el `logs/seguridad.log` del diseño no existe). nginx agrega `nosniff` y `Referrer-Policy` por su cuenta (`deploy/nginx-planificacion.conf`).

# 7. Configuración

## 7.1 Variables de entorno

La configuración se lee solo de variables de entorno del proceso (`os.environ`); no hay lectura de archivos `.env`. En el servidor las carga systemd (`EnvironmentFile=/etc/planificacion/planificacion.env`) o `deploy/manage.sh`.

| Variable | Valor por defecto | Efecto | ¿Obligatoria en producción? |
|---|---|---|---|
| `PLANIFICACION_ENTORNO` | Si falta: `desarrollo` si existe el archivo `.entorno_desarrollo` en la raíz; si no, `produccion` | Elige el entorno (`desarrollo` o `produccion`; otro valor impide arrancar) | Recomendada fijarla en `produccion` (ver 6.5) |
| `DJANGO_SECRET_KEY` | Desarrollo: lee o crea el archivo local `.clave_secreta_local`. Producción: sin valor | Clave secreta de Django (sesiones, firmas) | **Sí**: sin ella la aplicación no arranca |
| `DJANGO_ALLOWED_HOSTS` | Desarrollo: `localhost`, `127.0.0.1`, `[::1]`, `testserver`. Producción: vacío | Servidores permitidos, separados por coma y sin `http://` | **Sí**: sin ella no arranca |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Vacío | Orígenes confiables para CSRF, con `https://`, separados por coma | Recomendada (la plantilla de `deploy/` la define) |
| `DJANGO_PROXY_SSL` | Vacío | Con `1` (solo en producción) Django confía en `X-Forwarded-Proto` para saber que la solicitud llegó por HTTPS | Sí si HTTPS termina en nginx. Sin ella, detrás de un proxy que habla HTTP con gunicorn, `SECURE_SSL_REDIRECT` redirigiría sin fin (deducido del código; no probado con un proxy real) |
| `PLANIFICACION_DB_PATH` | `<raíz>/db.sqlite3` | Ruta de la base SQLite (WAL crea además `-wal` y `-shm` en la misma carpeta) | En la práctica sí: debe estar fuera del código y con respaldo |
| `PLANIFICACION_EVIDENCIAS` | `<raíz>/evidencias` | Carpeta de los adjuntos | En la práctica sí (incluir en el respaldo) |
| `PLANIFICACION_STATIC_ROOT` | `<raíz>/staticfiles` | Destino de `collectstatic`; nginx sirve `/static/` desde aquí | En la práctica sí |
| `PLANIFICACION_RESPALDOS` | Vacío | Carpeta por defecto de `respaldar` si no se pasa `--destino`; sin ninguna de las dos, el comando falla | Sí, para los respaldos |
| `PLANIFICACION_SIN_CLAVE` | Vacío (apagado) | Con `1` habilita `/acceso-rapido/` **solo en desarrollo**; en producción impide arrancar | **No debe existir** en producción |
| `PLANIFICACION_2FA` | Vacío | Con `1` exige segundo factor también en desarrollo; en producción siempre está activo | No |
| `PLANIFICACION_HOY` | Vacío | Fija «hoy» (`AAAA-MM-DD`) para mostrar un día del cierre; solo desarrollo (en producción se ignora) | No |
| `PLANIFICACION_RAIZ` | `/opt/planificacion/app` | Raíz del código; solo la leen `deploy/manage.sh` y `deploy/actualizar.sh` | Solo si se instala en otra ruta |
| `DJANGO_SETTINGS_MODULE` | `config.settings` | Lo fijan `manage.py` y `config/wsgi.py` si no está definida | No |

## 7.2 Qué cambia según el entorno

| Ajuste | Desarrollo | Producción |
|---|---|---|
| `DEBUG` | Verdadero | Falso |
| Secreto | Se crea un `.clave_secreta_local` si falta | Obligatorio por variable |
| Hosts permitidos | Lista local fija | Los de `DJANGO_ALLOWED_HOSTS` |
| HTTPS, cookies seguras, HSTS | No | Sí |
| Duración de la sesión | La de Django (por defecto) | 60 minutos sin actividad; se cierra con el navegador |
| Segundo factor | Apagado (salvo `PLANIFICACION_2FA=1`) | Siempre activo |
| `/acceso-rapido/` | Solo con `PLANIFICACION_SIN_CLAVE=1` | Imposible |
| `datos_de_ejemplo` | Permitido | Se niega |

## 7.3 Archivos de ejemplo

- `deploy/planificacion.env.example`: la plantilla completa para `/etc/planificacion/planificacion.env` (permisos 600, dueño `planificacion`): entorno, secreto, hosts, orígenes CSRF, proxy, base, adjuntos, estáticos y respaldos. Trae marcadores como `CAMBIAR-POR-UNA-CLAVE-LARGA-Y-UNICA` y el dominio de ejemplo `planificacion.example.cl`.
- `.env.example` (raíz): una versión reducida; no incluye adjuntos, estáticos ni respaldos.
- Ninguno lleva valores reales. El archivo real vive fuera del repositorio (`.env` está en `.gitignore`).

# 8. Operación

## 8.1 Comandos de `manage.py` propios

En el servidor se ejecutan con `sudo deploy/manage.sh <comando> ...` (carga el entorno de producción y corre como el usuario `planificacion`). En el computador local, `python manage.py <comando>`. Los comandos están en `nucleo/management/commands/`.

| Comando | Para qué | Opciones | Ejemplo |
|---|---|---|---|
| `crear_usuario` | Crea una cuenta con su rol y cargo. Para Gerente y administrador crea el segundo factor y muestra su clave **una sola vez** | `usuario` (posicional); `--rol` (obligatorio: `ADMIN_SISTEMA`, `GERENTE`, `JEFATURA`, `COLABORADOR`, `LECTURA`); `--nombre` (obligatorio); `--cargo` (obligatorio salvo administrador y solo lectura); `--correo`; `--desde AAAA-MM-DD` (desde cuándo ejerce el cargo; por defecto hoy) | `sudo deploy/manage.sh crear_usuario jefa --rol JEFATURA --nombre "Jefa de Control (ejemplo)" --cargo "Jefa de Control" --desde 2026-01-01` |
| `recuperar_acceso` | Clave nueva, quita el bloqueo por intentos y, si se pide, reinicia el segundo factor. Exige consola del servidor | `usuario`; `--reiniciar-2fa`; `--solo-desbloquear` | `sudo deploy/manage.sh recuperar_acceso gerente --reiniciar-2fa` |
| `respaldar` | Copia consistente de la base (API de respaldo de SQLite, sin detener la app) y de los adjuntos, con archivo de huellas SHA-256 | `--destino` (por defecto `PLANIFICACION_RESPALDOS`); `--conservar` (cuántos mantener, por defecto 30) | `sudo deploy/manage.sh respaldar --conservar 30` |
| `verificar_respaldo` | Prueba de restauración: comprueba la huella, restaura en una base temporal, revisa integridad y cadena de la bitácora y cuenta tareas, ocurrencias, eventos y usuarios | `archivo` (un `.sqlite3.gz`) | `sudo deploy/manage.sh verificar_respaldo /var/backups/planificacion/respaldo_20261117_023000.sqlite3.gz` |
| `verificar_bitacora` | Revisa la cadena de sellos; termina con error si hay eventos alterados | ninguna | `sudo deploy/manage.sh verificar_bitacora` |
| `cargar_plan` | Carga el plan desde un Excel (Planificación 2.0, Plan vigente o listado de 16 columnas); opcionalmente abre un mes y fija la gracia | `archivo`; `--aplicar`; `--confirmo-desactivar`; `--abrir-mes AAAA-MM`; `--desde AAAA-MM-DD`; `--inicio-uso AAAA-MM-DD`; `--dias-de-gracia` (21); `--cargo "TEXTO=CARGO"` (repetible); `--crear-cargos` (crea los cargos que traiga el Excel; necesario en una base nueva) | `sudo deploy/manage.sh cargar_plan /ruta/plan.xlsx --crear-cargos --aplicar --confirmo-desactivar` |
| `configurar_gracia` | Fija el inicio de uso y los días de gracia, o los apaga; sin opciones muestra el estado | `--inicio AAAA-MM-DD`; `--dias` (21); `--quitar` | `sudo deploy/manage.sh configurar_gracia --inicio 2026-11-01 --dias 21` |
| `datos_de_ejemplo` | Carga datos de **ejemplo**: el listado anterior y encima la Planificación 2.0, cuatro usuarios, 2026 abierto y noviembre de 2026 con avance simulado. Solo desarrollo | `--password` (obligatorio) | `python manage.py datos_de_ejemplo --password <clave-de-12-o-más-caracteres>` |
| `cargar_ejemplo_planificacion` | Ejemplo de la estructura de tres niveles: catálogo base de 11 procesos y Ventas con 3 tareas y 8 subtareas. Solo desarrollo y solo con la base sin procesos | ninguna | `python manage.py cargar_ejemplo_planificacion` |

Detalles que conviene conocer:

- **`crear_usuario`:** la clave se pide dos veces (con `getpass` si hay terminal, o por dos líneas de la entrada estándar). Se valida con las reglas de 12 o más caracteres. La asignación del cargo parte de `date.today()` (ver 13.2.2). El cargo indicado debe existir; si no, el comando se detiene.
- **`respaldar`:** deja `respaldo_AAAAMMDD_HHMMSS.sqlite3.gz`, `adjuntos_AAAAMMDD_HHMMSS.tar.gz` (solo si la carpeta de adjuntos no está vacía) y `respaldo_AAAAMMDD_HHMMSS.sha256`, con permisos 600 en una carpeta 700. Borra los conjuntos más antiguos según `--conservar`. No cifra ni copia fuera del servidor.
- **`cargar_plan`:** sin `--aplicar` solo muestra la vista previa. Se detiene si hay cargos que no existen. `--confirmo-desactivar` es obligatorio si el archivo desactivaría tareas. `--abrir-mes` exige el año abierto y `--desde` fija el comienzo de la medición. `--inicio-uso` configura la gracia.
- **`verificar_respaldo`:** ejecuta `verificar_bitacora` como subproceso sobre la base temporal y no toca la base en uso. Su salida es la evidencia que exige la puerta G3.

## 8.2 Otros comandos de Django que se usan

| Comando | Uso |
|---|---|
| `migrate --noinput` | Aplica las migraciones (siempre después de un `respaldar`) |
| `collectstatic --noinput` | Copia los estáticos a `PLANIFICACION_STATIC_ROOT` |
| `check --deploy` | Revisión de seguridad de producción (esperado: solo `security.W021`) |
| `shell -c "..."` | Tareas puntuales, como crear cargos o cambiar parámetros (ver 8.4) |
| `changepassword USUARIO` | La usa `cambiar_clave.bat` en el equipo local |
| `runserver 8000` | Solo desarrollo local |

## 8.3 Respaldo y restauración

**Qué hace hoy el kit:**

1. `respaldar` crea una copia consistente de la base y de los adjuntos, con huellas SHA-256, y limita la cantidad de copias.
2. `deploy/respaldo_diario.sh` lo ejecuta a diario (cron o temporizador de systemd, por ejemplo a las 02:30) con `--conservar 30` y, el día 1 de cada mes, ejecuta `verificar_respaldo` y guarda la salida en `/var/log/planificacion/restauracion.log`.
3. `verificar_respaldo` demuestra que un respaldo se puede abrir, que su integridad y la cadena de la bitácora están bien y cuánto contiene.

**Lo que falta completar (lo hace quien administra el servidor):** el cifrado de los archivos y la copia **fuera del servidor** están como líneas comentadas marcadas con ◆ en `deploy/respaldo_diario.sh`. Tal como se entrega, el script no cifra ni copia fuera.

**Restauración sobre la base en uso.** No existe un comando para eso (`verificar_respaldo` restaura solo en una base temporal). El siguiente procedimiento es una propuesta consistente con cómo se generan los respaldos y **no se ha probado en un servidor**:

```bash
sudo systemctl stop planificacion
# 1. guardar aparte la base actual y sus archivos -wal y -shm
# 2. restaurar la base y borrar los archivos -wal y -shm viejos
gunzip -c /var/backups/planificacion/respaldo_FECHA.sqlite3.gz | sudo -u planificacion tee /var/lib/planificacion/db.sqlite3 > /dev/null
sudo rm -f /var/lib/planificacion/db.sqlite3-wal /var/lib/planificacion/db.sqlite3-shm
# 3. restaurar los adjuntos (el tar contiene la carpeta «evidencias»)
sudo tar -xzf /var/backups/planificacion/adjuntos_FECHA.tar.gz -C /var/lib/planificacion
sudo systemctl start planificacion
sudo deploy/manage.sh verificar_bitacora
```

Antes de volver a una versión anterior del código, `docs/f1/08_guia_de_despliegue.md` (sección 9) indica restaurar el respaldo previo a la migración; `actualizar.sh` siempre respalda antes de migrar.

## 8.4 Puesta en marcha en un servidor nuevo: orden y advertencias

`docs/f1/08_guia_de_despliegue.md` describe la instalación del servicio, nginx y las cuentas. Probando los comandos sobre una base temporal aparecieron tres puntos que esa guía no cubre o contradice; por eso el **orden práctico** sería el siguiente (cada paso con su verificación pendiente en el servidor real):

| Paso | Qué hacer | Nota |
|---|---|---|
| 1 | Instalar, configurar variables y ejecutar `migrate`, `collectstatic`, servicio y nginx | Según la guía |
| 2 | **Crear los cargos al cargar el plan** | Una base recién migrada solo tiene el cargo «Contador»: `cargar_plan` sin `--crear-cargos` se detiene con «Hay cargos que no existen». Con `--crear-cargos` (primero sin `--aplicar` para ver la lista) se crean los cargos del Excel. |
| 3 | `cargar_plan ARCHIVO --crear-cargos` y luego `--crear-cargos --aplicar --confirmo-desactivar` | Sin `--abrir-mes` todavía (el año 2026 aún no está abierto) |
| 4 | Crear las cuentas con `crear_usuario ... --desde 2026-01-01` | Entregar en privado la clave del segundo factor de Gerente y administrador. `--desde` evita el problema de `Asignacion.desde` (ver 13.2.2) |
| 5 | (Solo si se crearon cuentas sin `--desde` o desde el Mantenedor) **ajustar `Asignacion.desde`** | Esas cuentas toman la fecha de hoy; si se abre un mes desde una fecha anterior la tarea no se genera (aviso `sin_responsable`). Ejemplo: `sudo deploy/manage.sh shell -c "from datetime import date; from nucleo.models import Asignacion; Asignacion.objects.update(desde=date(2026, 1, 1))"` |
| 6 | Con el Gerente ya ingresado: en «Abrir mes» cargar los feriados del año, confirmarlos y abrir el año; luego abrir el mes con la fecha de comienzo | 2027 y 2028 ya vienen cargados; 2026 no |
| 7 | `configurar_gracia --inicio AAAA-MM-DD --dias 21` | Se puede ejecutar antes o después de abrir el mes (recalcula las ocurrencias existentes) |
| 8 | Revisar «Matriz del cierre» y «Mi día»; `respaldar` y `verificar_respaldo`; `verificar_bitacora` | Insumo de la lista de aceptación |

Como alternativa al paso 6, `cargar_plan --abrir-mes AAAA-MM --desde AAAA-MM-DD` abre el mes desde la consola, pero solo funciona si el año ya está abierto.

## 8.5 El kit `deploy/` y la guía de despliegue

La guía operativa completa es `docs/f1/08_guia_de_despliegue.md` (no se copia aquí). Resumen:

| Archivo | Qué hace |
|---|---|
| `planificacion.service` | Unidad systemd: usuario y grupo `planificacion`; `EnvironmentFile=/etc/planificacion/planificacion.env`; gunicorn con `config.wsgi:application`, `--bind 127.0.0.1:8010`, `--workers 2`, `--timeout 60`; reinicio ante fallas; `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`, `UMask=0077` y escritura solo en `/var/lib/planificacion`, `/var/backups/planificacion` y `/var/log/planificacion` |
| `nginx-planificacion.conf` | Redirige HTTP a HTTPS; `client_max_body_size 12m`; `server_tokens off`; sirve `/static/` desde `/var/www/planificacion/static/`; el resto va a `127.0.0.1:8010` con `Host`, `X-Forwarded-Proto` y `X-Forwarded-For`; los adjuntos **no** se sirven desde nginx; las líneas del certificado quedan para `certbot` |
| `planificacion.env.example` | Plantilla de variables (7.3) |
| `manage.sh` | Carga el archivo de entorno y ejecuta `manage.py` con `sudo -E -u planificacion` |
| `actualizar.sh` | Seis pasos: respaldo, código (`git fetch`, `checkout`, `pull --ff-only`), dependencias (`pip install -r requirements.lock.txt`), migraciones, estáticos, y reinicio con `check --deploy` y `verificar_bitacora` |
| `respaldo_diario.sh` | Ver 8.3 |

Lista de aceptación para la puerta G3 (sección 7 de la guía): 12 controles, **todos pendientes**: la app no arranca sin secreto ni dominios; HTTPS y `check --deploy`; `/acceso-rapido/` da 404; claves de 12 caracteres y bloqueo; segundo factor obligatorio; cada rol ve lo suyo; respaldo diario con copia externa; **restauración probada**; bitácora íntegra; plan cargado con la fecha de comienzo; aprobación escrita de la dueña del producto; aceptación del administrador del servidor.

## 8.6 Puesta en marcha local (datos de ejemplo)

Pensada para el computador de la dueña del producto, sin clave:

| Archivo | Qué hace |
|---|---|
| `iniciar_local.bat` (Windows) | Crea `.venv` si falta, instala `requirements.txt`, crea `.entorno_desarrollo`, fija `PLANIFICACION_DB_PATH` (`db_local.sqlite3`), `PLANIFICACION_HOY=2026-11-09` y `PLANIFICACION_SIN_CLAVE=1`, ejecuta `migrate`, carga `datos_de_ejemplo` si la base es nueva, abre el navegador y levanta `runserver 8000` |
| `iniciar_local.sh` | Lo mismo para Linux o Mac (`--preparar` deja todo listo sin abrir el servidor) |
| `levantar_local.py` | Lo mismo en Python; lo usa `.claude/launch.json` (que apunta a `.venv/Scripts/python.exe`, es decir, a Windows) |
| `cambiar_clave.bat` | Cambia la clave de un usuario local con `changepassword` y le quita el bloqueo |

Los usuarios de ejemplo son `gerente`, `jefa`, `contadora` y `asistente`; la clave de ejemplo está en `LEEME.txt`. Se simula que hoy es el lunes 09-11-2026. Para empezar de cero se borra `db_local.sqlite3`. `datos_de_ejemplo` **no** configura la gracia de arranque. Ver 13.1: estos archivos nunca se ejecutaron en Windows.

# 9. Pruebas

## 9.1 Cómo correr la suite

Desde la raíz del repositorio, con el entorno virtual `.venv` (Linux o Mac):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # o requirements.lock.txt para las versiones fijadas
PLANIFICACION_ENTORNO=desarrollo .venv/bin/python -m pytest -q
```

Resultado verificado el 17-11-2026 (Linux, Python 3.13.17, Django 6.1.1, pytest 9.2.0): **726 pruebas, todas pasan, en 134,77 segundos** (2 min 15 s). En Windows el comando equivalente es `.venv\Scripts\python -m pytest -q`; **no se ha ejecutado en Windows**.

Ejemplos útiles: `python -m pytest pruebas/test_kpi.py -q` (un archivo), `python -m pytest -k gracia -q` (por nombre), `python -m pytest --collect-only -q` (lista las pruebas sin correrlas).

Cómo está montada (`pytest.ini` y `conftest.py`):

- `pytest.ini`: `DJANGO_SETTINGS_MODULE = config.settings`, `python_files = test_*.py`, `testpaths = pruebas`.
- `conftest.py` fija `PLANIFICACION_ENTORNO=desarrollo` si no hay variable (así la configuración es de desarrollo durante las pruebas) y reemplaza el hash de claves por MD5 solo durante las pruebas, porque se crean muchos usuarios. Aun así conviene escribir la variable en el comando, como arriba.
- pytest-django crea una base de pruebas aplicando las migraciones reales; por eso, en una base de pruebas ya existen los grupos de rol, los feriados de 2027 y 2028 y el cargo «Contador».
- `pruebas/ayudas.py` ofrece fábricas sin personas reales: `cargo`, `persona`, `tarea`, `anio_abierto`, `usuario_con_rol`.
- `test_operacion.py` prueba los comandos como se usan: lanza `manage.py` como subproceso sobre una base temporal (fixture `servidor`).
- Algunas pruebas usan los Excel de `docs/datos/` (`test_plan2.py`, `test_importador.py`, `test_comandos.py`).

## 9.2 Mapa de archivos de prueba

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `test_acceso.py` | 6 | Ingreso, bloqueo por intentos fallidos, no revelar si el usuario existe, registro en la bitácora |
| `test_acceso_rapido.py` | 9 | Modo sin clave: apagado por defecto, solo en desarrollo, en producción impide arrancar, la ruta no existe con el modo apagado |
| `test_segundo_factor.py` | 13 | TOTP: falla cerrada para Gerente y administrador, código de un solo uso, tolerancia de 30 s, bloqueo tras 5 errores, siempre activo en producción, cambio de clave de 12 caracteres |
| `test_auditoria.py` | 6 | Bitácora solo-agregar, sello encadenado, triggers que impiden `UPDATE` y `DELETE`, detección de una fila alterada |
| `test_operacion.py` | 8 | Comandos de servidor: `crear_usuario`, `recuperar_acceso`, `respaldar`, `verificar_respaldo`, respaldo alterado, `cargar_plan` sin cargos |
| `test_comandos.py` | 7 | Roles como grupos, reloj de desarrollo y `datos_de_ejemplo` (solo desarrollo) |
| `test_calendario.py` | 15 | Días hábiles, feriados, DH00 a DH10 y los hitos del cierre |
| `test_calendario_inicio.py` | 3 | El calendario no retrocede antes del primer mes abierto |
| `test_recurrencia.py` | 27 | Motor de recurrencia: regla más mes igual a fechas |
| `test_reglas_texto.py` | 15 | La periodicidad en palabras |
| `test_feriados_parametros.py` | 10 | Propuesta de feriados, confirmación y parámetros |
| `test_periodos.py` | 15 | Abrir mes: vista previa, idempotencia, copia de responsable y regla, avisos |
| `test_abrir_mes.py` | 15 | Pantalla Abrir mes: feriados confirmados, avisos, solo Gerente y administrador |
| `test_semana_del_cierre.py` | 6 | Pausar o reasignar entre DH01 y DH10 |
| `test_gracia.py` | 8 | Gracia de arranque: `vence_el`, «Por registrar», registrar dentro de la gracia |
| `test_ejecucion.py` | 36 | Marcar, revisar, devolver, recibir y «no aplica», con segregación de funciones en el servidor |
| `test_reasignar.py` | 14 | Cambiar quién ejecuta una tarea |
| `test_horas_reales.py` | 29 | Horas reales y comparación con las estimadas |
| `test_evidencias.py` | 32 | Adjuntos: tipos, firma, tamaño, permisos y entrega segura |
| `test_vista_hoy.py` | 13 | Mi día: lo propio, lo que se revisa y recibe, acciones por POST |
| `test_checklist.py` | 12 | Mi día, Mi semana, Mi mes con el cumplimiento a la vista |
| `test_checklist_cargos.py` | 5 | Check List por cargo y responsable |
| `test_detalle.py` | 13 | Detalle de la tarea: datos, historial, comentarios, acciones por perfil |
| `test_kpi.py` | 27 | KPI: a tiempo, tarde, devuelta, «no aplica», externos, muestra insuficiente (fechas de `America/Santiago`) |
| `test_informes.py` | 30 | Panel del cierre y Cumplimiento por colaborador |
| `test_tablero_cronograma.py` | 12 | Tablero de estados y cronograma |
| `test_carga.py` | 16 | Carga estimada contra capacidad y carga del cierre por día |
| `test_matriz.py` | 29 | Matriz del cierre: jornada 9/5 h, tope del Gerente, semana del cierre, propuesta de equilibrio |
| `test_matriz_pantalla.py` | 10 | Pantalla y descarga de la matriz |
| `test_importador.py` | 44 | Importador del Excel: conversión de reglas, vista previa, aplicación, idempotencia |
| `test_plan2.py` | 42 | Planificación 2.0: carga del Excel de tres hojas; la matriz reproduce su tabla de carga día por día |
| `test_excel_masivo.py` | 36 | Descarga y carga masiva de tareas y procesos |
| `test_vistas_excel_masivo.py` | 17 | Pantallas de descarga y carga masiva |
| `test_mantenedor_tareas.py` | 32 | Servicios del Mantenedor de procesos y tareas |
| `test_mantenedor_usuarios.py` | 18 | Servicios del Mantenedor de usuarios |
| `test_vistas_mantenedor.py` | 38 | Pantallas de Tareas, Procesos y Usuarios |
| `test_estructura.py` | 30 | Estructura de tres niveles: códigos, reordenar, dependencias, historial |
| `test_vistas_estructura.py` | 28 | Árbol y tabla, filtros, exportación, procesos con orden y dependencias |
| **Total** | **726** | |

Los conteos salen de `pytest --collect-only` (incluyen casos parametrizados). Hay 38 archivos de pruebas.

## 9.3 Lo que la suite no demuestra

Ver 13.1: los navegadores reales, HTTPS tras nginx, una aplicación de códigos en un teléfono real, el kit `deploy/` en un servidor, Windows, carga concurrente y el respaldo fuera del servidor no están cubiertos.

# 10. Mapa de pantallas y rutas

Las rutas están en `nucleo/urls.py` (más `/admin/` en `config/urls.py`). Todas exigen sesión salvo `/ingresar/`; una persona sin sesión es enviada a `/ingresar/`. «Con perfil» significa cualquiera de los cinco roles; una cuenta sin rol recibe 403 (`sin_perfil.html`). Las plantillas están en `nucleo/templates/nucleo/`.

| URL | Nombre | Vista | Plantilla | Quién entra |
|---|---|---|---|---|
| `/` | `inicio` | `views.inicio` | (redirige a Mi día) | Con sesión |
| `/ingresar/` | `login` | `LoginView` con `FormularioDeIngreso` | `login.html` | Público |
| `/salir/` | `logout` | `LogoutView` (solo POST) | (redirige a `/ingresar/`) | Con sesión |
| `/acceso-rapido/` | `acceso_rapido` | `views.acceso_rapido` | `acceso_rapido.html` | Solo con el modo sin clave (desarrollo); si no, 404 |
| `/cuenta/segundo-factor/` | `segundo_factor` | `views_cuenta.segundo_factor_vista` | `segundo_factor.html` | Con sesión; si el rol no lo exige, redirige a Mi día |
| `/cuenta/clave/` | `cambiar_clave` | `PasswordChangeView` | `cambiar_clave.html` | Con sesión |
| `/cuenta/clave/lista/` | `clave_cambiada` | `views_cuenta.clave_cambiada` | (registra en bitácora y redirige) | Con sesión |
| `/checklist/dia/` | `hoy` | `views.hoy` | `hoy.html` | Con perfil (`?persona=` para ver a otra persona) |
| `/checklist/semana/` | `semana` | `views.semana` | `semana.html` | Con perfil (`?fecha=`, `?persona=`) |
| `/checklist/mes/` | `mes` | `views.mes` | `mes.html` | Con perfil (`?mes=AAAA-MM`, `?persona=`) |
| `/checklist/cargos/` | `checklist_cargos` | `views_checklist_cargos.cargos` | `checklist_cargos.html` | Con perfil |
| `/tareas/<pk>/` | `detalle_ocurrencia` | `views.detalle` | `detalle.html` | Con perfil; las acciones dependen de cada persona |
| `/ocurrencias/<pk>/<accion>/` | `ocurrencia_accion` | `views.ocurrencia_accion` (solo POST) | (redirige a la página de origen) | Con sesión; el permiso se valida en el servicio. Acciones: `hecha`, `recibida`, `revisar`, `devolver`, `bloquear`, `retomar`, `comentar`, `horas`, `reasignar`, `tomar` |
| `/evidencias/<pk>/` | `evidencia` | `views.evidencia` | (entrega el archivo) | Quien puede ver ese adjunto (6.2) |
| `/informes/panel/` | `informe_panel` | `views_informes.panel` | `informe_panel.html` | Con perfil (`?mes=`, `?ver=`, `?fecha=`) |
| `/informes/cumplimiento/` | `informe_cumplimiento` | `views_informes.cumplimiento` | `informe_cumplimiento.html` | Con perfil |
| `/informes/tablero/` | `informe_tablero` | `views_informes.tablero` | `informe_tablero.html` | Con perfil (`?proceso=`, `?solo_mias=1`) |
| `/informes/cronograma/` | `informe_cronograma` | `views_informes.cronograma` | `informe_cronograma.html` | Con perfil (`?vista=cierre`, `semana` o `mes`) |
| `/informes/carga/` | `informe_carga` | `views_informes.carga_del_equipo` | `informe_carga.html` | Con perfil |
| `/informes/matriz/` | `informe_matriz` | `views_informes.matriz_del_cierre` | `informe_matriz_plan.html`; con `?ver=propuesta`, `informe_matriz.html` | `GERENTE`, `JEFATURA` |
| `/informes/matriz/exportar/` | `informe_matriz_exportar` | `views_informes.matriz_exportar` | (Excel) | `GERENTE`, `JEFATURA` |
| `/planificacion/` | `planificacion` | `views_planificacion.planificacion` | `planificacion.html` | Con perfil (`?vista=tabla` o árbol, y filtros) |
| `/planificacion/exportar/` | `planificacion_exportar` | `views_planificacion.planificacion_exportar` | (Excel) | `GERENTE`, `JEFATURA` |
| `/cierre/abrir/` | `abrir_mes` | `views_apertura.abrir_mes` | `abrir_mes.html` | `GERENTE`, `ADMIN_SISTEMA` |
| `/mantenedor/tareas/` | `mant_tareas` | `views_mantenedor.tareas` | `mant_tareas.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/tareas/nueva/` | `mant_tarea_nueva` | `views_mantenedor.tarea_nueva` | `mant_tarea_form.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/tareas/<pk>/` | `mant_tarea_editar` | `views_mantenedor.tarea_editar` | `mant_tarea_form.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/tareas/exportar/` | `mant_tareas_exportar` | `views_mantenedor.tareas_exportar` | (Excel de 16 columnas) | `GERENTE`, `JEFATURA` |
| `/mantenedor/tareas/plan-vigente/` | `mant_plan_vigente_exportar` | `views_mantenedor.plan_vigente_exportar` | (Excel «Plan vigente») | `GERENTE`, `JEFATURA` |
| `/mantenedor/tareas/cargar/` | `mant_tareas_cargar` | `views_mantenedor.tareas_cargar` | `mant_tareas_cargar.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/procesos/` | `mant_procesos` | `views_mantenedor.procesos` | `mant_procesos.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/procesos/<pk>/` | `mant_proceso_detalle` | `views_mantenedor.proceso_detalle` | `mant_proceso_detalle.html` | `GERENTE`, `JEFATURA` |
| `/mantenedor/procesos/exportar/` | `mant_procesos_exportar` | `views_mantenedor.procesos_exportar` | (Excel) | `GERENTE`, `JEFATURA` |
| `/mantenedor/procesos/cargar/` | `mant_procesos_cargar` | `views_mantenedor.procesos_cargar` (solo POST) | (redirige) | `GERENTE`, `JEFATURA` |
| `/mantenedor/usuarios/` | `mant_usuarios` | `views_mantenedor.usuarios` | `mant_usuarios.html` | `GERENTE`, `ADMIN_SISTEMA` |
| `/mantenedor/usuarios/nuevo/` | `mant_usuario_nuevo` | `views_mantenedor.usuario_nuevo` | `mant_usuario_form.html` | `GERENTE`, `ADMIN_SISTEMA` |
| `/mantenedor/usuarios/<pk>/` | `mant_usuario_editar` | `views_mantenedor.usuario_editar` | `mant_usuario_form.html` | `GERENTE`, `ADMIN_SISTEMA` |
| `/admin/` | (Django) | `admin.site.urls` | (admin de Django) | Cuentas `is_staff`; no hay modelos propios registrados |

Menú lateral (`base.html`): Informes (Panel del cierre, Tablero, Cronograma, Cumplimiento por colaborador, Carga del equipo y, para Gerente y Jefatura, Matriz del cierre), Planificación (Árbol y tabla), Check List (Mi día, Mi semana, Mi mes, Por cargo y responsable), Cierre mensual (Abrir mes, para Gerente y administrador) y Mantenedor (Tareas y Procesos para Gerente y Jefatura; Usuarios para Gerente y administrador).

# 11. Cómo extender

Antes de tocar nada: correr la suite (`python -m pytest -q`) y dejar el ejemplo de cada cambio con su prueba. La regla de la casa: **la regla de negocio va en un servicio, la vista solo la llama**, y todo cambio relevante se registra con `auditoria.registrar`.

## 11.1 Agregar un tipo de regla de recurrencia

Ejemplo: una regla nueva `QUINCENAL`.

1. **Motor** (`nucleo/servicios/recurrencia.py`): agregar el nombre a `TIPOS` y una rama en `fechas_limite`. Si necesita un parámetro nuevo, agregarlo a la clase `Regla`.
2. **Modelo** (`nucleo/models.py`): `Tarea.regla_tipo` toma sus opciones de `TIPOS`, así que hay que generar una migración (`python manage.py makemigrations nucleo -n tipo_de_regla_quincenal`). Si hay un parámetro nuevo, agregar un campo `regla_*` a `Tarea`, a `Tarea.regla()` y a `periodos._regla_a_dict`.
3. **Texto**: `nucleo/servicios/reglas_texto.py`, función `describir`.
4. **Excel de ida y vuelta**: `importador.convertir_regla` (qué «Periodicidad» y «Cuándo» producen la regla) y `excel_masivo.texto_de_periodicidad` (cómo se escribe de vuelta). Deben ser inversas: lo descargado debe poder volver a cargarse sin cambios.
5. **Mantenedor**: `mantenedor._validar` y `ejecuciones_por_mes`; el formulario (`views_mantenedor.TIPOS`, `_valores_de`, `_valores_de_post`, `_datos_de` y `mant_tarea_form.html`).
6. **Abrir mes**: agregar el tipo a `views_apertura.ORDEN_TIPOS` (el resumen la ordena con `ORDEN_TIPOS.index(...)`; un tipo que falte aquí provoca un error al mostrar la vista previa).
7. **Clasificación**: si es una regla del cierre, `kpi.TIPOS_DE_CIERRE`; si es de operación, `carga.OPERACION` y `matriz.OPERACION` o `matriz.CIERRE`.
8. **Pruebas**: `test_recurrencia.py` (con feriados y fines de semana), `test_reglas_texto.py`, `test_importador.py`, `test_mantenedor_tareas.py`, `test_periodos.py`.

## 11.2 Agregar una pantalla

1. **Servicio**: la lógica y los permisos en `nucleo/servicios/<modulo>.py` (`permisos.rol_de`, `PermisoDenegado`, `ErrorDeNegocio`) y el registro en la bitácora.
2. **Vista**: en el `nucleo/views_*.py` que corresponda, con `@login_required` o `@con_roles(...)` (definido en `views_mantenedor.py`). Si la pantalla es para todo el equipo, devolver `_sin_perfil` cuando la cuenta no tiene rol.
3. **Plantilla**: un archivo nuevo en `nucleo/templates/nucleo/` que extienda `nucleo/base.html`; los formularios llevan `{% csrf_token %}`.
4. **Ruta**: una línea en `nucleo/urls.py` con su `name`.
5. **Menú**: un enlace en `base.html` y, si depende del rol, una bandera nueva en `contexto.menu`.
6. **Descargas de Excel**: escribir con `excel_masivo._poner` (un texto que empieza con `=`, `+`, `-` o `@` no se vuelve fórmula), responder con `Cache-Control: no-store` y registrar la descarga.
7. **Pruebas**: con `pruebas/ayudas.py` (`usuario_con_rol`) y el cliente de pruebas de Django; incluir los casos negativos (403 por rol y por servicio).

## 11.3 Agregar un campo a `Tarea` con migración

Ejemplo: `centro_costo`.

1. **Modelo y migración**: agregar el campo en `nucleo/models.py`, luego `python manage.py makemigrations nucleo -n campo_centro_costo`, revisar el archivo generado en `nucleo/migrations/` y `python manage.py migrate`. En el servidor, `deploy/actualizar.sh` respalda antes de migrar.
2. **Mantenedor**: `mantenedor.DatosTarea`, `_validar`, `_aplicar` e `_instantanea` (esta última alimenta el antes y el después de la bitácora); en `views_mantenedor.py`: `_valores_de`, `_valores_de_post`, `_datos_de`; y el campo en `mant_tarea_form.html`.
3. **Leer desde Excel**: `importador.FilaImport`, `leer_excel`, `_valores_base` o `_valores_plan2`, y **`_valores_actuales`** (si el campo no está ahí, la vista previa no detecta sus cambios); para la Planificación 2.0 y el Plan vigente, `plan2.leer` y `plan2.leer_plan_vigente`.
4. **Escribir a Excel**: `excel_masivo.ENCABEZADOS` y `exportar_tareas`; y `plan_vigente.COLUMNAS`, `ANCHOS` y la lista de valores (deben tener la misma cantidad de elementos). Agregar la etiqueta en `views_mantenedor.ETIQUETAS_DE_CAMPO` para que la vista previa la muestre con nombre legible.
5. **Si debe quedar congelado al generar el mes**, copiarlo a `Ocurrencia` (campo, migración y asignación en `periodos.abrir_mes`), igual que `minutos_estimados`.
6. **Pruebas**: `test_mantenedor_tareas.py`, `test_importador.py` y `test_excel_masivo.py` (la descarga debe poder recargarse sin cambios).

## 11.4 Agregar un KPI

1. **Cálculo** en `nucleo/servicios/kpi.py`, como función pura sobre las ocurrencias de un período y la fecha de hoy. Usar `Ocurrencia.exigible` (no `fecha_limite`, para respetar la gracia), excluir `no_aplica` y los cargos externos cuando corresponda, y decir «sin datos» en vez de inventar.
2. **Umbrales**: como parámetros en `parametros.INICIALES` (valor, estado y nota), leídos con `parametros.entero`; un valor supuesto va como `pendiente_confirmar`.
3. **Presentación**: textos y clases en `presentacion.py` (siempre con palabra además del color).
4. **Pantalla**: función en `views_informes.py` (`@login_required` y `_sin_perfil`), plantilla `informe_*.html`, ruta y menú (11.2).
5. **Pruebas**: `test_kpi.py` (con fechas de `America/Santiago`) y `test_informes.py`.

## 11.5 Otros cambios frecuentes

| Cambio | Dónde |
|---|---|
| Renombrar o reordenar cargos | `importador.NOMBRES_DE_CARGO` y `ORDEN_CARGOS` (para lo nuevo) y una migración de datos (para lo existente; ver `0009_nombres_de_cargos`, `0016_plan_2_0`) |
| Cambiar la jornada | `calendario.JORNADA_HORAS` (y `Cargo.horas_mes_max` para topes) |
| Cambiar el techo de planificación | `matriz.TECHO_POR_DH` |
| Nuevo comando de operación | Archivo en `nucleo/management/commands/`, con prueba al estilo de `test_operacion.py` |
| Nuevo parámetro | `parametros.INICIALES`; no hay pantalla (ver 4.12) |
| Nuevo rol o permiso | `permisos.py` (constantes, `ROLES`, `QUE_MARCAN`), una migración que cree el grupo (ver `0005_roles`), y la validación en el servicio correspondiente |

# 12. Decisiones y puertas relevantes

Fuente: `docs/f1/00_decisiones_y_gates.md` (DEC-01 a DEC-43). Aquí solo un resumen por tema; las decisiones reemplazadas se indican con una flecha.

## 12.1 Decisiones por tema

| Tema | Decisiones | Resumen |
|---|---|---|
| Stack y despliegue | DEC-03, DEC-12, DEC-13 | El stack lo eligió el equipo de diseño: Django con plantillas del servidor, SQLite con WAL, gunicorn y nginx, como el Arqueo de Caja (ADR-001 en `docs/f1/01_arquitectura_adr.md`). Despliega y mantiene el administrador del servidor. Nombre oficial de la aplicación |
| Equipo y cargos | DEC-01, DEC-20, DEC-39, DEC-43 | Cuatro cargos del equipo (Gerente AyF, Jefa de Control, Contador Senior, Analista Contable) en ese orden, más el cargo «Contador» desde el 17-11-2026; los externos van después |
| Calendario y cierre | DEC-05 → DEC-15 → DEC-26 → DEC-35 | DH08, DH09 y DH10 son **días hábiles**; DH00 es el último hábil del mes anterior; las semanas del cierre van de DH01 a DH10 |
| Feriados | DEC-11, DEC-31 | Se cargan desde una librería y una persona los confirma; 2027 y 2028 vienen cargados |
| Jornada | DEC-14 → DEC-27 | Lunes a jueves 9 h y viernes 5 h; el Gerente AyF dedica un máximo de 80 h al mes |
| Responsables y revisión | DEC-06, DEC-08 → DEC-17, DEC-34 → DEC-36 | Los externos no están en el KPI y se marcan «Recibido» por quien recibe; revisa el cargo que dice el Excel; la revisión va dentro de las horas de quien ejecuta |
| Estados y horas | DEC-16, DEC-09 → DEC-18, DEC-22 | Estado «Bloqueada» con motivo; tiempos estimados por tarea; horas reales anotadas por quien ejecuta |
| Estructura y códigos | DEC-19, DEC-21, DEC-23 → DEC-25, DEC-38 | Procesos en el orden del Excel; código `OO-PPP.TT.SSS` de tres niveles; si un código mezcla procesos, manda el nombre del proceso |
| Excel | DEC-24, DEC-37, DEC-40, DEC-41 | Descarga y carga masiva; la Planificación 2.0 es el plan vigente; el Plan vigente se descarga y se recarga; las tareas de 9 minutos pasan a 10 |
| Semana del cierre y matriz | DEC-28, DEC-29, DEC-33 | Cada tarea puede quedar igual, pausarse o reasignarse en las semanas del cierre; la matriz muestra el plan y la propuesta de equilibrio es opcional |
| Adjuntos y pantallas | DEC-30, DEC-32 | Documentos adjuntos a los comentarios; mejoras de pantalla del QA |
| Flexibilidad | DEC-41 | Cualquier persona del equipo puede cambiar quién ejecuta una tarea mientras no esté hecha |
| Seguridad y operación | DEC-10, DEC-42 | Permisos de la Jefatura (edita procesos y tareas); segundo factor obligatorio para Gerente y administrador; comandos de operación y kit `deploy/` |
| Gracia de arranque | DEC-43 | Medición desde el 01-11-2026 con tres semanas de gracia, hasta el 22-11-2026 |
| Parámetros por delegación | (sección 1 de `00_decisiones_y_gates.md`) | Umbral ámbar 90 %, plazo de revisión 1 día hábil y muestra mínima 10, marcados «pendiente de confirmar» |

Preguntas de la fase de diseño ya resueltas que afectan el código: P1 (el Gerente revisa las tareas de la Jefa; se logra con los datos, no con una regla fija en el código), P4 (el día 13 se ajusta al hábil anterior, pendiente de confirmar la norma de Previred) y P7 (medición desde el 05-11; luego reemplazada por el 01-11 de DEC-43).

## 12.2 Registro de puertas

| Puerta | Qué es | Estado |
|---|---|---|
| G0 | Nota de comprensión | Aprobada con condiciones (30-10-2026) |
| G1 | Diseño de `docs/f1/` | Aprobada con condiciones (30-10-2026), interpretada a partir de las respuestas de la dueña del producto |
| G2 | Construcción en un ambiente de prueba | No solicitada |
| **G3** | **Producción en el servidor** | **No solicitada ni aprobada.** Exige la aprobación escrita de la dueña del producto, la del administrador del servidor, la restauración de un respaldo probada y la lista de 12 controles de la sección 7 de `docs/f1/08_guia_de_despliegue.md` |

Aprobar G1 no autoriza producción ni cargar datos reales en un servidor. Regla de trabajo vigente (`CLAUDE.md`): se construye y prueba primero en el computador local con datos de ejemplo; la seguridad con claves va en las etapas finales, justo antes del despliegue; el modo sin clave debe ser imposible en producción (falla cerrada).

## 12.3 Pendientes registrados

- Aprobación G3 y prueba del kit en el servidor real.
- Confirmar los feriados 2027 y 2028 cargados desde la librería (la persona responsable los revisa en «Abrir mes»).
- Parámetros marcados «pendiente de confirmar» (4.12).
- Confirmar con la norma vigente el ajuste del día 13 (Previred): hoy el hábil anterior.
- Confirmar las siglas propuestas de los procesos, las dependencias del catálogo base y el tratamiento de algunos cargos como externos.
- Retención de respaldos (propuesta: 30 diarios) y de bitácora (propuesta: 5 años), por confirmar.
- Supuestos de DEC-41: el responsable «de persona» del Excel debe ser un cargo; las tareas trimestrales y anuales se resolvieron en DEC-43 (anuales en enero, trimestral desde marzo).
- Tareas sin revisor: la aplicación las muestra como «Sin revisor» y no las corrige.

# 13. Límites conocidos y qué no se ha probado

## 13.1 Lo que no se ha probado

| Qué | Estado | Evidencia o motivo |
|---|---|---|
| Windows | **Nada se ejecutó en Windows.** `iniciar_local.bat`, `cambiar_clave.bat` y `.claude/launch.json` (que apunta a `.venv/Scripts/python.exe`) nunca fueron ejecutados por el asistente | `docs/TRASPASO.md`; la suite se corrió solo en Linux |
| `iniciar_local.sh` y `levantar_local.py` | No se ejecutaron en esta verificación | Solo se leyeron; el comando `datos_de_ejemplo` que usan sí está cubierto por `test_comandos.py` |
| Kit `deploy/` en un servidor real | **Nunca se corrió**: ni la unidad systemd, ni nginx, ni certbot, ni `manage.sh`, `actualizar.sh` o `respaldo_diario.sh` | `docs/f1/08_guia_de_despliegue.md`. Los comandos que usa sí se probaron en desarrollo (`test_operacion.py`) |
| `check --deploy` | Corrido **solo en local** con variables de producción de prueba: una advertencia (`security.W021`). No se corrió en el servidor | Esta verificación |
| HTTPS, cookies seguras, HSTS y proxy | Solo configuración revisada; no se probó tras nginx ni con certificado. La condición de `DJANGO_PROXY_SSL` está deducida del código | — |
| Segundo factor con un teléfono real | **No probado con una aplicación de códigos real.** Las pruebas generan los códigos con PyOTP. El código QR nunca se ejercitó: la librería `qrcode` no está en `requirements.lock.txt` ni en el entorno virtual | `test_segundo_factor.py` |
| Respaldo fuera del servidor y cifrado | Son marcadores (◆) en el script, sin implementar | `deploy/respaldo_diario.sh` |
| Restauración sobre el servidor | Solo existe la prueba de restauración en base temporal; el procedimiento completo no se ha ejecutado | 8.3 |
| Actualización con `actualizar.sh` | No probada (por ejemplo, `git pull --ff-only` cuando `VERSION` es una etiqueta) | — |
| Carga y concurrencia | Sin pruebas de carga. SQLite con 2 procesos de gunicorn y escrituras serializadas por `transaction_mode IMMEDIATE`; diseñado para un equipo pequeño | ADR-001 |
| PostgreSQL | No usado ni probado | ADR-001 |
| Navegadores y accesibilidad | Sin pruebas automáticas en navegadores ni auditoría de accesibilidad | — |
| Datos reales | Nada se ha cargado con datos reales en ningún servidor. Las pruebas usan los Excel de `docs/datos/` y datos de ejemplo | `docs/TRASPASO.md` |
| Feriados 2026 en producción | No se cargan por migración; dependen del paso en «Abrir mes» | 4.1 |

## 13.2 Hallazgos de la verificación (el código no coincide con la guía o con el diseño)

Estos puntos salieron de leer el código y de varios experimentos desechables sobre una base temporal (escritos fuera del repositorio). No se modificó ningún archivo del repositorio.

### 13.2.1 En una base nueva no existen los cargos (verificado; corregido con `--crear-cargos`)

`cargar_plan` se detenía con «Hay cargos que no existen en la app» porque una base recién migrada solo trae el cargo «Contador» (migración `0019`), y `crear_usuario` exige el cargo. **Corregido** el 17-11-2026: `cargar_plan --crear-cargos` crea los cargos del Excel (prueba `test_en_una_base_nueva_el_comando_pide_crear_los_cargos_y_con_la_opcion_los_crea`) y la guía `docs/f1/08_guia_de_despliegue.md` quedó con el orden correcto.

### 13.2.2 `Asignacion.desde` parte de «hoy» y puede impedir abrir un mes pasado (verificado; mitigado con `--desde`)

`crear_usuario` usa `date.today()` y el Mantenedor usa `reloj.hoy()` como inicio de la asignación del cargo. `periodos.vista_previa` exige una persona vigente **en cada fecha** que va a generar: con cuentas creadas el 17-11 y un mes abierto desde el 01-11, las fechas anteriores no tienen responsable, aparece el aviso `sin_responsable` y la tarea **no se genera** (se comprobó: una tarea diaria dio 0 ocurrencias con el aviso «no tiene persona vigente el 02-11-2026»). Salida: ajustar `desde` (8.4, paso 5).

**Mitigado** el 17-11-2026: `crear_usuario` acepta `--desde AAAA-MM-DD` (prueba `test_crear_usuario_permite_fijar_desde_cuando_ejerce_el_cargo`) y la guía lo exige. Sigue pendiente que el Mantenedor permita elegir esa fecha.

### 13.2.3 `cargar_plan --abrir-mes` necesita el año abierto

Por el código de `periodos.vista_previa`, el comando falla con «No pude abrir el mes» si el año no está abierto, y el plan ya quedó aplicado. 2026 no viene cargado por migración, de modo que primero se deben cargar, confirmar y abrir los feriados en «Abrir mes» (por lectura del código; no se ejecutó el caso completo).

### 13.2.4 Las cuentas creadas desde el Mantenedor quedan sin clave

`mantenedor.crear_usuario` crea la cuenta sin contraseña (el comentario del archivo dice que la clave se asigna en la etapa de seguridad). No hay pantalla para asignarla. En producción esa persona no puede ingresar hasta que el administrador ejecute `recuperar_acceso`. Las cuentas creadas con el comando `crear_usuario` sí llevan clave.

### 13.2.5 El enlace «Salir» de la pantalla del segundo factor respondía 405 (verificado; corregido)

`nucleo/templates/nucleo/segundo_factor.html` usa un enlace `GET` a `/salir/`, y `LogoutView` solo acepta `POST` (se comprobó: `GET` da 405 y `POST` 302). Quien queda en esa pantalla no puede salir con ese enlace. **Corregido** el 17-11-2026: «Salir» ahora es un formulario `POST` con CSRF.

### 13.2.6 `/admin/` queda expuesto y una cuenta sin rol no pasa por el segundo factor

`config/urls.py` monta el admin de Django. La aplicación no registra modelos propios, pero una cuenta creada con `createsuperuser` entraría con solo su clave: `segundo_factor.exige` mira el rol de la aplicación y una cuenta sin grupo no lo tiene. Conclusión leída del código, no probada: no crear superusuarios y, si no se necesita, bloquear `/admin/` en nginx.

### 13.2.7 Funciones del diseño que no tienen pantalla o no existen

Cierre de período con foto de KPI y reapertura; pantalla de Auditoría; pantallas de Parámetros y de Cargos; solicitar y aprobar «no aplica»; marca por excepción (estas dos existen en el servicio y en las pruebas, sin ruta). `Anio.estado = cerrado` y `Periodo.estado = cerrado` no los asigna ningún código.

### 13.2.8 Campos que se guardan pero no gobiernan nada

`Tarea.al_terminar_cierre` (se importa, se exporta y no se usa), `predecesoras` (solo informan en la matriz; no se exigen al ejecutar), `dh_inicio`, `horas_dh` y `horas_semana` (solo afectan la matriz, no las fechas) y `modo_cierre = fuera`, que se comporta como `igual` aunque su texto diga que no consume horas del equipo.

### 13.2.9 La bitácora detecta manipulación; no la impide

El sello es un SHA-256 sin clave secreta ni ancla externa. Quien pueda escribir en el archivo de la base puede quitar los triggers y recalcular toda la cadena (6.6). Riesgo residual RC-04, aceptado con condiciones en el diseño.

### 13.2.10 Criterio de «atrasada» no uniforme para las devueltas

Una ocurrencia `devuelta` vencida cuenta como atrasada en los listados del panel y el tablero, pero `kpi.resumen` solo cuenta `pendiente` y `bloqueada`. El KPI de cumplimiento a tiempo no se ve afectado (se basa en la primera marca).

### 13.2.11 Seguridad que el diseño proponía y no está

Sin `Content-Security-Policy` global ni `Permissions-Policy`, sin `LOGGING` propio (el `logs/seguridad.log` de `docs/f1/05_despliegue_respaldo.md` no existe) y sin obligación de cambiar la clave en el primer ingreso (`docs/etapas.md` dice que cada persona la cambia al primer ingreso; el código no lo fuerza).

### 13.2.12 Detalles menores

- `cambiar_clave.bat` pide un usuario «analista», pero el usuario de ejemplo se llama `asistente`.
- `crear_usuario` usa `date.today()` en lugar de `reloj.hoy()`.
- La plantilla `en_construccion.html` y la vista `views.en_construccion` no tienen ruta.
- `paginas.json` (raíz) y `.vista_previa/` son material de vista previa; la aplicación no los lee.

## 13.3 Documentación desactualizada

| Documento | Qué quedó atrás |
|---|---|
| `README.md` | Su tabla de estado habla de 600 pruebas y dice que falta «respaldo con restauración, seguridad con claves y despliegue», que ya están construidos (la suite tiene 724) |
| `docs/TRASPASO.md` | Menciona «676 pasan» y, más abajo, 713 pruebas; hoy son 726 |
| `docs/f1/02_modelo_datos_recurrencia.md` | Describe tablas que no existen como tales (`TareaPredecesora`, `ReglaRecurrencia`, `Jornada`, `Ausencia`), un `Periodo.estado = borrador` y reglas D7/D10 anteriores a DEC-35 |
| `docs/f1/03_kpi_roles_sod.md` | Su matriz de permisos difiere de la vigente (6.2): por ejemplo, el diseño dice que el Colaborador no revisa y que el administrador importa Excel |
| `docs/f1/04_seguridad_riesgos_pruebas.md`, `05_despliegue_respaldo.md` | Proponen controles (CSP estricta, `logs/seguridad.log`) que no están implementados |
| `docs/f1/08_guia_de_despliegue.md` | Dice que los cargos se crean al cargar el plan y no menciona el ajuste de `Asignacion.desde` (13.2.1 y 13.2.2) |

## 13.4 Supuestos y riesgos que siguen abiertos

- **Un solo escritor.** SQLite con WAL es suficiente para un equipo pequeño. El diseño fija los disparadores para pasar a PostgreSQL: más de 10 usuarios simultáneos, una integración con Odoo o el Arqueo, o una auditoría externa que exija permisos por rol en la base.
- **Todo es estimación.** Las horas por tarea son estimaciones (la mayoría de base, algunas definidas por la Gerente AyF); los indicadores de carga y la matriz dependen de ellas.
- **Calendario de 2027 y 2028** tomado de la librería `holidays` 0.107: un feriado decretado después se agrega a mano en «Abrir mes».
- **Tareas sin revisor** o con un cargo sin persona vigente: se muestran como aviso, no se corrigen solas.

## 13.5 Camino previsto hacia una integración (por ejemplo, Odoo)

No existe ninguna integración. El diseño dejó la lógica en una capa de servicios (`nucleo/servicios/`) separada de las vistas para poder exponer una API más adelante (ADR-001, objeción OBJ-2: DRF queda diferido). Hoy los datos entran y salen por Excel (Plan vigente, listado de tareas, matriz, árbol y procesos) y por la base SQLite. Cualquier integración debería apoyarse en esos servicios y pasar por una decisión sobre el motor de base de datos.

# 14. Anexo: glosario y fuentes

## 14.1 Glosario

| Término | Significado |
|---|---|
| Ocurrencia | Una vez concreta de una tarea en un período, con su fecha límite y su estado |
| Período | Un mes abierto en la aplicación (`Periodo`): reúne las diarias y semanales del mes y el cierre del mes anterior |
| DHnn | n-ésimo día hábil del mes; DH00 es el último hábil del mes anterior |
| Cierre | El conjunto de tareas de DH00 a DH10 con los hitos DH08, DH09 y DH10 |
| Cargo | Función que ejerce una persona durante un rango de fechas (`Asignacion`); las tareas se asignan a cargos, no a personas |
| Cargo externo | Responsable sin cuenta en la aplicación; sus tareas se marcan «Recibido» y no entran al KPI de nadie |
| Gracia de arranque | Período inicial en que lo anterior al inicio de uso no cuenta como atrasado (`vence_el`) |
| Techo de planificación | Fracción de la jornada que se planifica cada día; el resto es reserva |
| Plan vigente | El conjunto de tareas activas hoy; también el Excel que lo exporta |
| Clave estable | Huella de proceso, tarea y subtarea con la que se reconoce una tarea al recargar un Excel |
| Bitácora | Registro de eventos (`EventoAuditoria`) solo de agregar, con sello encadenado |
| Falla cerrada | Ante una configuración o un estado dudoso, el sistema se niega a arrancar o a mostrar contenido en vez de abrirse |
| Legión | Método de trabajo por fases con puertas de aprobación humana con que se diseñó el proyecto |

## 14.2 Fuentes consultadas

Código: `config/`, `nucleo/` (modelos, vistas, servicios, comandos, migraciones, plantillas), `pruebas/`, `deploy/`, scripts de la raíz. Documentos: `CLAUDE.md`, `README.md`, `LEEME.txt`, `docs/TRASPASO.md`, `docs/etapas.md`, `docs/f1/00` a `08`, `docs/encargo/PROMPT_CLAUDE_CODE.md` y los encabezados de `docs/datos/Planificacion_2.0_contabilidad.xlsx`.

Ejecuciones: la suite completa (726 pruebas), `manage.py check --deploy` con variables de producción de prueba, `manage.py check` con `PLANIFICACION_SIN_CLAVE=1` en producción (se negó a arrancar) y pruebas desechables sobre una base temporal (apertura con asignación posterior, `cargar_plan` sin cargos, `cargar_plan` con cargos creados, `GET` contra `/salir/` y el contenido de una base de pruebas recién migrada).
