# Etapas del proyecto (igual que el Arqueo de Caja)

| # | Etapa | Dónde corre | Qué ves tú | Quién decide | Estado |
|---|---|---|---|---|---|
| 1 | Diseño técnico (`docs/f1/`) | Papel | Documentos | Karla (G1) | Hecho |
| 2 | **Construcción y prueba local** | Tu computador, con datos de EJEMPLO | La web real, para probar y corregir | Karla, en cada pantalla | **Aquí estamos** |
| 3 | Prueba de aceptación | Tu computador o un servidor de pruebas | Todo el flujo con el equipo, sin datos reales | Karla (G2) | Pendiente |
| 4 | Despliegue en el servidor OpenCloud | Servidor propio, con HTTPS | La app definitiva | Karla (G3, por escrito) y Eugenio, que despliega | Pendiente |
| 5 | Puesta en marcha y estabilización | Servidor | Primer cierre real (noviembre → diciembre) | Karla | Pendiente |

## Cómo ver la web mientras se construye (etapa 2)

1. Baja el repositorio a tu computador (`git clone`, o descarga el ZIP de la rama `claude/peaceful-ride-ysf0iw`).
2. Doble clic en **`iniciar_local.bat`**. La primera vez instala lo necesario; después abre en segundos.
3. Entra a http://127.0.0.1:8000 con `gerente`, `jefa`, `contadora` o `analista` y la clave `Ejemplo-local-2026`.
4. Cuando yo suba cambios: `git pull` y vuelve a abrir. Para empezar de cero, borra `db_local.sqlite3`.

La fecha simulada es el viernes 04-12-2026 (Día 4 del cierre), para ver el cierre de diciembre. Los datos son de ejemplo.

## Cuentas reales
Se crean solo en el servidor, después de G3, con claves de **12 o más caracteres** que cada persona cambia al primer ingreso. Nombres, correos y claves reales **no** se guardan en el repositorio.
