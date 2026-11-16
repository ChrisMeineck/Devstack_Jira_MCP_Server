# PowerShell-Start-Skript fuer den devstack-jira-mcp Server
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Find-Python {
    foreach ($cmd in @("python_", "py", "python")) {
        try {
            & $cmd --version *> $null
            if ($LASTEXITCODE -eq 0) { return $cmd }
        } catch { continue }
    }
    throw "Python nicht gefunden. Bitte python_, py oder python im PATH bereitstellen."
}

$python = Find-Python
Write-Host "Python-Befehl: $python"
& $python --version

if (-not (Test-Path ".deps-installed")) {
    Write-Host "Installiere Abhaengigkeiten ..."
    & $python -m pip install --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen." }
    New-Item -ItemType File -Path ".deps-installed" -Force | Out-Null
}

Write-Host "Starte mcp_server.py ..."
& $python mcp_server.py
