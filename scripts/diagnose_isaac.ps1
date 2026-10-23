param([switch]$GpuPhysics,[switch]$Visual,[switch]$Flow,[switch]$PathTracing,[switch]$AcceptNvidiaLicense)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$evidenceFolder = Join-Path $projectRoot 'docs\evidence\2026-10-23'
$logsFolder = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $evidenceFolder,$logsFolder | Out-Null
$mode = if ($PathTracing) { 'path-tracing' } elseif ($Visual) { 'visual' } elseif ($GpuPhysics) { 'cuda-physics' } else { 'headless' }
$reportFile = Join-Path $evidenceFolder ('isaac-' + $mode + '.json')
$logFile = Join-Path $logsFolder ('isaac-' + $mode + '.log')
$options = @{ Headless = (-not ($Visual -or $PathTracing)); Diagnostic = $true; Flow = [bool]$Flow; PathTracing = [bool]$PathTracing; AcceptNvidiaLicense = [bool]$AcceptNvidiaLicense }
$extraArguments = @('--output',$reportFile)
if ($GpuPhysics) { $extraArguments += '--gpu-physics' }
& (Join-Path $PSScriptRoot 'run_isaac.ps1') @options -RunnerArguments $extraArguments *> $logFile
$nativeExitCode = $LASTEXITCODE
$logErrors = @(Select-String -LiteralPath $logFile -Pattern 'CUDA error|out.of.memory|illegal memory access|ERROR_OUT_OF_DEVICE_MEMORY|device lost')
if ($nativeExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportFile)) {
    Get-Content -LiteralPath $logFile -Tail 45
    throw "Native diagnostic failed (exit $nativeExitCode). Log: $logFile"
}
$nativeReport = Get-Content -LiteralPath $reportFile -Raw | ConvertFrom-Json
if ($nativeReport.status -ne 'passed' -or $logErrors.Count -gt 0) {
    $logErrors | Select-Object -First 8
    throw "Native diagnostic did not pass cleanly. Report: $reportFile"
}
$nativeReport | ConvertTo-Json -Depth 6
