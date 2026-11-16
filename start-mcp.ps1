# PowerShell-Start-Skript fuer den devstack-jira-mcp Server
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Find-Python {
    # Bevorzugt den py-Launcher, sonst python aus dem PATH
    foreach ($candidate in @(@("py", "-3"), @("python"))) {
        $exe = $candidate[0]
        $prefix = @($candidate | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            & $exe @prefix --version *> $null
            if ($LASTEXITCODE -eq 0) { return , $candidate }
        } catch { continue }
    }
    throw "Python nicht gefunden. Bitte Python 3.10+ installieren (py-Launcher oder python im PATH)."
}

$python = Find-Python
$exe = $python[0]
$prefix = @($python | Select-Object -Skip 1)
Write-Host "Python-Befehl: $($python -join ' ')"
& $exe @prefix --version

& $exe @prefix -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 oder neuer wird benoetigt." }

if (-not (Test-Path ".deps-installed")) {
    Write-Host "Installiere Abhaengigkeiten ..."
    & $exe @prefix -m pip install --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen." }
    New-Item -ItemType File -Path ".deps-installed" -Force | Out-Null
}

Write-Host "Starte mcp_server.py ..."
& $exe @prefix mcp_server.py
