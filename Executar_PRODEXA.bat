@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Nao foi possivel instalar as dependencias.
    pause
    exit /b 1
)
py "extrator_decathlon_v36_4_filtro3 (1).py"
if errorlevel 1 pause