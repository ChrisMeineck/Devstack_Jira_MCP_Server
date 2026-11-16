@echo off
setlocal enabledelayedexpansion

echo === devstack-jira-mcp starten ===
cd /d "%~dp0"

REM Python-Detektion: bevorzugt den py-Launcher, sonst python aus dem PATH
set PYTHON_CMD=

py -3 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py -3
    goto :found
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :found
)

echo [FEHLER] Python nicht gefunden. Bitte Python 3.10+ installieren (py-Launcher oder python im PATH).
pause
exit /b 1

:found
echo Python-Befehl: %PYTHON_CMD%
%PYTHON_CMD% --version

%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [FEHLER] Python 3.10 oder neuer wird benoetigt.
    pause
    exit /b 1
)

REM Dependencies idempotent installieren (kein venv)
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
