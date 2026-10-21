# WWZ lab helper — assumes ICS PC IP 192.168.137.1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== WWZ Switch lab ===" -ForegroundColor Cyan
Write-Host "Expected PC IP for Switch hosts: 192.168.137.1 (ICS)" -ForegroundColor Yellow
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Python not found. Install from python.org and tick Add to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Current IPv4 addresses:" -ForegroundColor Yellow
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" } |
    Select-Object IPAddress, InterfaceAlias |
    Format-Table -AutoSize

$hasIcs = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -eq "192.168.137.1" }
if (-not $hasIcs) {
    Write-Host "WARNING: 192.168.137.1 not found. Turn on ICS or update hosts-snippet.txt if your IP changed." -ForegroundColor Red
} else {
    Write-Host "OK: 192.168.137.1 is present" -ForegroundColor Green
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    foreach ($port in 11702, 11704) {
        $name = "WWZ Lab $port"
        if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow | Out-Null
            Write-Host "Firewall allow TCP $port" -ForegroundColor Green
        }
    }
} else {
    Write-Host "Not admin: skip firewall. Re-run as Administrator once if Switch cannot connect." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Starting server.py … Ctrl+C to stop" -ForegroundColor Cyan
python server.py
