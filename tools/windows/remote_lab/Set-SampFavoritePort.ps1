param(
    [string]$Root = "C:\samp-test",
    [ValidateRange(0, 100)][int]$FavoriteIndex,
    [string]$ExpectedHost,
    [ValidateRange(1, 65535)][int]$ExpectedPort,
    [ValidateRange(1, 65535)][int]$NewPort
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Common.ps1")

if (@(Get-SampLabProcesses).Count -gt 0) {
    throw "Refusing to edit SA-MP favorites while GTA/SA-MP is running."
}
if ($ExpectedHost.Length -gt 253 -or $ExpectedHost -notmatch '^[A-Za-z0-9.-]+$') {
    throw "ExpectedHost contains unsupported characters."
}

$config = Get-SampLabConfig -Root $Root
$interactiveUser = ([string]$config.interactive_user).Split("\")[-1]
$userDataPath = Join-Path "C:\Users\$interactiveUser\Documents\GTA San Andreas User Files\SAMP" "USERDATA.DAT"
if (-not (Test-Path -LiteralPath $userDataPath)) {
    throw "SA-MP USERDATA.DAT not found: $userDataPath"
}

$bytes = [IO.File]::ReadAllBytes($userDataPath)
if ($bytes.Length -lt 16 -or [Text.Encoding]::ASCII.GetString($bytes, 0, 4) -cne "SAMP") {
    throw "Unexpected SA-MP USERDATA.DAT header."
}
$declaredCount = [BitConverter]::ToUInt32($bytes, 8)
if ($FavoriteIndex -ge $declaredCount) {
    throw "FavoriteIndex $FavoriteIndex is outside declared count $declaredCount."
}

# SA-MP R5 stores each endpoint as uint32 byte length, raw host bytes, then a
# little-endian uint16 port. Scan only plausible host records, not title text,
# and require the requested index plus its old endpoint to match exactly.
$entries = @()
for ($offset = 12; $offset -le $bytes.Length - 7; $offset++) {
    $length = [BitConverter]::ToUInt32($bytes, $offset)
    if ($length -lt 1 -or $length -gt 253 -or $offset + 4 + $length + 2 -gt $bytes.Length) {
        continue
    }
    $endpointHost = [Text.Encoding]::UTF8.GetString($bytes, $offset + 4, $length)
    if ($endpointHost -notmatch '^[A-Za-z0-9.-]+$') {
        continue
    }
    $portOffset = $offset + 4 + $length
    $port = [BitConverter]::ToUInt16($bytes, $portOffset)
    if ($port -lt 1) {
        continue
    }
    $entries += [pscustomobject]@{
        host = $endpointHost
        port = $port
        port_offset = $portOffset
    }
}
if ($entries.Count -ne $declaredCount) {
    throw "Parsed $($entries.Count) endpoints but USERDATA.DAT declares $declaredCount."
}

$entry = $entries[$FavoriteIndex]
if ($entry.host -cne $ExpectedHost -or $entry.port -ne $ExpectedPort) {
    throw "Favorite mismatch at index ${FavoriteIndex}: expected ${ExpectedHost}:${ExpectedPort}, got $($entry.host):$($entry.port)."
}

$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $userDataPath).Hash.ToLowerInvariant()
$backupName = "USERDATA_{0}_{1}.DAT" -f (Get-Date -Format "yyyyMMdd_HHmmss"), $beforeHash.Substring(0, 12)
$backupPath = Join-Path (Join-Path $Root "backups") $backupName
Copy-Item -LiteralPath $userDataPath -Destination $backupPath

$newPortBytes = [BitConverter]::GetBytes([uint16]$NewPort)
$bytes[$entry.port_offset] = $newPortBytes[0]
$bytes[$entry.port_offset + 1] = $newPortBytes[1]
[IO.File]::WriteAllBytes($userDataPath, $bytes)

$verify = [IO.File]::ReadAllBytes($userDataPath)
$actualPort = [BitConverter]::ToUInt16($verify, $entry.port_offset)
if ($actualPort -ne $NewPort) {
    Copy-Item -LiteralPath $backupPath -Destination $userDataPath -Force
    throw "Favorite verification failed; backup restored."
}

[ordered]@{
    schema = 1
    changed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    path = $userDataPath
    favorite_index = $FavoriteIndex
    host = $ExpectedHost
    port_before = $ExpectedPort
    port_after = $actualPort
    sha256_before = $beforeHash
    sha256_after = (Get-FileHash -Algorithm SHA256 -LiteralPath $userDataPath).Hash.ToLowerInvariant()
    backup = $backupPath
} | ConvertTo-Json -Depth 4
