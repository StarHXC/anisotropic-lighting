@echo off
title Anisotropic Lighting Bake

set "PYTHON=C:\Users\xingcan.huang\AppData\Local\Programs\Python\Python312\python.exe"
set "SCRIPT=%~dp0aniso_bake.py"

if not exist "%PYTHON%" (
    echo [ERROR] Python not found. Edit this bat and fix the PYTHON path.
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo [ERROR] aniso_bake.py not found: %SCRIPT%
    pause
    exit /b 1
)

cd /d "%~dp0"
echo Baking with current config.json ...
"%PYTHON%" "%SCRIPT%" --bake --accept-unverified
echo.
echo Done. Output: out\anisotropic_lightmap.png
pause
