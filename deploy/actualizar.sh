#!/usr/bin/env bash
# Actualiza la aplicación a una versión nueva. SIEMPRE respalda antes de migrar. Uso:  sudo deploy/actualizar.sh [rama-o-etiqueta]
set -euo pipefail
RAIZ="${PLANIFICACION_RAIZ:-/srv/planificacion/app}"
VERSION="${1:?Indica la rama o etiqueta aprobada, por ejemplo: sudo deploy/actualizar.sh v1.0}"
M="$RAIZ/deploy/manage.sh"
cd "$RAIZ"
echo "1/6 Respaldo previo…";           "$M" respaldar
echo "2/6 Código ($VERSION)…";         sudo -u planificacion git fetch origin && sudo -u planificacion git checkout "$VERSION" && sudo -u planificacion git pull --ff-only origin "$VERSION"
echo "3/6 Dependencias…";              sudo -u planificacion /srv/planificacion/venv/bin/pip install -r requirements.lock.txt
echo "4/6 Migraciones…";               "$M" migrate --noinput
echo "5/6 Archivos estáticos…";        "$M" collectstatic --noinput
echo "6/6 Reinicio y revisión…";       systemctl restart planificacion && sleep 3 && "$M" check --deploy && "$M" verificar_bitacora
echo "Listo. Si algo falló: ver «Plan de salida» en docs/f1/08_guia_de_despliegue.md."
