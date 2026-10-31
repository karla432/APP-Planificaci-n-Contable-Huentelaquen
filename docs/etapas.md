# Etapas del proyecto (igual que el Arqueo de Caja)

| # | Etapa | Dónde corre | Qué ves tú | Quién decide | Estado |
|---|---|---|---|---|---|
| 1 | Diseño técnico (`docs/f1/`) | Papel | Documentos | Karla (G1) | Hecho |
| 2 | **Construcción y prueba local, sin claves** | Tu computador, con datos de EJEMPLO | La web real, para probar y corregir | Karla, en cada pantalla | **Aquí estamos** |
| 3 | Prueba de aceptación con el equipo | Tu computador | Todo el flujo, sin datos reales | Karla (G2) | Pendiente |
| 4 | **Seguridad e ingreso con claves** (últimas etapas) | Tu computador | Ingreso con clave de 12+ caracteres, bloqueo, 2FA, respaldo restaurado | Karla | Pendiente |
| 5 | Despliegue en el servidor OpenCloud | Servidor propio, con HTTPS | La app definitiva | Karla (G3, por escrito) y Eugenio, que despliega | Pendiente |
| 6 | Puesta en marcha y estabilización | Servidor | Primer cierre real | Karla | Pendiente |

**Regla de Karla (30-10-2026):** todo proyecto parte en su computador y la seguridad con claves se deja para las últimas etapas, antes del deploy. Nada va a producción sin cerrar la etapa 4.

## Cómo ver la web mientras se construye (etapa 2)

1. Baja el repositorio a tu computador (`git clone`, o descarga el ZIP de la rama `claude/peaceful-ride-ysf0iw`).
2. Doble clic en **`iniciar_local.bat`**. La primera vez instala lo necesario; después abre en segundos.
3. Entra a http://127.0.0.1:8000 con `gerente`, `jefa`, `contadora` o `asistente` y la clave `Ejemplo-local-2026`.
4. Cuando yo suba cambios: `git pull` y vuelve a abrir. Para empezar de cero, borra `db_local.sqlite3`.

La fecha simulada es el lunes 09-11-2026 (Día 6 del cierre de noviembre); el calendario empieza en noviembre y diciembre se abre después desde «Abrir mes». Los datos son de ejemplo.

## Cuentas reales
Se crean solo en el servidor, después de G3, con claves de **12 o más caracteres** que cada persona cambia al primer ingreso. Nombres, correos y claves reales **no** se guardan en el repositorio.
