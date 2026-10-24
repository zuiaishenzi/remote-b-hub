$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$zipPath = Join-Path $repoPath 'build/blender-4.2.23-windows-x64.zip'
$extractPath = Join-Path $repoPath 'build/blender-validation'
$exePath = Join-Path $extractPath 'blender-4.2.23-windows-x64/blender.exe'
if (-not (Test-Path -LiteralPath $exePath)) {
    New-Item -ItemType Directory -Path (Split-Path $zipPath) -Force | Out-Null
    curl.exe --fail --location --retry 2 --output $zipPath https://download.blender.org/release/Blender4.2/blender-4.2.23-windows-x64.zip
    if ($LASTEXITCODE -ne 0) { throw 'Official Blender test download failed' }
    $expectedHash = '82e791475779a7342424a480bdde9a20b43710da9264c60346125aa16cd910cb'
    if ((Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Official Blender SHA256 mismatch' }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
}
if ($env:GITHUB_ENV) { "REMOTE_B_TEST_BLENDER=$exePath" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append }
Write-Output $exePath
