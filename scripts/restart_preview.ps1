$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$servePath = Join-Path $projectRoot 'scripts\serve.py'
$processes = Get-CimInstance Win32_Process
$serviceIds = @($processes | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($servePath) } | Select-Object -ExpandProperty ProcessId)
for ($pass = 0; $pass -lt 6; $pass++) {
    $serviceIds += @($processes | Where-Object { $serviceIds -contains $_.ParentProcessId } | Select-Object -ExpandProperty ProcessId)
    $serviceIds = @($serviceIds | Sort-Object -Unique)
}
foreach ($service in ($processes | Where-Object { $serviceIds -contains $_.ProcessId })) {
    Stop-Process -Id $service.ProcessId -ErrorAction SilentlyContinue
}
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$command = '"' + $pythonPath + '" "' + $servePath + '"'
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [UInt16]0 }
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $projectRoot; ProcessStartupInformation = $startup }
if ($created.ReturnValue -ne 0) { throw "Local preview launch failed: $($created.ReturnValue)" }
Write-Output "Preview supervisor PID: $($created.ProcessId)"
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $system = Invoke-RestMethod -Uri 'http://127.0.0.1:5180/api/system' -TimeoutSec 2
        if ($system.source_is_current) { Write-Output "Ready: http://127.0.0.1:5180/ | dynamics $($system.dynamics_hash)"; exit 0 }
    } catch { }
}
throw 'Preview did not become ready. Inspect logs/preview.err.log.'
