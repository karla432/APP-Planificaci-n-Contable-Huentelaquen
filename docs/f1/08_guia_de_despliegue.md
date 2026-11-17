# 08 · Guía de despliegue y operación (para Eugenio)

Versión: 17-11-2026. **Esta guía no autoriza el despliegue.** Pasar a producción exige la aprobación escrita de Karla (puerta G3) y la tuya, con la lista de la sección 7 cumplida.
Lo que NO se ha probado: nada de esto se ejecutó en un servidor real ni en Windows. Los archivos de `deploy/` están escritos pero sin probar en tu servidor: léelos y ajústalos antes de usarlos.

## 1. Qué se instala
Una aplicación Django (gunicorn) detrás de nginx con HTTPS, base SQLite con WAL en una carpeta fuera del código, adjuntos en otra carpeta y respaldos en una tercera. Sin correo (en esta versión no se envían correos).

## 2. Lo que necesito que definas antes (o confirmes)
1. Dominio o subdominio y certificado (`certbot --nginx`).
2. Si usarás SQLite (lo previsto) o PostgreSQL. Con SQLite no hay cambios; con PostgreSQL hay que adaptar `DATABASES` y las comprobaciones de la bitácora.
3. Dónde se guarda el respaldo **fuera** del servidor, con qué cifrado, y quién puede restaurarlo.
4. Retención de respaldos (propuesta: 30 diarios) y de bitácora (propuesta: 5 años). Karla debe confirmarlas.

## 3. Instalación (resumen)
> Para el VPS donde corre el Arqueo de Caja (Ubuntu 22.04, puerto 8002, `planificacion.finanzashuentelauquen.cl`) sigue **`deploy/README_DESPLIEGUE.md`**, paso a paso. Ojo: Ubuntu 22.04 trae Python 3.10 y Django 6.1 exige 3.12 o más.
```bash
# Usuario, carpetas y permisos
sudo useradd --system --home /srv/planificacion --shell /usr/sbin/nologin planificacion
sudo mkdir -p /srv/planificacion /var/lib/planificacion/evidencias /var/backups/planificacion /var/log/planificacion /var/www/planificacion/static /etc/planificacion
sudo chown -R planificacion:planificacion /srv/planificacion /var/lib/planificacion /var/backups/planificacion /var/log/planificacion /var/www/planificacion
sudo chmod 700 /var/lib/planificacion /var/backups/planificacion

# Código (rama aprobada) y entorno virtual
sudo -u planificacion git clone https://github.com/karla432/app-planificaci-n-contable-huentelaquen.git /srv/planificacion/app
cd /srv/planificacion/app && sudo -u planificacion git checkout RAMA_O_ETIQUETA_APROBADA
sudo -u planificacion python3 -m venv /srv/planificacion/venv
sudo -u planificacion /srv/planificacion/venv/bin/pip install -r requirements.lock.txt
```
```bash
# Variables de entorno (la clave secreta es distinta en cada servidor)
sudo cp deploy/planificacion.env.example /etc/planificacion/planificacion.env
sudo chown planificacion:planificacion /etc/planificacion/planificacion.env && sudo chmod 600 /etc/planificacion/planificacion.env
sudo nano /etc/planificacion/planificacion.env     # completa DJANGO_SECRET_KEY, el dominio y las rutas
```
```bash
# Base, estáticos, servicio y nginx
sudo deploy/manage.sh migrate --noinput
sudo deploy/manage.sh collectstatic --noinput
sudo cp deploy/planificacion.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now planificacion
sudo cp deploy/nginx-planificacion.conf /etc/nginx/sites-available/planificacion && sudo ln -s /etc/nginx/sites-available/planificacion /etc/nginx/sites-enabled/
sudo certbot --nginx -d TU.DOMINIO && sudo nginx -t && sudo systemctl reload nginx
sudo deploy/manage.sh check --deploy
```
La app **se niega a arrancar** en producción sin `DJANGO_SECRET_KEY` y `DJANGO_ALLOWED_HOSTS`. El modo «entrar sin clave» no existe en producción. El segundo factor no se puede apagar en producción.
`check --deploy` deja solo una advertencia (W021, precarga HSTS): se deja así a propósito hasta que el dominio sea definitivo.

## 4. Cuentas
**Orden obligatorio en una base nueva** (la base nueva solo trae el cargo «Contador»; los demás cargos aparecen al cargar el plan):
1. Cargar el plan **con `--crear-cargos`**, sin abrir el mes todavía (sección 5, paso A).
2. Crear las cuentas (esta sección), siempre con `--desde 2026-01-01`.
3. Que la Gerente ingrese, confirme los feriados de 2026 y abra el año en «Abrir mes».
4. Abrir noviembre (sección 5, paso B).

Las cuentas reales se crean solo desde la consola (nunca van en el repositorio). Los cargos deben existir antes (paso 1).
```bash
sudo deploy/manage.sh crear_usuario USUARIO --rol GERENTE --nombre "Nombre de la persona" --cargo "Gerente AyF" --desde 2026-01-01
```
**`--desde` importa:** sin él, el cargo se asigna con la fecha de hoy y, al abrir noviembre desde el 01-11, las tareas con fecha anterior **no encuentran responsable** y no se generan (aviso `sin_responsable`). Usa una fecha anterior al comienzo de la medición.
La clave se pide por teclado (mínimo 12 caracteres). Roles: `GERENTE`, `JEFATURA`, `COLABORADOR`, `LECTURA`, `ADMIN_SISTEMA`.
- **Gerente AyF y administrador tienen segundo factor obligatorio.** El comando muestra UNA vez la clave para la aplicación de códigos (Google/Microsoft Authenticator): entrégasela en privado. En su primer ingreso escribe el código de 6 números.
- Cada persona puede cambiar su clave desde «Cambiar mi clave» (menú, abajo a la izquierda). **No se obliga a cambiarla en el primer ingreso**: pídele a cada persona que lo haga.
- Cambió de teléfono o perdió la clave: `sudo deploy/manage.sh recuperar_acceso USUARIO --reiniciar-2fa` (pide clave nueva; con `--solo-desbloquear` solo quita el bloqueo).
- Bloqueo: 5 intentos fallidos (clave o código) bloquean la cuenta 15 minutos.
- Una persona sin cuenta en la app no ve nada.
- Las cuentas que se crean desde el Mantenedor → Usuarios quedan **sin clave** y con el cargo asignado desde el día en que se crean: Eugenio debe darles clave con `recuperar_acceso USUARIO` y, si el mes ya se abrió con fechas anteriores, preferir crearlas por consola con `--desde`.
- **`/admin/` (administración de Django) sigue publicado.** Una cuenta con `createsuperuser` no pasa por el segundo factor, porque no tiene perfil de la aplicación. No crees superusuarios en producción, o bloquea `/admin/` en nginx (ejemplo: `location /admin/ { return 404; }`) hasta decidir.

## 5. Cargar el plan y abrir el mes
Karla te entrega el Excel «Planificación vigente» (contiene datos reales de la empresa: **no va al repositorio**). Ojo: el **responsable** de cada tarea es un **cargo** (por ejemplo «Contador Senior»), no el nombre de una persona; si el Excel trae un nombre, la carga se detiene y te lo dice.
**Paso A — cargar el plan y crear los cargos** (base nueva; primero sin `--aplicar` para ver qué haría y qué cargos crearía):
```bash
sudo deploy/manage.sh cargar_plan /ruta/Planificacion_vigente.xlsx --crear-cargos                 # solo muestra qué haría
sudo deploy/manage.sh cargar_plan /ruta/Planificacion_vigente.xlsx --crear-cargos --aplicar --confirmo-desactivar
```
Revisa la lista «Se crearán N cargos»: deben ser cargos, no nombres de personas (si trae un nombre, usa `--cargo "TEXTO=CARGO"`).

**Paso B — después de crear las cuentas y de que la Gerente abra el año 2026**, abrir noviembre con la gracia:
```bash
sudo deploy/manage.sh cargar_plan /ruta/Planificacion_vigente.xlsx --aplicar --confirmo-desactivar --abrir-mes 2026-11 --desde 2026-11-01 \
     --inicio-uso 2026-11-01 --dias-de-gracia 21
```
(Repetir la carga del mismo archivo no cambia nada: ya no hay diferencias.) Sin el año abierto, `--abrir-mes` falla.
`--desde` es el comienzo de la medición (01-11-2026). `--inicio-uso` es el día desde el que corre la gracia (01-11-2026): durante `--dias-de-gracia` (21 días, **hasta el 22-11-2026**) nada cuenta como atrasado; lo ya vencido aparece en «Mi día» como «Por registrar» y las primeras atrasadas se ven desde el lunes 23-11. Se puede cambiar después con `deploy/manage.sh configurar_gracia --inicio AAAA-MM-DD --dias 21` (o `--quitar`).
Si el Excel trae otro texto donde va un cargo, `--cargo "TEXTO=CARGO"` lo traduce sin tocar el archivo (el cargo «Contador» ya existe).
Antes de abrir el mes, Karla confirma los feriados del año y abre el año en la pantalla «Abrir mes» (2027 y 2028 ya vienen cargados; el 2026 lo confirma ella). **Fecha de comienzo: 01-11-2026.** Al abrir desde el 01-11, las tareas de noviembre cuya fecha ya pasó quedan generadas como pendientes, pero **no cuentan como atrasadas hasta el 23-11** (gracia acordada con Karla): el equipo las va registrando.
Después, el equipo puede cambiar quién ejecuta cada tarea (en el detalle de la tarea) y Karla/Jefa pueden descargar, corregir y volver a cargar el plan desde Mantenedor → Tareas.

## 6. Respaldo, restauración y verificación
- Diario: `deploy/respaldo_diario.sh` (cron o systemd timer, p. ej. 02:30). Hace una copia consistente de la base y de los adjuntos y deja un archivo de huellas SHA-256. **Tú completas el cifrado y la copia fuera del servidor** (están marcados con ◆ en el script).
- Una vez al mes (y **antes de G3**): `sudo deploy/manage.sh verificar_respaldo /var/backups/planificacion/respaldo_FECHA.sqlite3.gz`. Comprueba la huella, restaura en una base temporal, revisa la integridad y la cadena de la bitácora y cuenta tareas, ocurrencias, eventos y usuarios. **Guarda esa salida como evidencia de la restauración probada.**
- Cuando quieras: `sudo deploy/manage.sh verificar_bitacora` (la bitácora está encadenada con sellos; cualquier alteración se detecta).
- Actualizar a una versión nueva: `sudo deploy/actualizar.sh RAMA_O_ETIQUETA` (respalda antes de migrar y revisa al terminar).

## 7. Lista de aceptación para G3 (se marca con evidencia)
| # | Control | Cómo se comprueba | Estado |
|---|---|---|---|
| 1 | La app no arranca sin clave secreta ni dominios | Probar sin esas variables | Pendiente (servidor) |
| 2 | HTTPS activo y `check --deploy` sin errores | `deploy/manage.sh check --deploy` | Pendiente (servidor) |
| 3 | «Entrar sin clave» no existe | Abrir `/acceso-rapido/`: debe dar 404 | Pendiente (servidor) |
| 4 | Claves de 12 o más caracteres y bloqueo a los 5 intentos | Crear usuario con clave corta (debe fallar); 5 intentos fallidos | Pendiente (servidor) |
| 5 | Segundo factor obligatorio para Gerente AyF y administrador | Ingresar con cada uno: no ve nada hasta escribir el código | Pendiente (servidor) |
| 6 | Cada rol ve solo lo que le corresponde | Ingresar con un colaborador y con una persona de solo lectura | Pendiente (servidor) |
| 7 | Respaldo diario funcionando y copia fuera del servidor | Revisar la carpeta y el destino externo | Pendiente (servidor) |
| 8 | **Restauración probada** | `verificar_respaldo` con la salida guardada | Pendiente (servidor) |
| 9 | Bitácora íntegra | `verificar_bitacora` | Pendiente (servidor) |
| 10 | Plan cargado y mes abierto con la fecha de comienzo acordada | Pantallas «Matriz del cierre» y «Mi día» | Pendiente (servidor) |
| 11 | Karla aprueba por escrito la versión (etiqueta/commit) y el alcance | Mensaje o documento firmado | Pendiente |
| 12 | Eugenio acepta la operación (respaldos, actualizaciones, soporte) | Mensaje o documento | Pendiente |

## 8. Soporte (problemas conocidos)
| Síntoma | Qué hacer |
|---|---|
| «Cuenta bloqueada» | Esperar 15 minutos o `recuperar_acceso USUARIO --solo-desbloquear` |
| Código del segundo factor «no es válido» | Revisar que el reloj del teléfono esté en hora automática; si cambió de teléfono: `--reiniciar-2fa` |
| La app no abre | `systemctl status planificacion`, `journalctl -u planificacion -n 100`; revisar el archivo de entorno |
| «Falta el mes/día» en una tarea | Es una tarea «por revisar»: se corrige en Mantenedor → Tareas |
| Una persona no ve sus tareas | Revisar que su cuenta tenga cargo vigente (se ve en Mantenedor → Usuarios) |

## 9. Plan de salida
- **Volver a la versión anterior:** `git checkout ETIQUETA_ANTERIOR`, restaurar el respaldo previo a la migración (`respaldar` se ejecuta siempre antes de `migrate`) y reiniciar el servicio.
- **Si la app no está lista:** se sigue con el Excel actual. Los datos de la app se pueden descargar como Excel (Mantenedor → Tareas → «Descargar planificación vigente»).
- **Salida definitiva:** exportar tareas, ocurrencias y bitácora a archivos planos.

## 10. Límites conocidos (decirlos con franqueza)
- El secreto del segundo factor se guarda en la base: quien lea la base puede generar códigos. Por eso la base y sus respaldos deben estar cifrados y con permisos 600/700.
- No se obliga cambiar la clave en el primer ingreso (solo se ofrece «Cambiar mi clave»).
- El código QR del segundo factor solo se muestra si el servidor tiene instalada la librería `qrcode`; si no, la clave se escribe a mano en la aplicación.
- Los archivos de `deploy/` y los comandos de operación se probaron en el entorno de desarrollo, no en el servidor real.
- `qrcode` no está en `requirements.lock.txt`: con ese archivo el segundo factor no muestra QR (la clave se escribe a mano). Si se quiere QR, agregar la librería al lock y probar.
- Hay funciones del diseño original sin pantalla (cierre de período con foto de KPI, pantalla de Auditoría, Parámetros) y «No aplica» existe como servicio sin pantalla. Detalle en `docs/documentacion_tecnica.md`, sección 13.
