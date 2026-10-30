@echo off
rem Abre Planificacion Contable en TU computador para verla y probarla (datos de EJEMPLO, no reales).
rem Doble clic. La primera vez instala lo necesario (unos minutos); despues abre en segundos.
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Preparando el entorno por primera vez...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 ( echo No encontre Python. Instalalo desde python.org y vuelve a abrir este archivo. & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if errorlevel 1 ( echo Fallo la instalacion de dependencias. & pause & exit /b 1 )

if not exist .entorno_desarrollo type nul > .entorno_desarrollo
set PLANIFICACION_DB_PATH=%CD%\db_local.sqlite3
rem Simula que hoy es el viernes 04-12-2026 (Dia 4 del cierre) para ver el cierre de diciembre. Borra esta linea para usar la fecha real.
set PLANIFICACION_HOY=2026-12-04

if not exist db_local.sqlite3 (
  python manage.py migrate -v0
  python manage.py datos_de_ejemplo --password Ejemplo-local-2026
)

echo.
echo ============================================================
echo  Abre http://127.0.0.1:8000  (se cierra con Ctrl+C)
echo  Usuarios de ejemplo: gerente, jefa, contadora, analista
echo  Clave de ejemplo:    Ejemplo-local-2026
echo  Para empezar de cero, borra el archivo db_local.sqlite3
echo ============================================================
start "" http://127.0.0.1:8000/ingresar/
python manage.py runserver 8000
