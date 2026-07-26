param(
    [string]$Root = "C:\samp-test",
    [string]$Label = "burst",
    [ValidateRange(1, 120)][int]$Count = 60,
    [ValidateRange(25, 10000)][int]$IntervalMilliseconds = 50,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Common.ps1")

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$safeLabel = ConvertTo-SampLabName -Value $Label
New-SampLabDirectory -Path $OutputDirectory

$bounds = [Windows.Forms.SystemInformation]::VirtualScreen
if ($bounds.Width -le 0 -or $bounds.Height -le 0) {
    throw "The interactive session has no capturable virtual screen."
}

$frames = [System.Collections.Generic.List[object]]::new()
$startedUtc = (Get-Date).ToUniversalTime()
$clock = [Diagnostics.Stopwatch]::StartNew()
$nextCaptureMilliseconds = 0.0
$bitmap = New-Object Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [Drawing.Graphics]::FromImage($bitmap)
try {
    for ($index = 1; $index -le $Count; $index++) {
        $remainingMilliseconds = $nextCaptureMilliseconds - $clock.Elapsed.TotalMilliseconds
        if ($remainingMilliseconds -gt 0.0) {
            Start-Sleep -Milliseconds ([int][Math]::Ceiling($remainingMilliseconds))
        }

        $captureStartedMilliseconds = $clock.Elapsed.TotalMilliseconds
        $capturedUtc = (Get-Date).ToUniversalTime()
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
        $name = "{0}_{1}_{2:D3}.png" -f $timestamp, $safeLabel, $index
        $path = Join-Path $OutputDirectory $name

        $graphics.CopyFromScreen($bounds.Location, [Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($path, [Drawing.Imaging.ImageFormat]::Png)

        $captureFinishedMilliseconds = $clock.Elapsed.TotalMilliseconds
        $frames.Add([pscustomobject]@{
            index = $index
            captured_utc = $capturedUtc.ToString("o")
            capture_started_ms = [Math]::Round($captureStartedMilliseconds, 3)
            capture_finished_ms = [Math]::Round($captureFinishedMilliseconds, 3)
            path = $path
        })
        # Enforce the requested minimum between capture starts. If PNG encoding
        # itself takes longer, the next frame starts immediately after it and
        # the measured interval remains greater than the requested interval.
        $nextCaptureMilliseconds = $captureStartedMilliseconds + $IntervalMilliseconds
    }
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
    $clock.Stop()
}

$finishedUtc = (Get-Date).ToUniversalTime()
foreach ($frame in $frames) {
    $frame | Add-Member -NotePropertyName sha256 -NotePropertyValue (
        Get-SampLabHash -Path ([string]$frame.path)
    )
}

$manifestPath = Join-Path $OutputDirectory "manifest.json"
$manifest = [ordered]@{
    schema = 1
    label = $safeLabel
    requested_count = $Count
    requested_interval_ms = $IntervalMilliseconds
    started_utc = $startedUtc.ToString("o")
    finished_utc = $finishedUtc.ToString("o")
    elapsed_ms = [Math]::Round(($finishedUtc - $startedUtc).TotalMilliseconds, 3)
    virtual_screen = [ordered]@{
        x = $bounds.X
        y = $bounds.Y
        width = $bounds.Width
        height = $bounds.Height
    }
    frames = @($frames)
}
Write-SampLabJson -Value $manifest -Path $manifestPath

[pscustomobject]@{
    manifest = $manifestPath
    output_directory = $OutputDirectory
    count = $frames.Count
    requested_interval_ms = $IntervalMilliseconds
    frames = @($frames)
}
