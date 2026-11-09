# Cómo trabajamos con Karla (método de trabajo)

> Si empiezas una sesión nueva en este proyecto, lee primero `docs/TRASPASO.md` (estado, pendientes y reglas vigentes).

Estas reglas las pidió Karla Meneses el 30-10-2026 y valen para todo proyecto con ella.

## 1. Todo proyecto empieza en el computador local de Karla
- Se construye y se prueba primero **en su computador**, con datos de ejemplo, como se hizo con el Arqueo de Caja.
- Lo ideal es una sesión de Claude **corriendo en su PC** (app de escritorio, carpeta del proyecto), para levantar la web y darle el link en el momento.
- Si la sesión es en la nube, decírselo de inmediato y proponerle abrirla en local. No pedirle pasos técnicos largos: ella no es técnica; explicar simple y **de a un paso**.
- El servidor (deploy) viene después, cuando ella lo apruebe por escrito.

## 2. Seguridad e ingreso con claves van en las últimas etapas
- Mientras se construye en local se trabaja **sin clave** (modo de prueba, solo en su computador).
- Seguridad e ingreso con claves (claves de 12 o más caracteres, bloqueo por intentos, 2FA, bitácora, respaldo con restauración probada) se dejan para **las etapas finales, justo antes del deploy**.
- Lo que no cambia: **nunca** se despliega a producción ni se cargan datos o cuentas reales sin ese cierre y sin aprobación escrita de Karla. El modo sin clave debe ser imposible en producción (falla cerrada).

## 3. Siempre
- Español de Chile, lenguaje simple. Nunca guardar claves, nombres reales ni correos reales en el repositorio.
- Decir con franqueza lo que no se pudo probar (por ejemplo, algo que no se ejecutó en Windows).
