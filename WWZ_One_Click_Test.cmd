@echo off
setlocal
chcp 65001 >nul
title World War Z Switch - Automatic Echo Test
echo WWZ Switch test: setting up the test automatically...
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $src='https://raw.githubusercontent.com/AJstylishhh/wwz-switch-lab/0ace0b7f26df426fc22b9e0a4cf9a4669b48fbe9/run_wwz_echo_test.ps1'; $out=Join-Path $env:TEMP 'wwz_chatgpt_echo_test_0ace0b7.ps1'; try { Invoke-WebRequest -UseBasicParsing -Uri $src -OutFile $out; & $out; exit $LASTEXITCODE } catch { Write-Host ('Could not launch the WWZ test: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
set "rc=%errorlevel%"
echo.
if "%rc%"=="0" (
    echo The test finished. Send WWZ_Echo_Test_Report.txt from your Desktop.
) else (
    echo The test could not finish normally. Check the displayed error and Desktop report.
)
echo.
echo This window can be closed after you read the result.
pause
exit /b %rc%
