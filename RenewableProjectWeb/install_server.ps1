$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $AppRoot
if (-not (Test-Path -LiteralPath '.venv')) { python -m venv .venv }
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
New-Item -ItemType Directory -Force -Path 'data','logs','output','runtime' | Out-Null
& '.\.venv\Scripts\python.exe' '.\scripts\provision_chromedriver.py'
Write-Host '安装完成。运行 run_server.ps1 后，同事可通过 http://服务器IP:8765 访问。'
