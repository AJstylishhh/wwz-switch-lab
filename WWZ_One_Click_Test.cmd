@echo off
setlocal
title WWZ Switch - Echo Test
cd /d "%~dp0"
if not exist "%~dp0run_wwz_echo_test.ps1" (
    echo ERROR: run_wwz_echo_test.ps1 is missing.
    echo Keep the CMD and PS1 files together in the research project folder.
    pause
    exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_wwz_echo_test.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
    echo Test finished. Please send WWZ_Echo_Test_Report.txt from your Desktop.
) else (
    echo Test failed. Please check the error above and the Desktop report.
)
pause
exit /b %EXITCODE%
