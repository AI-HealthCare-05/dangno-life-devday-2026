$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path outputs/local-server.pid)) { Write-Host 'No local server PID recorded.'; exit 0 }
$serverPid = [int](Get-Content outputs/local-server.pid)
$processes = @(Get-CimInstance Win32_Process)
$server = $processes | Where-Object ProcessId -eq $serverPid
if (-not $server) { Write-Host 'Server already stopped.'; exit 0 }
if (-not $server.ExecutablePath.StartsWith($projectRoot + '\') -or $server.CommandLine -notlike '*run-local-mobile.py*') {
    throw 'Recorded PID is not this project server. Refusing to stop it.'
}
$ids = [Collections.Generic.List[int]]::new()
$ids.Add($serverPid)
for ($i = 0; $i -lt $ids.Count; $i++) {
    foreach ($child in $processes | Where-Object ParentProcessId -eq $ids[$i]) { $ids.Add([int]$child.ProcessId) }
}
for ($i = $ids.Count - 1; $i -ge 0; $i--) { Stop-Process -Id $ids[$i] -Force -ErrorAction SilentlyContinue }
Write-Host 'Local server stopped.'
