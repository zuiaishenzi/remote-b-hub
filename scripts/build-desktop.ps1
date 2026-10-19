param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
Push-Location $repoPath
try {
    $pythonPath = Join-Path $repoPath '.venv-build\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & py -3.14 -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment' }
    }
    if (-not $SkipInstall) {
        & $pythonPath -m pip install -r windows-b/requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
        & $pythonPath -m pip install -r tests/requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Test dependency installation failed' }
    }
    & $pythonPath -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed' }
    & $pythonPath tests/smoke_test.py
    if ($LASTEXITCODE -ne 0) { throw 'Relay API smoke test failed' }
    & $pythonPath tests/e2e_http_test.py
    if ($LASTEXITCODE -ne 0) { throw 'Relay HTTP integration test failed' }
    & $pythonPath windows-b/desktop_version.py build/runtime-info.json
    if ($LASTEXITCODE -ne 0) { throw 'Could not fingerprint executor sources' }
    & $pythonPath -m PyInstaller --noconfirm --clean --onefile --windowed --name RemoteBHub --paths windows-b --add-data 'build/runtime-info.json;.' --add-data 'windows-b/interop;interop' --hidden-import win32timezone --hidden-import win32com.client --hidden-import win32com.server --hidden-import win32crypt --hidden-import win32ts windows-b/desktop_launcher.py
    if ($LASTEXITCODE -ne 0) { throw 'EXE build failed' }
    $testDirectory = Join-Path $repoPath ('build\desktop-self-test-' + [guid]::NewGuid())
    $appPath = Join-Path $repoPath 'dist\RemoteBHub.exe'
    $argumentList = @('--self-test', '--data-dir', ('"' + $testDirectory + '"'))
    $process = Start-Process -FilePath $appPath -ArgumentList $argumentList -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath "$testDirectory\self-test.json")) { throw 'Frozen EXE self-test failed' }
    $process = Start-Process -FilePath $appPath -ArgumentList @('--smoke-test', '--data-dir', ('"' + $testDirectory + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath "$testDirectory\gui-smoke.json")) { throw 'Frozen GUI smoke test failed' }
    & $pythonPath tests/frozen_desktop_smoke.py $appPath
    if ($LASTEXITCODE -ne 0) { throw 'Frozen worker HTTP smoke test failed' }
    & $pythonPath -m PyInstaller --noconfirm --clean --onefile --windowed --name RemoteBClient --paths windows-a --paths windows-b --hidden-import win32crypt windows-a/client_gui.py
    if ($LASTEXITCODE -ne 0) { throw 'A client EXE build failed' }
    $clientPath = Join-Path $repoPath 'dist\RemoteBClient.exe'
    $clientTestDirectory = Join-Path $testDirectory 'a-client'
    $process = Start-Process -FilePath $clientPath -ArgumentList @('--smoke-test', '--data-dir', ('"' + $clientTestDirectory + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath "$clientTestDirectory\client-smoke.json")) { throw 'A client EXE smoke test failed' }
    Get-FileHash -Algorithm SHA256 -LiteralPath $appPath | Format-List
    Write-Host "Built and checked: $appPath"
} finally {
    Pop-Location
}
