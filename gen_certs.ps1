# Generate lab TLS cert for wwz.wwzapi.com (and aliases)
# Run once from the repo folder in PowerShell.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path "certs" -Force | Out-Null

$openssl = $null
foreach ($c in @(
    "C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
    "C:\Program Files\OpenSSL-Win32\bin\openssl.exe",
    "openssl"
)) {
    if ($c -eq "openssl") {
        if (Get-Command openssl -ErrorAction SilentlyContinue) { $openssl = "openssl"; break }
    } elseif (Test-Path $c) { $openssl = $c; break }
}

if ($openssl) {
    Write-Host "Using OpenSSL: $openssl" -ForegroundColor Cyan
    $cfg = @"
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = wwz.wwzapi.com
O = WWZ Lab
C = US

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = wwz.wwzapi.com
DNS.2 = wwz-production.wwzapi.com
DNS.3 = wwzprod.wwzapi.com
DNS.4 = rlx.hydrapi.net
DNS.5 = rlxp1a1l.hydrapi.net
"@
    $cfgPath = Join-Path $PSScriptRoot "certs\openssl.cnf"
    Set-Content -Path $cfgPath -Value $cfg -Encoding ASCII
    & $openssl req -x509 -newkey rsa:2048 -nodes `
        -keyout "certs\server.key" `
        -out "certs\server.crt" `
        -days 825 `
        -config $cfgPath
    Write-Host "Created certs\server.crt and certs\server.key" -ForegroundColor Green
    exit 0
}

Write-Host "OpenSSL not found — using PowerShell certificate store + export" -ForegroundColor Yellow

$cert = New-SelfSignedCertificate `
    -DnsName "wwz.wwzapi.com", "wwz-production.wwzapi.com", "wwzprod.wwzapi.com", "rlx.hydrapi.net", "rlxp1a1l.hydrapi.net" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears(2) `
    -KeyExportPolicy Exportable `
    -KeySpec KeyExchange

$pwd = ConvertTo-SecureString -String "wwzlab" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "certs\server.pfx" -Password $pwd | Out-Null

# Export public cert PEM
$certBytes = $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
$b64 = [Convert]::ToBase64String($certBytes, [Base64FormattingOptions]::InsertLineBreaks)
$pemCert = "-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----`n"
Set-Content -Path "certs\server.crt" -Value $pemCert -Encoding ASCII

# Try openssl for key from pfx if available later; else instruct user
Write-Host "Wrote certs\server.crt" -ForegroundColor Green
Write-Host "Wrote certs\server.pfx (password: wwzlab)" -ForegroundColor Green
Write-Host ""
Write-Host "Install OpenSSL-Win64, then run:" -ForegroundColor Yellow
Write-Host '  & "C:\Program Files\OpenSSL-Win64\bin\openssl.exe" pkcs12 -in certs\server.pfx -nocerts -nodes -out certs\server.key -passin pass:wwzlab'
Write-Host "Or re-run this script after OpenSSL is installed (preferred path creates .key automatically)."
