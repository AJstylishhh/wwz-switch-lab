# Starts only the active WWZ HTTPS+protobuf research MVP on the test PC.
# PowerShell: .\run-mvp.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path "certs\server.crt") -or -not (Test-Path "certs\server.key")) {
    Write-Error "No TLS test certificate. Run .\gen_certs.ps1 first."
    exit 1
}
Write-Host "WWZ experimental backend (NOT a playable server)" -ForegroundColor Cyan
Write-Host "This listens on TCP 11702 and 11704. Stop any existing server.py first." -ForegroundColor Yellow
py mvp_server.py --host 0.0.0.0
