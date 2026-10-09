param(
    [switch]$Download,
    [string]$FreePackZip,
    [string]$WinterZip,
    [string]$ValentineZip,
    [switch]$ListOnly
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$kittenRepo = Split-Path -Parent $PSScriptRoot
$kittenTarget = Join-Path $kittenRepo 'src\frontend\assets\animals\licensed-kittens'
$kittenTemporary = Join-Path $kittenRepo 'tmp\kitten-import-v164'
$kittenSource = 'https://last-tick.itch.io/animated-pixel-kittens-cats-32x32'

function Get-FreeKittenPacks {
    # Official public $0 flow only: no account, email, payment, or browser cookies.
    # The 2026-09-08 free page exposes these exact two reviewed uploads. Never
    # request Kittens pack.zip, Room pack, or an ID absent from that $0 page.
    $allowed = @{'Free pack.zip'='15289409'; 'Winter accessories.zip'='16035254'; '14 feb.zip'='16045897'}
    $page = Invoke-WebRequest -Uri $kittenSource -UseBasicParsing -SessionVariable kittenSession
    $csrf = [regex]::Match($page.Content, '<meta name="csrf_token" value="([^"]+)"').Groups[1].Value
    if (-not $csrf) { throw 'Official free download form changed.' }
    $lease = Invoke-RestMethod -Uri "$kittenSource/download_url" -Method Post -WebSession $kittenSession -Body @{csrf_token=$csrf}
    if (-not $lease.url -or -not $lease.url.StartsWith("$kittenSource/download/")) { throw 'Unexpected official download page.' }
    $downloadPage = Invoke-WebRequest -Uri $lease.url -WebSession $kittenSession -UseBasicParsing
    $uploads = [regex]::Matches($downloadPage.Content, '(?s)<div class="upload"><a[^>]*data-upload_id="([0-9]+)".*?<strong title="([^"]+)" class="name">')
    foreach ($name in @('Free pack.zip', 'Winter accessories.zip', '14 feb.zip')) {
        $matching = @($uploads | Where-Object { $_.Groups[2].Value -eq $name -and $_.Groups[1].Value -eq $allowed[$name] })
        if ($matching.Count -ne 1) { throw "Reviewed free upload changed or is no longer free: $name" }
        $file = Invoke-RestMethod -Uri "$kittenSource/file/$($allowed[$name])" -Method Post -WebSession $kittenSession -Body @{csrf_token=$csrf}
        if (-not $file.url -or ([uri]$file.url).Scheme -ne 'https') { throw 'Missing HTTPS asset download.' }
        $destination = Join-Path $kittenTemporary $name
        Invoke-WebRequest -Uri $file.url -OutFile $destination -UseBasicParsing
        if ((Get-Item -LiteralPath $destination).Length -gt 5MB) { throw 'Source ZIP exceeds the reviewed free-pack limit.' }
        Write-Output "$name SHA256: $((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash)"
    }
}

if ($Download) {
    New-Item -ItemType Directory -Path $kittenTemporary -Force | Out-Null
    Get-FreeKittenPacks
    $FreePackZip = Join-Path $kittenTemporary 'Free pack.zip'
    $WinterZip = Join-Path $kittenTemporary 'Winter accessories.zip'
    $ValentineZip = Join-Path $kittenTemporary '14 feb.zip'
}
if (-not $FreePackZip -or -not $WinterZip -or -not $ValentineZip) { throw 'Use -Download or supply FreePackZip, WinterZip, and ValentineZip.' }

if ($ListOnly) {
    foreach ($file in @($FreePackZip, $WinterZip, $ValentineZip)) {
        $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $file))
        try { $archive.Entries | ForEach-Object { "$($_.FullName) ($($_.Length) bytes)" } }
        finally { $archive.Dispose() }
    }
    return
}

function Install-KittenSheet([string]$ArchivePath, [string]$EntryName, [string]$Filename) {
    $archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ArchivePath))
    try {
        # Extract only an exact reviewed PNG into a fixed local game directory.
        # Never execute or unpack arbitrary ZIP paths; never redraw/recolor art.
        $entry = $archive.GetEntry($EntryName)
        if (-not $entry -or $entry.Length -gt 1MB) { throw "Missing or oversized source PNG: $EntryName" }
        $inputStream = $entry.Open()
        $memory = New-Object IO.MemoryStream
        try { $inputStream.CopyTo($memory); $bytes = $memory.ToArray() }
        finally { $inputStream.Dispose(); $memory.Dispose() }
        if ($bytes.Length -lt 29 -or [BitConverter]::ToString($bytes, 0, 8) -ne '89-50-4E-47-0D-0A-1A-0A') { throw 'Not a PNG.' }
        $width = $bytes[16]*16777216 + $bytes[17]*65536 + $bytes[18]*256 + $bytes[19]
        $height = $bytes[20]*16777216 + $bytes[21]*65536 + $bytes[22]*256 + $bytes[23]
        if ($width -ne 352 -or $height -ne 1696 -or $bytes[24] -ne 8 -or $bytes[25] -ne 6) {
            throw 'Source layout changed: expected 11x53 original 32px RGBA cells. Re-audit before installing.'
        }
        New-Item -ItemType Directory -Path $kittenTarget -Force | Out-Null
        $destination = Join-Path $kittenTarget $Filename
        [IO.File]::WriteAllBytes($destination, $bytes)
        Write-Output "$Filename SHA256: $((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash)"
    } finally { $archive.Dispose() }
}

# Source names are creator-authored palette variants, not application recolors.
Install-KittenSheet $FreePackZip 'Free pack/cat 1.9.png' 'white.png'
Install-KittenSheet $FreePackZip 'Free pack/cat 1.png' 'gray.png'
Install-KittenSheet $FreePackZip 'Free pack/cat 1.6.png' 'ginger.png'
Install-KittenSheet $WinterZip 'Winter accessories/cat 1 16x16 animation with reindeer antler headband green.png' 'winter-antlers-green.png'
Install-KittenSheet $WinterZip 'Winter accessories/cat 1 16x16 animation with reindeer antler headband red.png' 'winter-antlers-red.png'
Install-KittenSheet $WinterZip 'Winter accessories/cat 1 16x16 animation with Santa hat 1.png' 'winter-santa-hat-1.png'
Install-KittenSheet $WinterZip 'Winter accessories/cat 1 16x16 animation with Santa hat 2.png' 'winter-santa-hat-2.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation cupid.png' 'valentine-cupid.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation nimbus.png' 'valentine-nimbus.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation wings.png' 'valentine-wings.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with blue bow 2.png' 'valentine-bow-blue.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with gold bow.png' 'valentine-bow-gold.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with gold glasses hearts.png' 'valentine-glasses-gold.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with green bow 2.png' 'valentine-bow-green.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with pink bow 2.png' 'valentine-bow-pink-2.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with pink bow.png' 'valentine-bow-pink.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with red bow.png' 'valentine-bow-red.png'
Install-KittenSheet $ValentineZip '14 feb/cat 1 16x16 animation with red glasses hearts.png' 'valentine-glasses-red.png'
Write-Output 'Installed three free coats and every official free winter/Valentine equipment sheet for this game only. No paid cat/room pack or furniture was downloaded. Do not redistribute standalone source art.'
