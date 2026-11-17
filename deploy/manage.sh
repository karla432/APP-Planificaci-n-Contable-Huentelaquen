#!/usr/bin/env bash
# Ejecuta un comando de la aplicación con su entorno de producción:   sudo /srv/planificacion/app/deploy/manage.sh crear_usuario ...
set -euo pipefail
RAIZ="${PLANIFICACION_RAIZ:-/srv/planificacion/app}"
set -a; source /etc/planificacion/planificacion.env; set +a
cd "$RAIZ"
exec sudo -E -u planificacion /srv/planificacion/venv/bin/python manage.py "$@"
