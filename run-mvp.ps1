$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path "certs\server.crt") -or -not (Test-Path "certs\server.key")) {
    Write-Error "No TLS test certificate. Run .\gen_certs.ps1 first."
    exit 1
}
Write-Host "WWZ MVP + soft-session (NOT playable matchmaking)" -ForegroundColor Cyan
Write-Host "Stop other listeners on 11702/11704 first." -ForegroundColor Yellow
py mvp_server.py --host 0.0.0.0 --capture-dir captures
