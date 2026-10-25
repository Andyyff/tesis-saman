@echo off
rem Lo lanza el Programador de tareas de Windows cada hora (tarea "Tesis Saman - flujo").
rem El flujo corre en GitHub Actions; esto solo baja lo nuevo a esta carpeta de OneDrive (la lee Power BI).
rem Log en datos\actualizar.log. Para correr el flujo en esta PC a mano: correr_flujo.cmd
cd /d "%~dp0"
echo ===== %date% %time% >> datos\actualizar.log
"C:\Program Files\Git\cmd\git.exe" pull --ff-only >> datos\actualizar.log 2>&1
