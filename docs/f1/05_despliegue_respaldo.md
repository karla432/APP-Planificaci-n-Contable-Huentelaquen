# 05 · Despliegue, respaldo y plan de salida

Versión: F1-v1 · 30-10-2026. Plan, no ejecución. **No se despliega a producción, no se cargan datos reales en el servidor y no se envían correos reales sin aprobación escrita de Karla (G3).** Despliega y mantiene siempre Eugenio.

## 1. Esquema (igual al Arqueo de Caja, EVD-1)

| Pieza | Propuesta |
|---|---|
| Aplicación | Django con gunicorn, 127.0.0.1 en un puerto distinto al del Arqueo |
| Servicio | `systemd` (`planificacion.service`), usuario propio sin privilegios, `NoNewPrivileges` y `PrivateTmp` |
| Proxy | nginx con TLS (`certbot --nginx`) y servicio de estáticos |
| Base | SQLite con WAL en una ruta fuera del código, con permisos solo para el usuario del servicio |
| Secretos | `/etc/planificacion/planificacion.env`, nunca en el repo; la app se niega a arrancar en producción sin `DJANGO_SECRET_KEY` y `DJANGO_ALLOWED_HOSTS` |
| Entornos | `dev` (cada desarrollador), `staging` (mismo servidor, otro directorio, puerto y base) y `producción`. Staging no usa datos reales |
| Registro | `logs/seguridad.log` con rotación; salida de gunicorn en el journal |
| Proceso de actualización | `git pull` → instalar dependencias → `migrate` → `collectstatic` → reiniciar el servicio → `check --deploy` |

## 2. Lo que debe definir Eugenio antes de G3

- Dominio o subdominio y certificado.
- Si ya existe PostgreSQL en el servidor OpenCloud (si no, queda SQLite según el ADR).
- Servidor de correo (SMTP) para la v2 de avisos; en v1 no se envía correo.
- Dónde viven los respaldos **fuera** del servidor, y quién puede restaurarlos.
- Política de retención de respaldos y de auditoría. **Pendiente de confirmar** por Karla; propuesta inicial: respaldos diarios por 30 días, y auditoría exportada y archivada por 5 años como mínimo (propuesta a validar con Compliance).

## 3. Respaldo y restauración

1. Copia diaria **cifrada** de la base (copia consistente con la API de respaldo de SQLite) y de los archivos que se carguen.
2. Copia fuera del servidor.
3. **Prueba de restauración documentada y ejecutada antes de G3**: restaurar en una base nueva, verificar conteos y `verificar_bitacora`, y dejar la salida como evidencia.
4. Exportación periódica de la auditoría (archivo firmado por la propia cadena de sellos).

## 4. Plan de salida y recuperación

- **Reversión de una versión:** volver al commit anterior y restaurar la base del respaldo previo a la migración. Todo `migrate` va precedido de un respaldo.
- **Si la app no está lista el 05-11:** se sigue con el Excel actual y no se pierde nada. Los datos registrados en la app se pueden exportar a Excel (v1.1).
- **Salida definitiva:** exportar tareas, ocurrencias y auditoría a archivos planos.
- **Recuperación de acceso:** comando de consola como el del Arqueo (`recuperar_acceso`), que exige acceso al servidor.

## 5. Entregables de despliegue (F2)

`planificacion.service`, `nginx-planificacion.conf`, `manage.sh`, `.env.example`, guía de despliegue paso a paso, runbook de soporte, guía de usuario corta por perfil (colaborador, Jefa, Gerente, administrador).

## 6. Estado de las puertas

G1 pendiente. G2 y G3 no solicitadas.
