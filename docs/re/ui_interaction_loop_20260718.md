# T/chat and scoreboard interaction loop — 2026-07-18

## Scope

Automated original-R5 versus replacement checks for T chat, TAB scoreboard,
mouse/input ownership, movement, camera, HUD/radar, chat RPC and scoreboard
RPC23 groundwork.

Official references:

- https://open.mp/docs/scripting/callbacks/OnPlayerText
- https://open.mp/docs/scripting/callbacks/OnPlayerClickPlayer
- https://open.mp/docs/scripting/functions/TogglePlayerControllable

## Instrument

`tools/reloop_control` builds one identical 32-bit ASI for both prefixes. It
binds only `127.0.0.1:18737`, requires a local test token and accepts a small
newline-JSON command set. It never writes game memory. Samples include player
position, camera aim/modes, HUD/radar, cursor/window/key state, and the five
bytes at `gta_sa.exe+0x00141df5`.

The host sends normal Win32 input/window events. The bare gamemode logs the
real `OnPlayerText` and `OnPlayerClickPlayer` callbacks.

## Repeated replacement result

PROBE_TRACE runs:

- `20260718-225005-replacement-pvars-457528`
- `20260718-225354-replacement-pvars-459641`
- `20260718-225648-replacement-pvars-461465`

All three produced `PASS_RPC23_UNVERIFIED`:

- T changes `e8 46 f3 fe ff` to `90 90 90 90 90`.
- With T active, W is down but player and camera deltas are exactly `0.0`.
- Enter reaches `OnPlayerText` and restores the original five bytes.
- TAB enables the replacement mouse-mode/HUD-hide paths and uses the same
  five-byte input-disable patch.
- With TAB active, W is down but player and camera deltas are exactly `0.0`.
- TAB release restores `e8 46 f3 fe ff`.
- No `exception_filter` occurs in these three replacement runs.

## Original comparison

OBSERVED_037 + PROBE_TRACE in the three paired original runs:

- T uses the same NOP patch and blocks movement/camera.
- Default chat reaches `OnPlayerText`; returning `1` preserves the stock
  player-coloured name followed by white message text.
- TAB alone does not patch `gta_sa.exe+0x00141df5`. Holding W while TAB is down
  moves the player roughly 3.08 units in every run and the camera follows.
- Original HUD/radar writes are frame-timed, so an asynchronous sample can see
  either side of a draw/restore write.

The replacement matches the original T opcode path. Its TAB freeze implements
the explicitly requested shared mouse-mode behavior, while exact original TAB
opcode parity cannot be claimed from these observations.

## RPC23 status

Single-player self-click scans do not invoke `OnPlayerClickPlayer`. Optional
`--companion` mode successfully connects a real `ReLoopPeer`, but the second
Wine window steals effective GUI focus from the primary under Wayland. That run
is excluded from freeze/camera evidence. RPC23 remains `TODO_VERIFY` until
primary-window focus is deterministic or the peer is non-GUI.

## Crash policy

One calibration replacement launch exited pre-connect. The immediate identical
retry and the later three evidence runs passed. It is not a reproducible crash
under the required three-attempt policy.
