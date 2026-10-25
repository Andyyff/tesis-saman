@echo off
rem Lo lanza el Programador de tareas de Windows cada hora (tarea "Tesis Saman - flujo").
rem Deja los CSV para Power BI en datos\powerbi\ y agrega la salida a datos\flujo.log.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% >> datos\flujo.log
".venv\Scripts\python.exe" flujo.py >> datos\flujo.log 2>&1
