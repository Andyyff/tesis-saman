@echo off
rem Corre el flujo en esta PC (a mano; el automático corre en GitHub Actions y la PC solo baja con actualizar_datos.cmd).
rem Deja los CSV para Power BI en datos\powerbi\ y agrega la salida a datos\flujo.log.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% >> datos\flujo.log
".venv\Scripts\python.exe" flujo.py >> datos\flujo.log 2>&1
