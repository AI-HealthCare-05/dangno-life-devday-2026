param(
    [switch]$Download,
    [string]$BunbunZip,
    [string]$LastTickZip
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$rabbitRepo = Split-Path -Parent $PSScriptRoot
$rabbitTarget = Join-Path $rabbitRepo 'src\frontend\assets\animals\licensed-rabbits'
$rabbitTemporary = Join-Path $rabbitRepo 'tmp\rabbit-import-v158'

function Get-FreeRabbitPack([string]$Source, [string]$Destination) {
    # Official public $0 flow only. No account, email, payment, or saved cookies.
    $page = Invoke-WebRequest -Uri $Source -UseBasicParsing -SessionVariable rabbitSession
    $csrf = [regex]::Match($page.Content, '<meta name="csrf_token" value="([^"]+)"').Groups[1].Value
    if (-not $csrf) { throw "Official download form changed: $Source" }
    $lease = Invoke-RestMethod -Uri "$Source/download_url" -Method Post -WebSession $rabbitSession -Body @{csrf_token=$csrf}
    if (-not $lease.url -or -not $lease.url.StartsWith("$Source/download/")) { throw 'Unexpected download page' }
    $downloadPage = Invoke-WebRequest -Uri $lease.url -WebSession $rabbitSession -UseBasicParsing
    $uploads = [regex]::Matches($downloadPage.Content, 'data-upload_id="([0-9]+)"')
    if ($uploads.Count -ne 1) { throw 'Pack selection changed; review the official page before downloading' }
    $file = Invoke-RestMethod -Uri "$Source/file/$($uploads[0].Groups[1].Value)" -Method Post -WebSession $rabbitSession -Body @{csrf_token=$csrf}
    if (-not $file.url -or ([uri]$file.url).Scheme -ne 'https') { throw 'Missing HTTPS asset download' }
    Invoke-WebRequest -Uri $file.url -OutFile $Destination -UseBasicParsing
}

if ($Download) {
    New-Item -ItemType Directory -Path $rabbitTemporary -Force | Out-Null
    $BunbunZip = Join-Path $rabbitTemporary 'Bunbun.zip'
    $LastTickZip = Join-Path $rabbitTemporary 'Bunny.zip'
    Get-FreeRabbitPack 'https://evildumpling.itch.io/bunbun' $BunbunZip
    Get-FreeRabbitPack 'https://last-tick.itch.io/32x32-pixel-bunnies-animated-npc' $LastTickZip
}
if (-not $BunbunZip -or -not $LastTickZip) { throw 'Use -Download or supply both -BunbunZip and -LastTickZip.' }

function Install-RabbitSheet([string]$ArchivePath, [string]$EntryName, [string]$Filename, [int]$Width, [int]$Height) {
    $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ArchivePath))
    try {
        # Extract exactly one named PNG to a fixed target; never unpack paths or code.
        $entry = $archive.GetEntry($EntryName)
        if (-not $entry -or $entry.Length -gt 5MB) { throw "Missing or oversized source PNG: $EntryName" }
        $inputStream = $entry.Open()
        $memory = New-Object IO.MemoryStream
        try { $inputStream.CopyTo($memory); $bytes = $memory.ToArray() }
        finally { $inputStream.Dispose(); $memory.Dispose() }
        if ($bytes.Length -lt 24 -or [BitConverter]::ToString($bytes, 0, 8) -ne '89-50-4E-47-0D-0A-1A-0A') { throw 'Not a PNG' }
        $pngWidth = $bytes[16]*16777216 + $bytes[17]*65536 + $bytes[18]*256 + $bytes[19]
        $pngHeight = $bytes[20]*16777216 + $bytes[21]*65536 + $bytes[22]*256 + $bytes[23]
        if ($pngWidth -ne $Width -or $pngHeight -ne $Height) { throw 'Source frame layout changed; update metadata before installing.' }
        New-Item -ItemType Directory -Path $rabbitTarget -Force | Out-Null
        $destination = Join-Path $rabbitTarget $Filename
        [IO.File]::WriteAllBytes($destination, $bytes)
        Get-FileHash -LiteralPath $destination -Algorithm SHA256 | Select-Object Path,Hash
    } finally { $archive.Dispose() }
}

Install-RabbitSheet $BunbunZip 'spritesheet.png' 'bunbun.png' 128 256
Install-RabbitSheet $LastTickZip 'Bunny 1 16x16 animation.png' 'last-tick.png' 352 1088
Write-Output 'Installed for this game only. Do not publish these source PNGs or the ZIPs as standalone assets.'
