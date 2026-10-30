@echo off
rem Cambia la clave de un usuario de la version local y le quita cualquier bloqueo. Doble clic.
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat ( echo Primero abre iniciar_local.bat una vez. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
set PLANIFICACION_DB_PATH=%CD%\db_local.sqlite3
echo.
set /p USUARIO=Usuario a cambiar (gerente, jefa, contadora o analista): 
echo.
echo Escribe la clave nueva (minimo 12 caracteres; mientras escribes no se ve nada). Luego repitela.
python manage.py changepassword %USUARIO%
if errorlevel 1 ( echo No se cambio la clave. & pause & exit /b 1 )
python manage.py shell -c "from nucleo import bloqueo_acceso; bloqueo_acceso.limpiar('%USUARIO%')"
echo.
echo Listo: ya puedes entrar con la clave nueva.
pause
