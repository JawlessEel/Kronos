param([Parameter(Mandatory=$true)][string]$PayloadZip,
      [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'The Windows .NET Framework C# compiler is required to build this launcher.' }
$payload = (Resolve-Path -LiteralPath $PayloadZip).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$output = Join-Path (Resolve-Path -LiteralPath $OutputDirectory).Path 'Kronos-WebGPU-Setup-1.0.0.exe'
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll "/resource:$payload,KronosPayload.zip" "/out:$output" (Join-Path $PSScriptRoot 'WindowsLauncher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed' }
Get-FileHash -LiteralPath $output -Algorithm SHA256
