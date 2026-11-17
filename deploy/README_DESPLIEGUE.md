# Despliegue en el VPS del Arqueo (para Eugenio)

**Este archivo no autoriza el despliegue.** Antes de cargar datos o cuentas reales hace falta la aprobación escrita de Karla (puerta G3) y la tuya, con la lista de la sección 7 de `docs/f1/08_guia_de_despliegue.md`.
**Nada de esto se ha ejecutado en el servidor.** Se escribió mirando el servidor descrito, sin acceso a él ni a los archivos del Arqueo.

## Servidor y reparto
| | Arqueo de Caja (no se toca) | Planificación Contable |
|---|---|---|
| Usuario de sistema | (el del Arqueo) | `planificacion` |
| Código y entorno virtual | `/srv/arqueo/app` | `/srv/planificacion/app` y `/srv/planificacion/venv` |
| Variables | (las del Arqueo) | `/etc/planificacion/planificacion.env` (600) |
| Base y adjuntos | — | `/var/lib/planificacion/` (700) |
| Respaldos | (los del Arqueo) | `/var/backups/planificacion/` (700), timer `planificacion-respaldo` 03:15 |
| Estáticos | — | `/var/www/planificacion/static/` |
| Servicio | `arqueo` → 127.0.0.1:8001 | `planificacion` → 127.0.0.1:8002, `--workers 2` |
| Sitio nginx y certificado | `arqueo.finanzashuentelauquen.cl` | `planificacion.finanzashuentelauquen.cl` |

Ubuntu 22.04, 1 vCPU, 2 GB de RAM. Con 2 procesos la app usa del orden de 150–250 MB.

## 0. Antes de empezar
1. **DNS**: pedir a Haulmer el registro **A `planificacion` → `170.239.84.247`** en la zona `finanzashuentelauquen.cl`. Comprobar antes del paso 6: `dig +short planificacion.finanzashuentelauquen.cl` debe responder `170.239.84.247`. (Al 17-11-2026 el nombre todavía no existe; `arqueo.` sí apunta a esa IP.)
2. **Python**: Ubuntu 22.04 trae Python 3.10 y **Django 6.1 exige Python 3.12 o más**. Se instala Python 3.12 aparte (paquete `deadsnakes`); el `python3` del sistema y el del Arqueo no cambian.
3. **Repositorio**: si es privado, crea una *deploy key* de solo lectura para el usuario `planificacion` y clona por SSH.
4. Foto del estado actual, para comparar al final: `systemctl status arqueo --no-pager`, `sudo nginx -t`, `free -h`.

## 1. Python 3.12, usuario y carpetas
```bash
sudo apt update && sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.12 python3.12-venv git sqlite3

sudo useradd --system --home /srv/planificacion --shell /usr/sbin/nologin planificacion
sudo mkdir -p /srv/planificacion /var/lib/planificacion/evidencias /var/backups/planificacion /var/log/planificacion /var/www/planificacion/static /etc/planificacion
sudo chown -R planificacion:planificacion /srv/planificacion /var/lib/planificacion /var/backups/planificacion /var/log/planificacion /var/www/planificacion
sudo chmod 700 /var/lib/planificacion /var/backups/planificacion
```

## 2. Código y entorno virtual
```bash
sudo -u planificacion git clone https://github.com/karla432/APP-Planificaci-n-Contable-Huentelaquen.git /srv/planificacion/app
cd /srv/planificacion/app && sudo -u planificacion git checkout RAMA_O_ETIQUETA_APROBADA
sudo -u planificacion python3.12 -m venv /srv/planificacion/venv
sudo -u planificacion /srv/planificacion/venv/bin/pip install -r requirements.lock.txt
sudo chmod +x deploy/*.sh
```

## 3. Variables
```bash
sudo cp deploy/planificacion.env.example /etc/planificacion/planificacion.env
sudo chown planificacion:planificacion /etc/planificacion/planificacion.env && sudo chmod 600 /etc/planificacion/planificacion.env
/srv/planificacion/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"   # copia el resultado
sudo nano /etc/planificacion/planificacion.env    # pega la clave en DJANGO_SECRET_KEY (el dominio ya viene puesto)
```

## 4. Base, estáticos y servicio
```bash
sudo deploy/manage.sh migrate --noinput
sudo deploy/manage.sh collectstatic --noinput
sudo cp deploy/planificacion.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now planificacion
systemctl status planificacion --no-pager
curl -sI http://127.0.0.1:8002/ -H "Host: planificacion.finanzashuentelauquen.cl" | head -1   # responde (301 hacia https es lo esperado)
```

## 5. Sitio nginx (solo puerto 80 por ahora)
```bash
sudo cp deploy/nginx-planificacion.conf /etc/nginx/sites-available/planificacion
sudo ln -s /etc/nginx/sites-available/planificacion /etc/nginx/sites-enabled/planificacion
sudo nginx -t && sudo systemctl reload nginx     # si nginx -t falla, NO recargar: borrar el enlace y revisar
```

## 6. Certificado propio (cuando el DNS ya responda)
```bash
sudo certbot --nginx -d planificacion.finanzashuentelauquen.cl --redirect
sudo nginx -t && sudo systemctl reload nginx
sudo certbot renew --dry-run          # la renovación automática ya existe por el Arqueo; esto confirma que incluye el nuevo
sudo deploy/manage.sh check --deploy  # solo debe quedar W021 (precarga HSTS), a propósito
```

## 7. Respaldo diario propio
```bash
sudo cp deploy/planificacion-respaldo.service deploy/planificacion-respaldo.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now planificacion-respaldo.timer
sudo systemctl start planificacion-respaldo.service && ls -l /var/backups/planificacion/   # primera prueba
```
Completa en `deploy/respaldo_diario.sh` las dos líneas ◆ (cifrado y copia **fuera** del servidor). Prueba de restauración: `sudo deploy/manage.sh verificar_respaldo /var/backups/planificacion/respaldo_FECHA.sqlite3.gz` (guardar la salida como evidencia para G3).

## 8. Comprobar que el Arqueo sigue igual
```bash
systemctl status arqueo --no-pager
curl -sI https://arqueo.finanzashuentelauquen.cl/ | head -1
free -h
```

## 9. Después (con aprobación G3)
Cargar el plan, crear las cuentas y abrir noviembre: secciones 4 y 5 de `docs/f1/08_guia_de_despliegue.md` (orden obligatorio, `--desde 2026-01-01`, gracia de 21 días).

## Operación
- Comandos: `sudo /srv/planificacion/app/deploy/manage.sh <comando>`
- Actualizar: `sudo /srv/planificacion/app/deploy/actualizar.sh RAMA_O_ETIQUETA` (respalda antes de migrar)
- Registros: `journalctl -u planificacion -n 100`, `/var/log/nginx/planificacion.*.log`
- `/admin/` queda cerrado (404) en nginx: no pasa por el segundo factor.
- Sin la librería `qrcode` (no está en `requirements.lock.txt`) el segundo factor no muestra QR: la clave se escribe a mano en la aplicación de códigos.
