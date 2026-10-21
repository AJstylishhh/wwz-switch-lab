# Generate lab TLS cert for wwz.wwzapi.com
# Run:  .\gen_certs.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Path "certs" -Force | Out-Null

$opensslCandidates = @(
    "C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
    "C:\Program Files\OpenSSL-Win32\bin\openssl.exe"
)
$openssl = $null
foreach ($c in $opensslCandidates) {
    if (Test-Path $c) {
        $openssl = $c
        break
    }
}
if (-not $openssl) {
    $cmd = Get-Command openssl -ErrorAction SilentlyContinue
    if ($cmd) { $openssl = $cmd.Source }
}

if ($openssl) {
    Write-Host "Using OpenSSL: $openssl" -ForegroundColor Cyan

    $cfgLines = @(
        "[req]",
        "default_bits = 2048",
        "prompt = no",
        "default_md = sha256",
        "distinguished_name = dn",
        "x509_extensions = v3_req",
        "",
        "[dn]",
        "CN = wwz.wwzapi.com",
        "O = WWZ Lab",
        "C = US",
        "",
        "[v3_req]",
        "subjectAltName = @alt_names",
        "basicConstraints = CA:FALSE",
        "keyUsage = digitalSignature, keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "",
        "[alt_names]",
        "DNS.1 = wwz.wwzapi.com",
        "DNS.2 = wwz-production.wwzapi.com",
        "DNS.3 = wwzprod.wwzapi.com",
        "DNS.4 = rlx.hydrapi.net",
        "DNS.5 = rlxp1a1l.hydrapi.net"
    )
    $cfgPath = Join-Path $PSScriptRoot "certs\openssl.cnf"
    $cfgLines | Set-Content -Path $cfgPath -Encoding ASCII

    & $openssl req -x509 -newkey rsa:2048 -nodes -keyout "certs\server.key" -out "certs\server.crt" -days 825 -config $cfgPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "OpenSSL failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "SUCCESS: certs\server.crt and certs\server.key" -ForegroundColor Green
    exit 0
}

Write-Host "OpenSSL not found. Using PowerShell + openssl export path." -ForegroundColor Yellow
Write-Host "If this fails, install OpenSSL-Win64 and re-run." -ForegroundColor Yellow

$cert = New-SelfSignedCertificate `
    -DnsName @("wwz.wwzapi.com", "wwz-production.wwzapi.com", "wwzprod.wwzapi.com", "rlx.hydrapi.net", "rlxp1a1l.hydrapi.net") `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears(2) `
    -KeyExportPolicy Exportable `
    -KeySpec KeyExchange

$pwd = ConvertTo-SecureString -String "wwzlab" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath "certs\server.pfx" -Password $pwd | Out-Null

$certBytes = $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
$b64 = [Convert]::ToBase64String($certBytes, [Base64FormattingOptions]::InsertLineBreaks)
$pemCert = "-----BEGIN CERTIFICATE-----`r`n$b64`r`n-----END CERTIFICATE-----`r`n"
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot "certs\server.crt"), $pemCert)

Write-Host "Wrote certs\server.crt and certs\server.pfx" -ForegroundColor Green
Write-Host "Need server.key next. Run this AFTER OpenSSL is installed:" -ForegroundColor Yellow
Write-Host ""
Write-Host "& 'C:\Program Files\OpenSSL-Win64\bin\openssl.exe' pkcs12 -in certs\server.pfx -nocerts -nodes -out certs\server.key -passin pass:wwzlab"
Write-Host ""
Write-Host "Preferred: install OpenSSL-Win64, delete certs folder, run .\gen_certs.ps1 again." -ForegroundColor Cyan
