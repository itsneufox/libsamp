# Original-R5 AFK, pause, TAB, chat, and cursor memory probe

Date: 2026-07-28

Status: `STATIC_037`; runtime behavior and every field interpretation not
called out as a direct instruction effect remain `TODO_VERIFY`.

## Scope

This profile is a passive evidence collector for the original 0.3.7-R5
client. It is intended to answer:

- which calls actually open and close the TAB scoreboard;
- whether chat input and the F7 display mode are momentary or latched;
- how R5's cursor/input mode and delayed restore counter change;
- which focus/menu transitions coincide with those changes;
- when a remote player changes between active and AFK display state.

It does not inject keys, move the cursor, call `ShowCursor`, alter a timer, or
write a log from a hooked thread. The original function always runs through a
trampoline. Hook records go to a fixed ring and the existing worker writes
them later.

The WndProc at `samp.dll+0x61650` is deliberately not hooked. Its large switch
and many early `ret 0x10` exits are a wider compatibility surface than needed.
The smaller state-transition callees preserve caller RVAs, including WndProc
call sites, while keeping the patch set reviewable.

## Binary identities

Original R5:

- file: `artifacts/binaries/samp_installer.dll`;
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- preferred base: `0x10000000`;
- PE timestamp: `0x6372C39E`;
- entry RVA: `0x000CBC90`;
- image size: `0x0027E000`.

GTA San Andreas 1.0 US:

- file: `GTA San Andreas RZ/gta_sa.exe`;
- SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`;
- preferred base: `0x00400000`;
- PE timestamp: `0x427101CA`;
- entry RVA: `0x00424570`;
- image size: `0x01177000`;
- PE checksum: `0x00DC5BEA`.

The code accepts only these PE identity proxies, including machine,
preferred-image-base header, and relocation-table characteristics. GTA must
remain at its fixed preferred base and have relocations stripped. R5 must
retain a non-empty relocation directory but may be loader-relocated: absolute
SA-MP operands covered by the PE relocation table are normalized from
preferred-image VAs to the actual module base before comparison. RVAs,
opcodes, non-relocated bytes, and the GTA absolute operand remain exact.
Hashes above document the analyzed inputs; the probe does not hash files from
inside the game process.

## Static R5 findings

### TAB scoreboard

`STATIC_037`:

- `samp.dll+0x6F3D0` shows the scoreboard. It tests the DWORD at
  `this+0x0`, makes the GUI object at `this+0x34` visible, calls
  `CGame::SetCursorMode` with mode `3`, and writes `1` to `this+0x0`.
- `samp.dll+0x6E9E0` hides it. It clears the GUI-visible byte, optionally
  calls `CGame::SetCursorMode` with mode `0`, then writes `0` to
  `this+0x0`. Its one stack argument is preserved as a raw value.
- The global scoreboard pointer is `samp.dll+0x26EB4C`.
- The WndProc TAB path first requires `uMsg == WM_KEYUP` (`0x101`) at
  `samp.dll+0x61785` and `wParam == VK_TAB` (`0x09`) at `+0x6178D`.
  It reads the visible DWORD at `CScoreboard+0x0`: a nonzero value calls
  hide at `+0x617A0`, while zero calls show at `+0x617B6` when
  `CGame+0x24` is zero. Consequently, one completed TAB pulse toggles exactly
  one edge; observing show followed by hide requires two key-up pulses.
- WndProc also calls hide at
  `samp.dll+0x61B82` for `WM_KILLFOCUS`. These caller RVAs let a runtime trace
  distinguish the edges without hooking WndProc.

The show/hide names are based on the direct visible-state writes. The plain TAB
path is statically assigned to `WM_KEYUP`; right-button interaction and focus
cleanup remain separately identified by their caller RVAs.

### Chat input and F7 display mode

`STATIC_037`:

- the chat object pointer is `samp.dll+0x26EB84`;
- `samp.dll+0x69480` opens input and changes `this+0x14E0` to `1`;
- `samp.dll+0x69580` closes input and changes `this+0x14E0` to `0`;
- the chat-display object pointer is `samp.dll+0x26EB80`;
- `samp.dll+0x612C0` cycles the DWORD at `this+0x8` as
  `0 -> 2`, `1 -> 0`, and `2 -> 1`;
- that routine writes `1` to the raw dirty field at `this+0x63DA`.

The key helper at `samp.dll+0x61360` calls these routines for F6/F7. It is not
hooked because the state-transition callees also capture focus cleanup and
non-keyboard call paths.

### Cursor/input ownership

`STATIC_037`:

- `samp.dll+0xA06F0` is a `thiscall` function with two stack arguments and
  `ret 8`;
- it handles raw modes `0..4` and stores the selected mode at
  `CGame+0x61`;
- its mode-zero path derives a raw delayed-restore value at `CGame+0x65`;
- `samp.dll+0xA05D0` reads both fields. While the raw restore value is
  positive it decrements it. At zero it restores the GTA input-gate code and
  related mouse gate.

The probe therefore logs these as `cursor_mode_raw` and
`cursor_restore_raw`. The second value is a statically confirmed countdown,
not a proven general cursor reference count.

The following GTA bytes are read alongside each emitted UI record:

- `0x00541DF5..0x00541DF9`: GTA input-gate call bytes which R5 replaces with
  NOPs in cursor modes;
- `0x006194A0`: raw mouse-gate byte toggled by R5.

They are observations only. The probe never writes either address.

### Pause/frontend state

`STATIC_037`:

- `CGame::IsMenuActive` is `samp.dll+0xA0920`;
- it reads the DWORD at GTA address `0x00BA67A4` and returns whether it is
  non-zero;
- R5 render and WndProc paths use that result as a UI gate.

The hook publishes the first query and later result edges only. It also logs
the raw DWORD and its first three bytes.

The byte at `0x00B7CB49` is included only as
`pause_raw_b7cb49`. The existing anti-pause reference comes from the legacy
0.2x/GTA-side path, not a proven R5 xref. Its semantic label remains
`TODO_VERIFY`.

Read-only Win32 observations include `GetForegroundWindow`, `GetFocus`,
`GetCapture`, and `GetCursorInfo.flags`. These are tagged `WIN32_API` and are
not R5 object fields.

### Remote AFK state

`STATIC_037`:

- `CRemotePlayer::Process` is `samp.dll+0x166B0`;
- the sync-state byte is at `CRemotePlayer+0x10A`;
- the last-sync tick is at `CRemotePlayer+0x1B9`;
- the AFK/display state DWORD is at `CRemotePlayer+0x1C5`;
- the remote ped wrapper is at `CRemotePlayer+0x1DD`;
- elapsed time is calculated as `GetTickCount() - last_sync_tick`.

The guarded transition blocks establish:

- on-foot at `+0x16DA0`: state `2` after 3000 ms for an all-zero movement
  vector, otherwise after 1500 ms;
- driver at `+0x16FE2`: the same 3000/1500 ms split;
- passenger at `+0x1704E`: state `2` after 3000 ms;
- common clear at `+0x170D6`: state `2` returns to `0` when elapsed is below
  1500 ms.

The public-facing meaning “AFK glyph” is corroborated by the existing R5
nametag audit, but this profile still records the field numerically. Runtime
must establish exact ordering relative to sync receive and rendering.

## Hook set and guards

All nine hooks must pass before the first target is modified:

| RVA | Static role | Copied entry | Additional guards |
| --- | --- | ---: | --- |
| `+0x612C0` | chat display-mode cycle | 5 bytes | complete remaining body and all returns |
| `+0x69480` | chat open | 6 bytes | final active-state write and epilogue |
| `+0x69580` | chat close | 9 bytes | cursor call, active-state clear, epilogue |
| `+0x6E9E0` | scoreboard hide | 6 bytes | argument branch, cursor call, `ret 4` |
| `+0x6F3D0` | scoreboard show | 6 bytes | cursor call, visible-state write, return |
| `+0xA05D0` | delayed input restore | 7 bytes | both decrement/return forms |
| `+0xA06F0` | cursor mode | 6 bytes | mode `0..4` return forms, all `ret 8` |
| `+0xA0920` | menu query | 6 bytes | boolean conversion and return |
| `+0x166B0` | remote Process/AFK | 6 bytes | AFK blocks and both function tails |

Each entry span contains whole instructions and no relative branch or call.
The three guarded SA-MP globals at relocation RVAs `+0x695AF`, `+0x6EA11`,
and `+0x6F408` are compared against the actual R5 module base. The menu-query
entry embeds GTA's absolute address and is not an R5 relocation, so the fixed
GTA-base check is still required.

Installation is all-or-nothing. A failed partial install is rolled back in
reverse order. Shutdown restores a target only if its current bytes are the
exact `E9` plus NOP patch owned by this profile. Trampoline memory remains
process-lifetime storage so an in-flight wrapper cannot jump into freed code.

## Bounded capture

Hooked threads allocate no heap memory and perform no file I/O. Records are
published to a fixed 256-entry ring. The worker flushes:

- `ui_latches_r5`: event, reason bits, tick, GTA frame, thread, caller and
  hook RVA, arguments, raw transition values, and remote AFK timing;
- `ui_latch_state_r5`: scoreboard/chat/game pointers and raw fields,
  frontend/pause/input-gate bytes, and read-only Win32 focus/cursor state.

TAB, chat, and cursor-mode calls get pre/post snapshots. Delayed-restore
records are emitted only when a raw counter or input-gate byte changes. Their
changed pre-state fields are retained from the lightweight reads taken before
the original call; unchanged UI/Win32 context is copied from the single post
snapshot so the per-frame no-change path does not perform duplicate queries.
Menu-query records are baseline/edge-only.

Remote players use a fixed 128-slot tracker. A record is emitted for the first
observation, an AFK/sync-state edge, or a one-second heartbeat. If more than
128 distinct remote objects appear in one process, the worker logs
`remote_tracker_overflow`; heartbeat tracking is suppressed for additional
objects, while direct before/after state changes can still be recorded.

Reason bits:

- `0x01`: direct transition-call record;
- `0x02`: first baseline;
- `0x04`: AFK/menu/sync state edge;
- `0x08`: one-second remote heartbeat;
- `0x10`: delayed input-gate edge.

## Enablement

Environment:

```text
SAMP_PROBE_UI_LATCHES_HOOKS=1
```

Flag next to `samp_probe.asi`:

```text
samp_probe_ui_latches_hooks.flag
```

Managed Windows profile:

```bash
tools/windows/remote_lab/samp_lab.sh probe-profile ui-latches-r5
```

The focused profile skips the probe's normal Winsock/IAT, render, trailer, and
unrelated code-hook sets.

Prepared bounded runner path:

```bash
python3 tools/reloop/distributed_sync_runner.py \
  --scenario ui_latches \
  --windows-role pilot \
  --windows-probe-profile ui-latches-r5
```

The path requires Original R5 on Windows and sends only the allowlisted
sequence TAB, TAB, F6, F6, F7, F7, F7. Each TAB pulse is held for 750 ms and
therefore contributes one `WM_KEYUP` toggle; the function keys receive 100 ms
down/up edges. It does not automate ESC, the GTA pause menu, focus loss, or
arbitrary input. A successful runner verdict proves only that the expected
probe calls were recorded without ring overflow; screenshots and exact state
transitions still require review.

## Original-client runtime matrix

`OBSERVED_037 + PROBE_TRACE`:

- run `20260728_150323_dist_sync_ui_latches_pilot_1eeb41f8`, Original R5
  SHA-256
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`,
  recorded one `scoreboard_show` from caller `samp.dll+0x617BB` after one
  complete TAB pulse and no hide edge;
- the final screenshot retained the visible scoreboard, corroborating the
  recorded `scoreboard_visible=1` state;
- chat open/close, three F7 mode edges, all nine hook installations, and no
  ring overflow were recorded. The stored failure verdict was therefore a
  test-plan error rather than an observed original-client latch defect.

A controlled original R5 run should additionally cover, in order:

1. connect and idle for at least five seconds with another streamed player;
2. press and release TAB twice, then repeat with right-button interaction;
3. hold TAB, lose focus, regain focus while TAB is still held, then release;
4. open and close chat with F6 and with the normal chat key;
5. press F7 three times and confirm the raw `0 -> 2 -> 1 -> 0` cycle from the
   actual starting state;
6. open and close the GTA pause menu while observing menu-query edges;
7. stop and resume sync from the second player to cross 1500 and 3000 ms;
8. repeat the AFK transition while on foot, driving, and riding as passenger;
9. quit cleanly and verify nine owned hooks were restored.

Record the exact DLL/GTA hashes, server, gamemode, client role, key sequence,
and latest `process_attach` block. Only after this run may the resulting lines
be tagged `OBSERVED_037` / `PROBE_TRACE`.

## Open points

- `TODO_VERIFY`: whether the statically established plain-TAB `WM_KEYUP`
  toggle is suppressed by any additional frontend/focus state beyond the
  already observed guards.
- `TODO_VERIFY`: exact caller-to-reason mapping for right-button scoreboard
  interaction.
- `TODO_VERIFY`: whether `CGame+0x65` has any role beyond the statically seen
  delayed input restore.
- `TODO_VERIFY`: semantic meaning of `0x00B7CB49` in the R5 process.
- `TODO_VERIFY`: whether `CRemotePlayer::Process` ever runs outside the main
  game thread.
- `TODO_VERIFY`: the exact render frame in which AFK state `2` becomes a
  visible nametag glyph.
