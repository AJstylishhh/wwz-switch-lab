# WWZ lab helper (Windows)
# Run in PowerShell from the repo folder. Firewall rules need Admin once.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== WWZ Switch lab ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Install from https://www.python.org/downloads/ and tick Add to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Your IPv4 addresses:" -ForegroundColor Yellow
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" } |
    Select-Object IPAddress, InterfaceAlias |
    Format-Table -AutoSize

Write-Host "Put the IP the Switch can reach into atmosphere hosts (see hosts-snippet.txt)" -ForegroundColor Yellow
Write-Host ""

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    foreach ($port in 11702, 11704) {
        $name = "WWZ Lab $port"
        if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow | Out-Null
            Write-Host "Firewall allow TCP $port" -ForegroundColor Green
        } else {
            Write-Host "Firewall rule already exists for $port" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "Not admin: skip firewall. If Switch cannot connect, re-run this script as Administrator once." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Starting server.py … Ctrl+C to stop" -ForegroundColor Cyan
python server.py
