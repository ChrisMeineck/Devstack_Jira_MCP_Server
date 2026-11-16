@echo off
setlocal enabledelayedexpansion

echo === devstack-jira-mcp starten ===
cd /d "%~dp0"

REM Python-Detektion: bevorzugt python_, dann py, dann python
set PYTHON_CMD=

python_ --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python_
    goto :found
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto :found
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :found
)

echo [FEHLER] Python nicht gefunden. Bitte python_, py oder python im PATH bereitstellen.
pause
exit /b 1

:found
echo Python-Befehl: %PYTHON_CMD%
%PYTHON_CMD% --version

REM Dependencies idempotent installieren (global, kein venv)
if not exist ".deps-installed" (
    echo Installiere Abhaengigkeiten aus requirements.txt ...
    %PYTHON_CMD% -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo [FEHLER] pip install fehlgeschlagen.
        pause
        exit /b 1
    )
    echo. > .deps-installed
)

echo Starte mcp_server.py ...
%PYTHON_CMD% mcp_server.py
pause
