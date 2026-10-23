param([switch]$SkipVisual,[switch]$VisualOnly)
$ErrorActionPreference = 'Stop'
if ($SkipVisual -and $VisualOnly) { throw 'Choose SkipVisual or VisualOnly, not both.' }
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$evidence = Join-Path $projectRoot 'docs\evidence\2026-10-23'
$cases = @(
    @{ name='cpu-50'; hz=50; gpu=$false; visual=$false; tracing=$false },
    @{ name='cpu-120'; hz=120; gpu=$false; visual=$false; tracing=$false },
    @{ name='cpu-240'; hz=240; gpu=$false; visual=$false; tracing=$false },
    @{ name='cuda-120'; hz=120; gpu=$true; visual=$false; tracing=$false }
)
if ($VisualOnly) { $cases = @() }
if (-not $SkipVisual) {
    $cases += @{ name='rtx-real-time'; hz=120; gpu=$false; visual=$true; tracing=$false }
    $cases += @{ name='rtx-path-tracing'; hz=120; gpu=$false; visual=$true; tracing=$true }
}
$results = @()
$summaryFile = Join-Path $evidence 'isaac-validation-matrix.json'
if ($VisualOnly -and (Test-Path -LiteralPath $summaryFile)) {
    $existing = Get-Content -LiteralPath $summaryFile -Raw | ConvertFrom-Json
    $results = @($existing.cases | Where-Object { $_.case -notlike 'rtx-*' })
}
foreach ($case in $cases) {
    $report = Join-Path $evidence ('matrix-' + $case.name + '.json')
    $log = Join-Path $projectRoot ('logs\matrix-' + $case.name + '.log')
    $launchOptions = @{ Headless=(-not $case.visual); Diagnostic=$true; Flow=[bool]$case.visual; PathTracing=[bool]$case.tracing }
    $nativeArguments = @('--physics-hz',[string]$case.hz,'--output',$report)
    if ($case.gpu) { $nativeArguments += '--gpu-physics' }
    & (Join-Path $PSScriptRoot 'run_isaac.ps1') @launchOptions -RunnerArguments $nativeArguments *> $log
    if ($LASTEXITCODE -ne 0) { throw "Native matrix case $($case.name) exited $LASTEXITCODE. See $log" }
    $value = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if ($value.status -ne 'passed' -or $value.source_changed_during_run) { throw "Native matrix case did not qualify: $report" }
    $runtimeErrors = @(Select-String -LiteralPath $log -Pattern '\[Error\]|CUDA error|out.of.memory|illegal memory access|device lost|disjointed body transforms')
    if ($runtimeErrors.Count) { $runtimeErrors | Select-Object -First 5; throw "Native matrix case has runtime errors: $log" }
    $results += @{ case=$case.name; status=$value.status; report=$report; height_error=$value.vacuum_drop_height_error; angular_momentum_error=$value.pusher_relative_angular_momentum_error }
    Write-Output "PASS $($case.name)"
}
$manifests = @($results | ForEach-Object { (Get-Content -LiteralPath $_.report -Raw | ConvertFrom-Json).source_manifest | ConvertTo-Json -Compress })
if (@($manifests | Select-Object -Unique).Count -ne 1) { throw 'Matrix source manifests differ. Rerun the full matrix with unchanged source files.' }
@{status='passed';cases=$results} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $summaryFile -Encoding utf8
