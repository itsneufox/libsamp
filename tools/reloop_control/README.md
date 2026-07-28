# ReLoop control ASI

`reloop_control.asi` is a test-only input and telemetry bridge shared by the
original and replacement prefixes. It binds TCP only to `127.0.0.1:18737` and
accepts newline-delimited JSON carrying the fixed token `reloop-local-v1`.

The API exposes `ping`, `state`, `focus`, `key`, `window_key`,
`window_syskey`, `char`, `mouse`, and the narrowly guarded
`samp_screenshot` test command. `window_syskey` emits the matching
`WM_SYSKEYDOWN`/`WM_SYSKEYUP` pair and is used to exercise the original R5
Alt+Enter release-trigger without depending on the host compositor. `state`
samples the GTA HUD/radar/camera globals and the five bytes at
`gta_sa.exe+0x141df5`; it never writes game memory. Input commands are normal
Win32 window/input events so both DLLs receive the same stimulus.

The `mouse` action `move_delta` uses a bounded relative `SendInput` event
instead of moving the desktop cursor to an absolute point. `state` exposes the
three floats of GTA's `CCamera::InternalAim` front vector at
`gta_sa.exe+0x76F32C` as `aim_front_*`, plus the local ped matrix-forward vector
as `player_forward_*`. The older `aim_*` fields remain the InternalAim camera
position at `gta_sa.exe+0x76F338` for API compatibility. The angle fixture uses
the new vectors only as readback: it does not write GTA or SA-MP memory.

`samp_screenshot` exists only to capture an unattended Original-R5 observer
under Wayland, where GNOME can deny whole-desktop screenshots and a synthetic
F8 edge can be lost during focus handoff. It requires the R5 preferred PE
ImageBase, timestamp, entry RVA, image size, and exact relocation-normalized
code guards at `samp.dll+0x755C0/+0x75751`; the actual module may be relocated
by Wine/ASLR. Only then does it atomically set the original request flag at
`samp.dll+0x12DE64`; R5's own render callback consumes the flag on the next
frame. The command rejects every other DLL identity.
Evidence: `STATIC_037`, original DLL
SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.

Build with `build_win32.sh`, deploy the resulting ASI into both GTA roots, then
run `python3 tools/reloop/control_client.py scenario --output <file>` while the
client is connected. This deliberately uses a tiny dependency-free loopback
protocol instead of WebSocket framing; it is easier to make deterministic on
Wine and can be wrapped by WebSocket later without changing the command model.
