param([string]$Device = '127.0.0.1:5555', [switch]$Install)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$adb = $env:MOBILE_ADB
if (-not $adb) { $adb = Join-Path $projectRoot 'outputs/mobile/toolchain/sdk/platform-tools/adb.exe' }
if (-not (Test-Path -LiteralPath $adb)) { throw 'ADB is missing. Set MOBILE_ADB to the Android SDK adb.exe.' }
& $adb connect $Device
if ($LASTEXITCODE -ne 0) { throw 'BlueStacks connection failed.' }
$connected = $false
for ($attempt = 0; $attempt -lt 3; $attempt++) {
    $state = & $adb -s $Device get-state 2>$null
    if ($LASTEXITCODE -eq 0 -and $state -eq 'device') { $connected = $true; break }
    & $adb disconnect $Device | Out-Null
    & $adb connect $Device | Out-Null
    Start-Sleep -Seconds 1
}
if (-not $connected) { throw 'BlueStacks is not ready. Start BlueStacks and try again.' }
& $adb -s $Device reverse tcp:8000 tcp:8000
if ($LASTEXITCODE -ne 0) { throw 'Local server forwarding failed.' }
if ($Install) {
    & $adb -s $Device install -r src/frontend/native/android/app/build/outputs/apk/debug/app-debug.apk
    if ($LASTEXITCODE -ne 0) { throw 'APK installation failed.' }
}
& $adb -s $Device shell am start -n life.dangno.app/.MainActivity
if ($LASTEXITCODE -ne 0) { throw 'App launch failed.' }
