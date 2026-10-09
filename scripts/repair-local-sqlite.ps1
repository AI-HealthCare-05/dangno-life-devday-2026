param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$taskHomeLine = Get-Content -LiteralPath '.venv/pyvenv.cfg' | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $taskHomeLine) { throw 'Missing local Python runtime home' }
$taskRuntime = [IO.Path]::GetFullPath(($taskHomeLine -split '=',2)[1].Trim())
$taskPrivateRoot = Join-Path $taskRoot 'outputs/python'
if (-not $taskRuntime.StartsWith($taskPrivateRoot + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Only the project-private Python runtime can be repaired' }
$taskRuntimeItem = Get-Item -LiteralPath $taskRuntime
if ($taskRuntimeItem.LinkType -eq 'Junction' -and -not ([string]$taskRuntimeItem.Target).StartsWith($taskPrivateRoot + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime junction points outside the project' }
$taskExtension = Join-Path $taskRuntime 'DLLs/_sqlite3.pyd'
$taskVersion = (Get-Item -LiteralPath $taskExtension).VersionInfo.FileVersion
if ($taskVersion -ne '3.13.15') { throw 'This verified repair supports Python 3.13.15 only; obtain matching official package checksums for other versions' }
$taskImport = & $taskPython -c 'import sqlite3; print(sqlite3.sqlite_version)' 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host ('SQLite is available: ' + $taskImport); exit 0 }
if (-not $Apply) { Write-Host 'SQLite cannot load. Rerun this script with -Apply to back up and replace its two libraries with signed official files.'; exit 1 }
# Official package and published SHA-256: https://www.python.org/downloads/release/python-31315/
$taskUri = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip'
$taskExpected = 'd1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf'
$taskArchive = Join-Path $taskPrivateRoot 'official-sqlite-3.13.15.zip'
if (-not (Test-Path -LiteralPath $taskArchive)) { Invoke-WebRequest -Uri $taskUri -OutFile $taskArchive }
if ((Get-FileHash -LiteralPath $taskArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) { throw 'Official package checksum mismatch; no runtime changes made' }
$taskExtract = Join-Path $taskPrivateRoot ('sqlite-official-check-' + [Guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $taskArchive -DestinationPath $taskExtract
$taskFiles = @('_sqlite3.pyd','sqlite3.dll')
# Validate both files before changing either one. No security policy is modified.
foreach ($taskName in $taskFiles) {
    $taskSignature = Get-AuthenticodeSignature -LiteralPath (Join-Path $taskExtract $taskName)
    if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Missing valid Python Software Foundation signature; no runtime changes made' }
}
$taskBackup = Join-Path $taskPrivateRoot ('sqlite-before-repair-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
New-Item -ItemType Directory -Path $taskBackup | Out-Null
foreach ($taskName in $taskFiles) {
    Copy-Item -LiteralPath (Join-Path $taskRuntime ('DLLs/' + $taskName)) -Destination (Join-Path $taskBackup $taskName)
}
try {
    foreach ($taskName in $taskFiles) {
        Copy-Item -LiteralPath (Join-Path $taskExtract $taskName) -Destination (Join-Path $taskRuntime ('DLLs/' + $taskName)) -Force
    }
    & $taskPython -c 'import sqlite3; c=sqlite3.connect(":memory:"); assert c.execute("SELECT 1").fetchone()==(1,); print("Signed SQLite is available:", sqlite3.sqlite_version)'
    if ($LASTEXITCODE -ne 0) { throw 'Repaired SQLite failed validation' }
} catch {
    foreach ($taskName in $taskFiles) {
        Copy-Item -LiteralPath (Join-Path $taskBackup $taskName) -Destination (Join-Path $taskRuntime ('DLLs/' + $taskName)) -Force
    }
    throw
}
Write-Host ('Original libraries backed up in ' + $taskBackup)
