$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python environment is missing. See docs/mobile/LOCAL_DEVELOPMENT.md.' }
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener[0].OwningProcess)
    if ($owner.ExecutablePath -and $owner.ExecutablePath.StartsWith($projectRoot + '\')) {
        Write-Host 'Local server is already running: http://127.0.0.1:8000'
        exit 0
    }
    throw 'Another application is using port 8000.'
}
New-Item -ItemType Directory -Force -Path outputs | Out-Null
$verifiedPython = Join-Path $projectRoot 'outputs/python/official-sqlite-3.13.15/python.exe'
if (Test-Path -LiteralPath $verifiedPython) {
    $signature = Get-AuthenticodeSignature -LiteralPath $verifiedPython
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Official Python signature verification failed.' }
    # A virtual-environment launcher may start successfully, then have a native
    # dependency blocked during import. Prefer the verified runtime before startup.
    $python = $verifiedPython
    Write-Host 'Using the verified Python runtime with existing project dependencies.'
}
$server = Start-Process -FilePath $python -ArgumentList 'scripts/run-local-mobile.py' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput outputs/local-server.log -RedirectStandardError outputs/local-server.error.log -PassThru
$server.Id | Set-Content outputs/local-server.pid
Write-Host 'Local server starting: http://127.0.0.1:8000'
Write-Host 'Logs: outputs/local-server.error.log'
