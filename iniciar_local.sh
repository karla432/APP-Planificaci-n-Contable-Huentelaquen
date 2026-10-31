#!/bin/sh
# Igual que iniciar_local.bat para Linux/Mac. Con --preparar solo deja todo listo (sin abrir el servidor).
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -r requirements.txt
[ -e .entorno_desarrollo ] || : > .entorno_desarrollo
export PLANIFICACION_DB_PATH="$PWD/db_local.sqlite3"
export PLANIFICACION_HOY="${PLANIFICACION_HOY:-2026-12-04}"
export PLANIFICACION_SIN_CLAVE=1  # solo desarrollo local
NUEVA=0; [ -e db_local.sqlite3 ] || NUEVA=1
python manage.py migrate -v0   # siempre aplica las actualizaciones de la base (no borra nada)
[ "$NUEVA" = "1" ] && python manage.py datos_de_ejemplo --password Ejemplo-local-2026
echo "Usuarios de ejemplo: gerente, jefa, contadora, asistente · clave: Ejemplo-local-2026"
[ "$1" = "--preparar" ] && exit 0
exec python manage.py runserver 8000
