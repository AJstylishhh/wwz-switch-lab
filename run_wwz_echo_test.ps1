# WWZ automatic Windows echo test. Authored by OpenAI ChatGPT (GPT-6).
# Does not expose packets, tokens, credentials or player identities.
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$branch='research/chatgpt-hydra-server-mvp'
$repoUrl='https://github.com/AJstylishhh/wwz-switch-lab.git'
$roots=@([Environment]::GetFolderPath('Desktop'),(Join-Path $env:USERPROFILE 'OneDrive\Desktop'),(Join-Path $env:USERPROFILE 'Desktop')) | Where-Object {$_ -and (Test-Path $_ -PathType Container)} | Select-Object -Unique
if (-not $roots) { throw 'Desktop folder not found.' }
$desktop=$roots[0]
$logs=Join-Path $desktop ('WWZ_Test_Logs_'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$report=Join-Path $desktop 'WWZ_Echo_Test_Report.txt'
$udpOut=Join-Path $logs 'udp-output.txt'
$udpErr=Join-Path $logs 'udp-errors.txt'
$httpOut=Join-Path $logs 'https-output.txt'
$httpErr=Join-Path $logs 'https-errors.txt'
$testOut=Join-Path $logs 'unit-tests.txt'
$udp=$null
$http=$null
$status='NOT RUN'
function Stop-OldListeners([int[]]$ports,[bool]$udpMode) {
    $ids=@()
    foreach ($port in $ports) {
        if ($udpMode) {
            $ids+=@(Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
        } else {
            $ids+=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
        }
    }
    foreach ($procId in ($ids | Where-Object {$_ -gt 0} | Sort-Object -Unique)) {
        $info=Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
        if (-not $info) { throw "Cannot inspect process owning a required port: PID $procId" }
        $oldUdp=($info.Name -match '^(py|python|pythonw)\.exe$' -and $info.CommandLine -match '(udp_port_probe|udp_probe_compare)\.py')
        $oldHttp=($info.Name -match '^(py|python|pythonw)\.exe$' -and $info.CommandLine -match 'mvp_server\.py')
        if (($udpMode -and -not $oldUdp) -or (-not $udpMode -and -not $oldHttp)) {
            throw "Required port used by another program (PID $procId). Unrelated processes were not stopped."
        }
        Write-Host "Closing old WWZ test listener PID $procId"
        Stop-Process -Id $procId -Force
    }
}
function Stop-Ours($proc) {
    if (-not $proc) { return }
    try { $proc.Refresh(); if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } } catch {}
}
function Locate-Certs($repoPath) {
    $dirs=@((Join-Path $repoPath 'certs'))
    foreach ($base in $roots) {
        $dirs+=Join-Path $base 'wwz-switch-lab\certs'
        $dirs+=Join-Path $base 'wwz2-switch-lab-2\certs'
        $dirs+=Join-Path $base 'wwz-switch-lab-research\certs'
    }
    foreach ($dir in ($dirs | Select-Object -Unique)) {
        $crt=Join-Path $dir 'server.crt'
        $key=Join-Path $dir 'server.key'
        if ((Test-Path $crt -PathType Leaf) -and (Test-Path $key -PathType Leaf)) {
            return @{Certificate=$crt;Key=$key}
        }
    }
    throw 'Existing test TLS certificate/key not found; no credentials or folders were changed.'
}
function Save-Report {
    $lines=New-Object System.Collections.Generic.List[string]
    $lines.Add('WWZ UDP echo test | '+(Get-Date -Format s))
    $lines.Add('Outcome: '+$status)
    $lines.Add('Research branch: research/chatgpt-hydra-server-mvp')
    $lines.Add('UDP:50000 private-lab echo for 38-byte datagrams only')
    $lines.Add(' ')
    $lines.Add('=== Test results ===')
    if (Test-Path $testOut) {
        foreach ($line in (Get-Content $testOut | Select-String '^(test_|Ran |OK$|FAILED|ERROR)')) {$lines.Add($line.Line)}
    }
    $lines.Add(' ')
    $lines.Add('=== UDP statistics ===')
    if (Test-Path $udpOut) {
        foreach ($line in (Get-Content $udpOut)) {$lines.Add($line)}
    } else { $lines.Add('No UDP output available.') }
    if ((Test-Path $udpErr) -and (Get-Item $udpErr).Length -gt 0) {$lines.Add('UDP process returned errors; see local logs.')}
    $lines.Add(' ')
    $lines.Add('=== HTTPS route and timing summary ===')
    foreach ($source in @($httpOut,$httpErr)) {
        if (Test-Path $source) {
            foreach ($line in (Get-Content $source | Select-String '(Listening |POST /|Environment discovery:|Experimental .*reply:|Unmapped RPC:)')) {
                $lines.Add($line.Line)
            }
        }
    }
    $lines.Add(' ')
    $lines.Add('No UDP payloads, credential fields, raw requests or player identifiers included.')
    $lines.Add('Original process logs remain in local WWZ_Test_Logs folder.')
    Set-Content -LiteralPath $report -Value $lines -Encoding UTF8
}
try {
    Write-Host 'WWZ automatic echo test - preparing local files...'
    $git=Get-Command git -ErrorAction SilentlyContinue
    $existing=$null
    foreach ($base in $roots) {
        $candidate=Join-Path $base 'wwz-switch-lab-research'
        if (Test-Path (Join-Path $candidate '.git')) {$existing=$candidate;break}
    }
    if ($existing) {
        if (-not $git) {throw 'Git checkout found, but git.exe is unavailable.'}
        $repo=$existing
        $current=(& $git.Source -C $repo branch --show-current | Out-String).Trim()
        if ($current -ne $branch) {throw "Research checkout is on '$current'; refusing to change branches."}
        & $git.Source -C $repo pull --ff-only
        if ($LASTEXITCODE -ne 0) {throw 'Git pull failed. Local changes were not overwritten.'}
    } elseif ($git) {
        $repo=Join-Path $desktop 'wwz-switch-lab-research'
        if (Test-Path $repo) {throw 'Research folder exists but is not a Git clone. Refusing to overwrite it.'}
        & $git.Source clone --branch $branch --single-branch $repoUrl $repo
        if ($LASTEXITCODE -ne 0) {throw 'Git clone failed.'}
    } else {
        Write-Host 'Git unavailable; downloading temporary ZIP copy...'
        $zip=Join-Path $logs 'research.zip'
        $extract=Join-Path $logs 'extracted'
        $zipUrl='https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $zipUrl -OutFile $zip
        Expand-Archive -LiteralPath $zip -DestinationPath $extract
        $repo=Get-ChildItem $extract -Directory | Where-Object {(Test-Path (Join-Path $_.FullName 'mvp_server.py'))} | Select-Object -First 1 -ExpandProperty FullName
        if (-not $repo) {throw 'ZIP does not contain the research server.'}
    }
    foreach ($file in @('mvp_server.py','udp_probe_compare.py','routes.environment-production-shape.example.json')) {
        if (-not (Test-Path (Join-Path $repo $file))) {throw "Missing current research file: $file"}
    }
    $certs=Locate-Certs $repo
    $launcher=Get-Command py -ErrorAction SilentlyContinue
    if (-not $launcher) {throw 'Python launcher (py.exe) not found.'}
    $python=(& $launcher.Source -c 'import sys; print(sys.executable)' | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) {throw 'Cannot find Python interpreter.'}
    Stop-OldListeners -ports @(50000) -udpMode $true
    Stop-OldListeners -ports @(11702,11704) -udpMode $false
    Start-Sleep -Milliseconds 600
    Write-Host 'Running regression tests...'
    Push-Location $repo
    try {
        $test1 = Start-Process -FilePath $python -ArgumentList '-m unittest discover -s tests -p test_udp_probe_compare.py -v' -WorkingDirectory $repo -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'test-udp-stdout.txt') -RedirectStandardError (Join-Path $logs 'test-udp-stderr.txt')
        $udpTestText = @(Get-Content (Join-Path $logs 'test-udp-stdout.txt')) + @(Get-Content (Join-Path $logs 'test-udp-stderr.txt'))
        $udpTestText | Set-Content -LiteralPath $testOut
        if ($test1.ExitCode -ne 0) {throw 'UDP probe tests failed. Read local unit-tests.txt.'}
        $test2 = Start-Process -FilePath $python -ArgumentList '-m unittest discover -s tests -p test_production_environment_shape.py -v' -WorkingDirectory $repo -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'test-env-stdout.txt') -RedirectStandardError (Join-Path $logs 'test-env-stderr.txt')
        $envTestText = @(Get-Content (Join-Path $logs 'test-env-stdout.txt')) + @(Get-Content (Join-Path $logs 'test-env-stderr.txt'))
        $envTestText | Add-Content -LiteralPath $testOut
        if ($test2.ExitCode -ne 0) {throw 'Environment tests failed. Read local unit-tests.txt.'}
    } finally {Pop-Location}
    $udp=Start-Process -FilePath $python -ArgumentList '-u udp_probe_compare.py --echo-38 --timeout 105' -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $udpOut -RedirectStandardError $udpErr
    $httpArgs='-u mvp_server.py --host 0.0.0.0 --ports 11702,11704 --routes routes.environment-production-shape.example.json --cert "'+$certs.Certificate+'" --key "'+$certs.Key+'"'
    $http=Start-Process -FilePath $python -ArgumentList $httpArgs -WorkingDirectory $repo -PassThru -WindowStyle Hidden -RedirectStandardOutput $httpOut -RedirectStandardError $httpErr
    Start-Sleep -Seconds 2
    $udp.Refresh(); $http.Refresh()
    if ($udp.HasExited -or $http.HasExited) {throw 'A listener exited during startup; inspect the saved local logs.'}
    Write-Host ''
    Write-Host 'LAB SERVERS READY. OPEN WWZ ON THE SWITCH AND ENTER ONLINE ONCE.' -ForegroundColor Green
    Write-Host 'This program will collect the results and stop its own listeners automatically.'
    $deadline=(Get-Date).AddSeconds(110)
    while ((Get-Date) -lt $deadline) {
        $udp.Refresh(); $http.Refresh()
        if ($udp.HasExited) {break}
        if ($http.HasExited) {throw 'HTTPS server quit during the test.'}
        Start-Sleep -Milliseconds 500
    }
    $status='COMPLETED: inspect packet counts and game menu result; echo is not a real WWZ server'
} catch {
    $status='FAILED: '+$_.Exception.Message
    Write-Host $status -ForegroundColor Red
} finally {
    Stop-Ours $udp
    Stop-Ours $http
    try {Save-Report} catch {Write-Host ('Report error: '+$_.Exception.Message) -ForegroundColor Red}
}
Write-Host ''
Write-Host ('Report on Desktop: '+$report) -ForegroundColor Cyan
Write-Host 'Send just the report, not private capture files.'
if ($status -like 'FAILED:*') {exit 1}
exit 0
