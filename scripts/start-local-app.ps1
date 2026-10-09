param([string]$Device = '127.0.0.1:5555')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
# Run in a child scope so an already-running server does not end this launcher.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-local-mobile.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Local server startup failed.' }
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Local server is not ready. Check outputs/local-server.error.log.' }
& (Join-Path $PSScriptRoot 'connect-bluestacks.ps1') -Device $Device
