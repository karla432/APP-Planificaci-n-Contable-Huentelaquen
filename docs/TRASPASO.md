# Traspaso a la sesión local (03-11-2026)

Este archivo es para la sesión de Claude que corre **en el computador de Karla**. Lo anterior se hizo en una sesión en la nube; todo está en el repositorio y en esta carpeta. Lee también `CLAUDE.md` (cómo trabajamos con Karla).

## Quién es Karla y cómo hablarle
Karla Meneses, Gerente de Administración y Finanzas de Hacienda Huentelauquén. No es técnica: español de Chile, simple, **de a un paso**. Quiere trabajar **siempre en local** (su PC), nunca en la nube. No pedirle pasos técnicos largos: levantar la app y darle el link es trabajo tuyo.

## Qué es el proyecto
**Planificación Contable Huentelauquén**: app Django (SQLite, páginas del servidor) que planifica, reparte y controla las tareas contables del equipo (Gerente AyF, Jefa de Control, Contador Senior, Analista Contable) y mide el cumplimiento. Se construye primero en local con datos de ejemplo; después la despliega Eugenio en un servidor (OpenCloud).

## Reglas que no cambian
- **No se despliega, no se mandan correos reales ni se cargan datos o cuentas reales a un servidor** sin aprobación escrita de Karla (puerta G3) y de Eugenio.
- Seguridad e ingreso con claves (12 o más caracteres, bloqueo, 2FA, bitácora, respaldo probado) van en las **últimas etapas**. Mientras tanto: modo de prueba sin clave, solo en su computador.
- Nunca guardar claves, nombres reales ni correos reales en el repositorio.
- Decir con franqueza lo que no se pudo probar. **Nada se ha ejecutado en Windows ni se ha corrido `iniciar_local.bat` desde la sesión en la nube.**

## Cómo levantar la app en local
`iniciar_local.bat` (doble clic) o `python levantar_local.py`. Carga datos de EJEMPLO con la Planificación 2.0 ya cargada (se simula el lunes 09-11-2026). Usuarios: gerente, jefa, contadora, asistente. Si hay un `db_local.sqlite3` anterior, borrarlo para que se arme de nuevo. Pruebas: `python -m pytest -q` (674 pasan; settings en PRODUCCION salvo `PLANIFICACION_ENTORNO=desarrollo`).

## Dónde está cada cosa
- `docs/f1/00_decisiones_y_gates.md`: decisiones DEC-01…DEC-39, supuestos y puertas.
- `docs/f1/07_planificacion_2_0.md`: la Planificación 2.0 (cómo se carga y qué cambia).
- `docs/datos/Planificacion_2.0_contabilidad.xlsx`: el plan vigente (hojas Diario-Semanal y Mensual; Maestro es respaldo).
- `nucleo/servicios/plan2.py` (carga del plan), `matriz.py` (matriz del cierre), `importador.py`, `calendario.py`, `recurrencia.py`.
- `pruebas/test_plan2.py`: comprueba que la matriz de la app reproduce la tabla de carga del archivo de Karla, día por día.

## Reglas del negocio vigentes (resumen)
- DH08, DH09 y DH10 son **días hábiles** (reportes listos en la tarde, Gerente General, Directorio). DH00 = último día hábil del mes anterior. Semanas del cierre: DH01 a DH10.
- Jornada: lunes a jueves 9 h, viernes 5 h. Gerente AyF: máximo 80 h al mes para Huentelauquén.
- La **revisión va dentro de las horas de quien ejecuta** (no suma carga al revisor).
- Cargo: **Analista Contable** (antes «Asistente Contable»).
- Techo de planificación por día: 90 % (DH00–DH06), 80 % DH07, 75 % DH08, 85 % DH09, 95 % DH10.
- La pantalla «Matriz del cierre» muestra el plan vigente; la propuesta de equilibrio es opcional (`?ver=propuesta`).

## Estado al 03-11-2026
Hecho y con pruebas (674): Planificación 2.0 cargada (206 tareas activas, 224 predecesoras), matriz con hitos/dependencias/techo, horas reales por usuario, carga masiva Excel de tareas y procesos, estructura de 3 niveles (`OO-PPP.TT.SSS`), adjuntos en comentarios, calendario 2027–2028, QA de Karla aplicado. Rama de trabajo: `claude/peaceful-ride-ysf0iw` (último commit `acfd98b`).

## Pendiente: 6 confirmaciones de Karla sobre la Planificación 2.0 (pregúntalas UNA por una)
1. **Tareas desactivadas.** El plan ya no trae 8 tareas: las 4 que ella confirmó (21-REM.04.003, 30-CYP.02.006, 31-ACU.03.001, 35-CDF.01.006, esta última ya estaba en el plan con otro código) más 21-REM.04.002, 27-CON.02.001, 35-CDF.01.001, .002 y .003, que el plan reemplazó por tareas distintas con el mismo código. Se desactivan (no se borran). ¿Confirma?
2. **Códigos repetidos.** Algunas tareas nuevas reciben en la app un código distinto al del archivo porque el archivo reutilizó códigos que ya tenían otra tarea. Las predecesoras no se pierden.
3. **Proceso «Cierre contable general».** Se creó como proceso nuevo 36-CCG (el archivo ponía código 27-CON con ese nombre de proceso). ¿Va como proceso propio o dentro de «Contabilidad»?
4. **Duraciones.** 77 tareas cambian de duración respecto de lo que tenía la app (por ejemplo cotejos de 90 min a 9 min). Es lo que dice el archivo.
5. **Hito DH04.** En el archivo dice «Revisión de avance (DH05)» pero está en DH04: ¿error de texto?
6. **Tarea 13-PBC.03.001** (cuota de contribuciones, abril/junio/septiembre/noviembre «semana 4») no trae el día del mes: queda «por revisar».

También sigue pendiente confirmar los supuestos de `00_decisiones_y_gates.md` (por ejemplo, los feriados 2027–2028 de la librería, que ella debe revisar en «Abrir mes»).

## Próximos pasos posibles (que decida Karla)
Exportar de vuelta el mismo formato de tres hojas; tabla de «lo que se acumula por las pausas» (hoja Diario-Semanal, tabla C); revisar la bandeja de «Mi día/Mi semana» con el plan nuevo; luego, etapa de seguridad y despliegue (con aprobación escrita).
