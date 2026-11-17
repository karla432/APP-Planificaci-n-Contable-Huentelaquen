#!/usr/bin/env bash
# Respaldo diario (cron o systemd timer, por ejemplo a las 02:30): copia consistente + cifrado + copia FUERA del servidor.
# Eugenio completa las dos líneas marcadas con ◆ según lo que defina para el cifrado y el destino externo.
set -euo pipefail
/srv/planificacion/app/deploy/manage.sh respaldar --conservar 30
ULTIMO="$(ls -1t /var/backups/planificacion/respaldo_*.sqlite3.gz | head -1)"
# ◆ 1. Cifrar los archivos del respaldo (ejemplo con gpg y una clave pública guardada fuera del servidor):
#    gpg --batch --yes --encrypt --recipient respaldos@EMPRESA "$ULTIMO"
# ◆ 2. Copiar FUERA del servidor (ejemplo): rsync -a /var/backups/planificacion/ usuario@otro-servidor:/respaldos/planificacion/
# Una vez al mes, prueba de restauración (guarda la salida como evidencia):
if [ "$(date +%d)" = "01" ]; then /srv/planificacion/app/deploy/manage.sh verificar_respaldo "$ULTIMO" | tee -a /var/log/planificacion/restauracion.log; fi
