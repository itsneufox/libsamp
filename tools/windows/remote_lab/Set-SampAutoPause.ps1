param([string]$Root = "C:\samp-test")

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Common.ps1")

$processes = @(Get-SampLabProcesses)
if ($processes.Count -ne 0) {
    throw "Refusing to edit WindowedMode configuration while GTA/SA-MP is active."
}

$config = Get-SampLabConfig -Root $Root
$gameDir = [string]$config.game_dir
$path = Join-Path $gameDir "III.VC.SA.WindowedMode.ini"
$encoding = [Text.Encoding]::Default
$lines = if (Test-Path -LiteralPath $path) {
    @([IO.File]::ReadAllLines($path, $encoding))
} else {
    @()
}
$before = Get-SampLabAutoPauseState -GameDir $gameDir
$section = ""
$gameSectionSeen = $false
$autoPauseSeen = $false
$updated = [Collections.Generic.List[string]]::new()

foreach ($rawLine in $lines) {
    $line = $rawLine.Trim()
    if ($line.StartsWith("[") -and $line.EndsWith("]")) {
        if ($section -eq "game" -and -not $autoPauseSeen) {
            $updated.Add("autoPause = 0")
            $autoPauseSeen = $true
        }
        $section = $line.Substring(1, $line.Length - 2).Trim().ToLowerInvariant()
        if ($section -eq "game") {
            $gameSectionSeen = $true
        }
        $updated.Add($rawLine)
        continue
    }
    if ($section -eq "game" -and $line.Contains("=")) {
        $parts = $line -split "=", 2
        if ($parts[0].Trim().ToLowerInvariant() -eq "autopause") {
            $updated.Add("autoPause = 0")
            $autoPauseSeen = $true
            continue
        }
    }
    $updated.Add($rawLine)
}

if ($section -eq "game" -and -not $autoPauseSeen) {
    $updated.Add("autoPause = 0")
    $autoPauseSeen = $true
}
if (-not $gameSectionSeen) {
    if ($updated.Count -ne 0 -and $updated[$updated.Count - 1] -ne "") {
        $updated.Add("")
    }
    $updated.Add("[game]")
    $updated.Add("autoPause = 0")
}

$backup = $null
if (Test-Path -LiteralPath $path) {
    $backupName = "III.VC.SA.WindowedMode.{0}.ini" -f (
        Get-Date -Format "yyyyMMdd_HHmmss"
    )
    $backup = Join-Path (Join-Path $Root "backups") $backupName
    Copy-Item -LiteralPath $path -Destination $backup -Force
}

$temporary = "$path.tmp.$PID"
[IO.File]::WriteAllLines($temporary, $updated, $encoding)
Move-Item -LiteralPath $temporary -Destination $path -Force
$after = Get-SampLabAutoPauseState -GameDir $gameDir
if ($after.disabled -ne $true) {
    throw "Failed to enforce [game] autoPause = 0 in $path"
}

[pscustomobject]@{
    path = $path
    backup = $backup
    before = $before
    after = $after
} | ConvertTo-Json -Depth 5
