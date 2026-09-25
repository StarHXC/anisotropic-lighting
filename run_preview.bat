@echo off
title Anisotropic Lighting Preview

set "PYTHON=C:\Users\xingcan.huang\AppData\Local\Programs\Python\Python312\python.exe"
set "SCRIPT=%~dp0preview.py"

if not exist "%PYTHON%" (
    echo [ERROR] Python not found. Edit this bat and fix the PYTHON path.
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo [ERROR] preview.py not found: %SCRIPT%
    pause
    exit /b 1
)

cd /d "%~dp0"
echo Starting preview...
"%PYTHON%" "%SCRIPT%"
if errorlevel 1 (
    echo.
    echo [ERROR] Preview exited with an error. See messages above.
    pause
)
