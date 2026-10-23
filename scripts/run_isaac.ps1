[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Headless,
    [switch]$Diagnostic,
    [switch]$PathTracing,
    [switch]$Flow,
    [switch]$AcceptNvidiaLicense,
    [string]$IsaacRoot = 'D:\AppInstalled\NVIDIA\IsaacSim\6.2.0',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$RunnerArguments
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonWrapper = Join-Path $IsaacRoot 'python.bat'
if (-not (Test-Path -LiteralPath $pythonWrapper)) { throw "Isaac runtime not installed at $IsaacRoot" }
$licenseRecord = Join-Path (Split-Path $IsaacRoot -Parent) 'rocket-lab-license-accepted.json'
if ($AcceptNvidiaLicense) {
    @{ accepted_at = [DateTime]::UtcNow.ToString('o'); agreement = 'https://docs.omniverse.nvidia.com/platform/latest/common/NVIDIA_Omniverse_License_Agreement.html'; source = 'Explicit human acceptance' } | ConvertTo-Json | Set-Content -LiteralPath $licenseRecord -Encoding utf8
}
if (-not (Test-Path -LiteralPath $licenseRecord)) { throw 'NVIDIA license acceptance is required. Read the agreement and use -AcceptNvidiaLicense after accepting it.' }
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
$env:OMP_NUM_THREADS = '4'
$runner = Join-Path $projectRoot 'scripts\isaac_runner.py'
$nativeArguments = @($runner)
if ($Headless) { $nativeArguments += '--headless' }
if ($Diagnostic) { $nativeArguments += '--diagnostic' }
if ($PathTracing) { $nativeArguments += @('--renderer','path-tracing') }
if ($Flow) { $nativeArguments += '--flow' }
$nativeArguments += $RunnerArguments
& $pythonWrapper @nativeArguments
exit $LASTEXITCODE
