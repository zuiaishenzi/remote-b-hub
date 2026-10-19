param([Parameter(Mandatory=$true)][string]$InteropDirectory,
      [Parameter(Mandatory=$true)][string]$DestinationExe)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$library = Join-Path $InteropDirectory 'SolidWorks.Interop.sldworks.dll'
if (-not (Test-Path -LiteralPath $compiler)) { throw '.NET Framework x64 C# compiler is unavailable' }
if (-not (Test-Path -LiteralPath $library)) { throw 'SOLIDWORKS Interop DLL is unavailable' }
$sourceFile = Join-Path $PSScriptRoot 'SwInteropController.cs'
& $compiler /nologo /target:exe /platform:x64 "/out:$DestinationExe" "/reference:$library" /reference:Microsoft.CSharp.dll /reference:System.Web.Extensions.dll $sourceFile
if ($LASTEXITCODE -ne 0) { throw 'C# compile failed' }
