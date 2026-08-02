param(
    [string]$Root = "C:\samp-test",
    [ValidateSet("key", "click")][string]$Mode = "key",
    [ValidateSet("ENTER", "ESCAPE", "SPACE", "ALTENTER", "TAB", "F6", "F7", "UP", "DOWN", "LEFT", "RIGHT", "FIRE", "GAS", "GASFIRE", "PASSENGER", "STEERLEFT", "STEERRIGHT", "BRAKE", "HANDBRAKE", "HORN", "MODE", "CLASS", "KILL", "QUIT", "MENUTEST", "TPASSWORD", "TPASSWORDVALUE", "SFA", "LVA", "AA", "ACTORS", "ACTORSOFF", "RPC175EDGE", "RPC175EDGEOFF", "RPC175RAW", "RPC176RAW", "RPC178EDGE", "RPC178EDGEOFF", "RPCLEGACYRAW", "RPCLEGACYDRUNKON", "RPCLEGACYDRUNKOFF", "SYNCFOOT", "SYNCCAR", "SYNCRUSTLER", "SYNCSTOP")][string]$Key = "ENTER",
    [int]$X = 0,
    [int]$Y = 0,
    [string]$Label = "input"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Common.ps1")

$gta = @(Get-Process -Name "gta_sa" -ErrorAction SilentlyContinue)
$browser = @()
if ($gta.Count -eq 1 -and $gta[0].MainWindowHandle -ne 0) {
    $process = $gta[0]
} elseif (
    ($Mode -eq "key" -and $Key -in @("ENTER", "UP", "DOWN")) -or
    $Mode -eq "click"
) {
    # A manually registered browser run is the recovery path when the normal
    # favorite-selection automation cannot launch GTA. Keep that exception
    # deliberately narrow: list navigation plus clicks on the browser itself
    # may target samp.exe; gameplay keys still require exactly one GTA window.
    $browser = @(Get-Process -Name "samp" -ErrorAction SilentlyContinue)
    if ($browser.Count -ne 1 -or $browser[0].MainWindowHandle -eq 0) {
        throw "Exactly one interactive gta_sa.exe window, or one samp.exe browser for navigation, is required."
    }
    $process = $browser[0]
} else {
    throw "Exactly one interactive gta_sa.exe window is required."
}
if (-not ("SampTestWindowInput" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SampTestWindowInput {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
}
"@
}
if (-not ("SampTestKeyboardInput" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SampTestKeyboardInput {
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte virtualKey, byte scanCode, uint flags, UIntPtr extraInfo);
}
"@
}
$windowHandle = [SampTestWindowInput]::GetForegroundWindow()
[uint32]$foregroundProcessId = 0
[SampTestWindowInput]::GetWindowThreadProcessId($windowHandle, [ref]$foregroundProcessId) | Out-Null
if ($foregroundProcessId -ne $process.Id) {
    $shell = New-Object -ComObject WScript.Shell
    if (-not $shell.AppActivate($process.Id)) {
        throw "Could not activate the GTA test window."
    }
    Start-Sleep -Milliseconds 200
    $windowHandle = [SampTestWindowInput]::GetForegroundWindow()
    $foregroundProcessId = 0
    [SampTestWindowInput]::GetWindowThreadProcessId($windowHandle, [ref]$foregroundProcessId) | Out-Null
    if ($foregroundProcessId -ne $process.Id) {
        throw "GTA did not become the foreground window."
    }
}

if ($Mode -eq "key") {
    if ($Key -eq "FIRE") {
        [SampTestWindowInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds 750
        } finally {
            [SampTestWindowInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        }
    } elseif ($Key -eq "GAS") {
        [SampTestKeyboardInput]::keybd_event(0x57, 0, 0, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds 750
        } finally {
            [SampTestKeyboardInput]::keybd_event(0x57, 0, 0x0002, [UIntPtr]::Zero)
        }
    } elseif ($Key -eq "GASFIRE") {
        [SampTestKeyboardInput]::keybd_event(0x57, 0, 0, [UIntPtr]::Zero)
        [SampTestWindowInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds 750
        } finally {
            [SampTestWindowInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
            [SampTestKeyboardInput]::keybd_event(0x57, 0, 0x0002, [UIntPtr]::Zero)
        }
    } elseif ($Key -in @("PASSENGER", "STEERLEFT", "STEERRIGHT", "BRAKE", "HANDBRAKE", "HORN")) {
        [byte]$virtualKey = switch ($Key) {
            "PASSENGER" { 0x47 }
            "STEERLEFT" { 0x41 }
            "STEERRIGHT" { 0x44 }
            "BRAKE" { 0x53 }
            "HANDBRAKE" { 0x20 }
            "HORN" { 0x48 }
        }
        [SampTestKeyboardInput]::keybd_event($virtualKey, 0, 0, [UIntPtr]::Zero)
        try {
            # STATIC_037:
            # CLocalPlayer::Process consumes the passenger control on the
            # first pressed frame. Keep G down across several DirectInput
            # samples without turning the test into a long held-key repeat.
            Start-Sleep -Milliseconds $(if ($Key -eq "PASSENGER") { 100 } else { 750 })
        } finally {
            [SampTestKeyboardInput]::keybd_event($virtualKey, 0, 0x0002, [UIntPtr]::Zero)
        }
    } elseif ($Key -eq "ALTENTER") {
        # Fixed fullscreen/windowed transition probe.  Use real modifier state
        # rather than a SendKeys chord so gta_sa.exe receives WM_SYSKEYUP for
        # VK_RETURN, which is the R5-compatible replacement's guarded path.
        [SampTestKeyboardInput]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds 50
            [SampTestKeyboardInput]::keybd_event(0x0D, 0, 0, [UIntPtr]::Zero)
            try {
                Start-Sleep -Milliseconds 100
            } finally {
                [SampTestKeyboardInput]::keybd_event(0x0D, 0, 0x0002, [UIntPtr]::Zero)
            }
            Start-Sleep -Milliseconds 50
        } finally {
            [SampTestKeyboardInput]::keybd_event(0x12, 0, 0x0002, [UIntPtr]::Zero)
        }
    } elseif ($Key -in @("TAB", "F6", "F7")) {
        # STATIC_037 + TODO_VERIFY:
        # The focused R5 UI-latch probe observes the scoreboard, chat-open,
        # chat-display-cycle and cursor transition callees. Emit a real,
        # bounded key-down/key-up pair so DirectInput and WndProc both see the
        # same edge. TAB remains held long enough for a concurrent screenshot
        # burst to catch the visible scoreboard.
        [byte]$virtualKey = switch ($Key) {
            "TAB" { 0x09 }
            "F6" { 0x75 }
            "F7" { 0x76 }
        }
        [byte]$scanCode = switch ($Key) {
            "TAB" { 0x0F }
            "F6" { 0x40 }
            "F7" { 0x41 }
        }
        [SampTestKeyboardInput]::keybd_event($virtualKey, $scanCode, 0, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds $(if ($Key -eq "TAB") { 750 } else { 100 })
        } finally {
            [SampTestKeyboardInput]::keybd_event($virtualKey, $scanCode, 0x0002, [UIntPtr]::Zero)
        }
    } elseif ($Key -in @("SPACE", "UP", "DOWN", "LEFT", "RIGHT")) {
        # PROBE_TRACE:
        # WScript.SendKeys emits gameplay/menu keys too briefly for every
        # DirectInput frame on the native Windows host. Hold the fixed
        # navigation/accept allowlist across several 60 Hz frames so a missed
        # sampler edge cannot masquerade as a client latch defect.
        [byte]$virtualKey = switch ($Key) {
            "SPACE" { 0x20 }
            "UP" { 0x26 }
            "DOWN" { 0x28 }
            "LEFT" { 0x25 }
            "RIGHT" { 0x27 }
        }
        [byte]$scanCode = switch ($Key) {
            "SPACE" { 0x39 }
            "UP" { 0x48 }
            "DOWN" { 0x50 }
            "LEFT" { 0x4B }
            "RIGHT" { 0x4D }
        }
        [uint32]$keyFlags = if ($Key -eq "SPACE") { 0 } else { 0x0001 }
        [SampTestKeyboardInput]::keybd_event($virtualKey, $scanCode, $keyFlags, [UIntPtr]::Zero)
        try {
            Start-Sleep -Milliseconds 100
        } finally {
            [SampTestKeyboardInput]::keybd_event($virtualKey, $scanCode, ($keyFlags -bor 0x0002), [UIntPtr]::Zero)
        }
    } else {
    $sendKey = switch ($Key) {
        "ENTER" { "{ENTER}" }
        "ESCAPE" { "{ESC}" }
        "SPACE" { " " }
        "UP" { "{UP}" }
        "DOWN" { "{DOWN}" }
        "LEFT" { "{LEFT}" }
        "RIGHT" { "{RIGHT}" }
        # Fixed UFW test action; intentionally not a general text-input mode.
        "MODE" { "{F6}/modo{ENTER}" }
        # Split F4 and /kill into separate observable actions.  A combined
        # SendKeys burst made it impossible to tell whether the legacy class
        # latch, chat activation, or the spawn request caused a sync failure.
        "CLASS" { "{F4}" }
        "KILL" { "{F6}/kill{ENTER}" }
        "QUIT" { "{F6}/q{ENTER}" }
        # Fixed stock-SA-MP CreateMenu parity fixture.
        "MENUTEST" { "{F6}/menutest{ENTER}" }
        # Fixed password-dialog parity fixture. Arbitrary text is deliberately
        # still excluded from the remote command queue.
        "TPASSWORD" { "{F6}/tpassword{ENTER}" }
        # Fixed known value for the active password fixture. Submission remains
        # a separate ENTER action so a screenshot can prove visual masking
        # before the server trace asserts the unchanged RPC62 bytes.
        "TPASSWORDVALUE" { "p4rity42" }
        # Fixed teleport actions used to stress the large object/model RPC
        # bursts on the SuperFreeroam compatibility route.
        "SFA" { "{F6}/sfa{ENTER}" }
        "LVA" { "{F6}/lva{ENTER}" }
        "AA" { "{F6}/aa{ENTER}" }
        # Fixed local bare-server Actor parity actions. Keep arbitrary command
        # injection out of the remote queue while allowing a deterministic
        # original/replacement Actor lifecycle run.
        "ACTORS" { "{F6}/rpcactors{ENTER}" }
        "ACTORSOFF" { "{F6}/rpcactorsoff{ENTER}" }
        "RPC175EDGE" { "{F6}/rpc175edge{ENTER}" }
        "RPC175EDGEOFF" { "{F6}/rpc175edgeoff{ENTER}" }
        "RPC175RAW" { "{F6}/rpc175raw{ENTER}" }
        "RPC176RAW" { "{F6}/rpc176raw{ENTER}" }
        "RPC178EDGE" { "{F6}/rpc178edge{ENTER}" }
        "RPC178EDGEOFF" { "{F6}/rpc178edgeoff{ENTER}" }
        "RPCLEGACYRAW" { "{F6}/rpclegacyraw{ENTER}" }
        "RPCLEGACYDRUNKON" { "{F6}/rpclegacydrunkon{ENTER}" }
        "RPCLEGACYDRUNKOFF" { "{F6}/rpclegacydrunkoff{ENTER}" }
        "SYNCFOOT" { "{F6}/syncpair onfoot{ENTER}" }
        "SYNCCAR" { "{F6}/syncpair car{ENTER}" }
        "SYNCRUSTLER" { "{F6}/syncpair rustler{ENTER}" }
        "SYNCSTOP" { "{F6}/syncpair stop{ENTER}" }
    }
    $shell = New-Object -ComObject WScript.Shell
    $shell.SendKeys($sendKey)
    if ($Key -eq "MODE") {
        # UFW answers /modo with a list dialog.  Confirm its preselected
        # FreeRoam row promptly so the test reaches the TextDraw mode selector
        # before the server's dialog/sync timeout closes this connection.
        Start-Sleep -Milliseconds 1000
        $shell.SendKeys("{ENTER}")
    }
    }
} else {
    $rect = New-Object SampTestWindowInput+RECT
    if (-not [SampTestWindowInput]::GetWindowRect($windowHandle, [ref]$rect)) {
        throw "Could not read the GTA window bounds."
    }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($X -lt 0 -or $Y -lt 0 -or $X -ge $width -or $Y -ge $height) {
        throw "Relative click coordinate is outside the GTA window: $X,$Y in $($width)x$height."
    }
    [SampTestWindowInput]::SetCursorPos($rect.Left + $X, $rect.Top + $Y) | Out-Null
    [SampTestWindowInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    # GTA/SA-MP polls the DirectInput mouse state once per frame.  Back-to-back
    # mouse_event calls can collapse into a transition that is visible as hover
    # movement but never sampled as a held button on native Windows.
    Start-Sleep -Milliseconds 100
    [SampTestWindowInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
}

Start-Sleep -Milliseconds 750
$screenshot = & (Join-Path $PSScriptRoot "Capture-Screenshot.ps1") -Root $Root -Label $Label
[pscustomobject]@{
    action = "input"
    mode = $Mode
    key = if ($Mode -eq "key") { $Key } else { $null }
    relative_x = if ($Mode -eq "click") { $X } else { $null }
    relative_y = if ($Mode -eq "click") { $Y } else { $null }
    process_id = $process.Id
    screenshot = $screenshot
}
