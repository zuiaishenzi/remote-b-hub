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
    }
    & $pythonPath -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed' }
    & $pythonPath -m PyInstaller --noconfirm --clean --onefile --windowed --name RemoteBHub --paths windows-b --hidden-import win32timezone --hidden-import win32com.client --hidden-import win32com.server --hidden-import win32crypt --hidden-import win32ts windows-b/desktop_launcher.py
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
    Get-FileHash -Algorithm SHA256 -LiteralPath $appPath | Format-List
    Write-Host "Built and checked: $appPath"
} finally {
    Pop-Location
}
