# Install the isolated Windows x64 browser helper. No user profile is selected.
param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid version' }
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 required' }
$base = Join-Path $env:LOCALAPPDATA 'Programs\agent-browser-browse'
$versions = Join-Path $base 'versions'
$target = Join-Path $versions $Version
$archive = 'agent-browser-browse-windows-x86_64.tar.gz'
$url = "https://github.com/amxv/agent-browser-browse/releases/download/v$Version"
New-Item -ItemType Directory -Force -Path $versions | Out-Null
$stage = Join-Path $base ('.stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    $download = Join-Path $stage $archive
    Invoke-WebRequest "$url/$archive" -OutFile $download
    Invoke-WebRequest "$url/SHA256SUMS" -OutFile (Join-Path $stage 'SHA256SUMS')
    $rows = @(Get-Content (Join-Path $stage 'SHA256SUMS') | Where-Object { $_ -match "^([a-fA-F0-9]{64})\s+$([regex]::Escape($archive))$" })
    if ($rows.Count -ne 1) { throw 'Missing or ambiguous SHA256' }
    $expected = ($rows[0] -split '\s+')[0]
    if ((Get-FileHash $download -Algorithm SHA256).Hash -ne $expected) { throw 'SHA256 mismatch' }
    $members = & tar.exe -tzf $download
    if ($LASTEXITCODE -ne 0) { throw 'Invalid browser archive' }
    foreach ($member in $members) {
        $name = $member -replace '^\./', ''
        if ($name -notin @('', 'agent-browser-browse-native.exe', 'LICENSE.upstream', 'UPSTREAM_VERSION', 'UPSTREAM_COMMIT', 'PATCH_SHA256')) {
            throw "Unsafe archive member: $member"
        }
    }
    $unpacked = Join-Path $stage 'unpacked'
    New-Item -ItemType Directory -Path $unpacked | Out-Null
    & tar.exe -xzf $download -C $unpacked
    if ($LASTEXITCODE -ne 0) { throw 'Archive extraction failed' }
    $native = Join-Path $unpacked 'agent-browser-browse-native.exe'
    if (-not (Test-Path $native -PathType Leaf)) { throw 'Native executable missing' }
    if ((Get-Content (Join-Path $unpacked 'UPSTREAM_VERSION') -Raw).Trim() -ne $Version) { throw 'Version mismatch' }
    # Validate PE AMD64 machine before executing downloaded code.
    $stream = [IO.File]::OpenRead($native)
    try {
        $reader = New-Object IO.BinaryReader($stream)
        if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'Not a PE executable' }
        $stream.Position = 0x3c
        $offset = $reader.ReadInt32()
        if ($offset -lt 0x40 -or $offset -gt $stream.Length - 6) { throw 'Invalid PE header' }
        $stream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x00004550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'Not a Windows x64 executable' }
    } finally { $stream.Dispose() }
    if ((& $native --version) -ne "agent-browser $Version") { throw 'Executable version mismatch' }
    if (-not (Test-Path $target)) { Move-Item $unpacked $target }
    $config = Join-Path $base 'empty-config.json'
    if (-not (Test-Path $config)) { [IO.File]::WriteAllText($config, "{}`n") }
    $wrapper = Join-Path $base 'agent-browser-browse.cmd'
    if (Test-Path $wrapper) {
        $sessions = & $wrapper session list --json | ConvertFrom-Json
        if (-not $sessions.success -or @($sessions.data.sessions).Count -ne 0) { throw 'Existing browsing sessions active or uninspectable' }
    }
    $script = "@echo off`r`nif not defined AGENT_BROWSER_NAMESPACE set `"AGENT_BROWSER_NAMESPACE=abb`"`r`nif not defined AGENT_BROWSER_CONFIG set `"AGENT_BROWSER_CONFIG=%~dp0empty-config.json`"`r`n`"%~dp0versions\$Version\agent-browser-browse-native.exe`" %*`r`n"
    $pending = Join-Path $stage 'agent-browser-browse.cmd'
    [IO.File]::WriteAllText($pending, $script)
    Move-Item $pending $wrapper -Force
    Write-Output "Installed agent-browser-browse $Version at $base. Add this directory to your user PATH."
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
