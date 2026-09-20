$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $AppRoot
$Python = Join-Path $AppRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Runtime is not installed. Run install_server.ps1 first.'
}
& $Python -m uvicorn app:app --host 0.0.0.0 --port 8765
