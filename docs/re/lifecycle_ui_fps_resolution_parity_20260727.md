# Lifecycle, UI, FPS, resolution, and AFK parity (2026-07-27)

## Scope and binaries

This note records the focused parity pass for startup/quit/GMX cleanup,
CreateMenu, TextDraws, `/fpslimit`, resolution handling, and background/AFK
input.

- Original SA-MP 0.3.7-R5 `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- GTA SA 1.0 US SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`.
- Replacement under test after the three-callback startup gate:
  `build-win32/samp.dll` SHA256
  `b3d64cd26b3d5b9f7f44104df88d86007ad92dedbffb7571b8a9d133271bc046`.

Evidence labels below follow the repository `AGENTS.md`.

## Startup and GTA-thread ownership

### Reproduced failure

`PROBE_TRACE`:

- `20260726-234235-replacement-ui-298546`
- `20260726-234249-replacement-ui-298546`
- `20260726-234302-replacement-ui-298546`

All three one-second pre-connect runs failed before any graphics callback
(`callbacks=0`). Faults were observed at GTA `0x5380AF` and `0x7F39FB`.
`0x5380AF` belongs to `CFileLoader::LoadObjectInstance`, while `0x7F39FB`
belongs to `RwTexDictionaryFindNamedTexture`.

`STATIC_037`:

- Original R5 installs its main processing callback at the GTA call site
  `0x53EB13`.
- The R5 callback is `samp.dll+0xC4FF0`, which calls the main processing
  routine at `samp.dll+0xC4F70` on the GTA render/game thread.
- Legacy 0.2x follows the same architecture: the launch monitor performs the
  finite startup handoff, while ongoing game processing runs from the graphics
  loop.

This makes thread ownership the synchronization primitive. Clothes descriptor
comparison and a momentarily idle streaming channel are useful diagnostics,
but are not sufficient readiness predicates:

- the semantic snapshot reached `safe=1 stable=3/3` at GTA frames 3-5;
- normal streaming only became active later, around frame 17;
- one-callback scene loads remained nondeterministic and could hang inside
  `LoadScene`.

The replacement now requires:

1. the byte-validated graphics callback to capture the GTA thread ID;
2. three graphics callbacks on that same thread;
3. only then may the retained `04E4` refresh and script camera operations
   execute.

The monitor path only advances the GTA frontend and records pending work. It
does not fall back to unsafe scene/camera calls if the callback is absent.

The earlier three-callback experiment did allow direct
`LoadSceneCollision`/`LoadScene` calls and produced successful controls, but
later stress runs proved that the same state can still block indefinitely
inside either routine:

- pre-connect hangs:
  `20260727-165414-replacement-ui-680318`,
  `20260727-165627-replacement-ui-680318`, and
  `20260727-170425-replacement-labels-688825`;
- post-Join spawn hang:
  `20260727-170626-replacement-labels-688825`;
- successful controls:
  `20260727-165838-replacement-ui-680318` and
  `20260727-170837-replacement-labels-688825`.

`STATIC_037` revalidation of the original R5 DLL found no reference to GTA
`CStreaming::LoadSceneCollision` (`0x40ED80`) and no reference to
`CStreaming::LoadScene` (`0x40EB70`). It found one reference to
`LoadAllRequestedModels` (`0x40EA10`) at `samp.dll+0xA0A6A`, inside the
specific request/load-model helper. The replacement therefore no longer calls
the two direct scene routines from pre-connect, spawn, class-selection,
SetPlayerPos, or movement refresh. GTA's normal streamer and the established
`04E4` refresh path remain active.

The diagnostic semantic gate remains default-off. Its current TXD/clothes
signals must not be presented as original behavior.

## Native CreateMenu

`STATIC_037`:

- constructor: `samp.dll+0xA7420`;
- row/column setters: `+0xA7530`, `+0xA7580`, `+0xA7600`;
- hide: `+0xA7670`;
- selected row: `+0xA7710`;
- show: `+0xA7740`;
- pool input processing: `samp.dll+0x8200`;
- GXT lookup hook: `samp.dll+0xA4030`.

The replacement now constructs and shows GTA's native menu panel rather than
using the D3DX approximation in the normal path. GTA panel handle `0` is a
valid first panel and must not be interpreted as failure.

Input parity from `CMenuPool::Process`:

- CPad index 16 / `ButtonCross` / default keyboard `Space` sends RPC 132
  `MenuSelect`;
- CPad index 15 / `ButtonTriangle` / default keyboard `Enter` or `F` sends RPC
  140 `MenuQuit`;
- Escape is not read by this original handler;
- selection is processed before quit and native hide is delayed one frame.

Comparable runtime runs:

- original:
  `20260727-000403-original-player-324579`;
- replacement:
  `20260727-000158-replacement-player-321003`.

Both runs opened the same `/menutest` fixture and selected row 0 with `Space`.
The replacement logged:

```text
menu_native: shown panel=0 ... backend=gta_panel
rpc-user-out id=132 name=MenuSelect menu=2 row=0 sent=1
```

The server invoked `OnPlayerSelectedMenuRow` with row 0 for both clients.
Because both clients now use GTA's panel renderer, the stock GTA texture,
font, selection, and column layout are shared. The Windows lab subsequently
captured a comparable external pixel pair:

- original:
  `windows-menu-original/20260727_110452_menu_original_pixel_145c2e61`;
- replacement:
  `windows-menu-replacement-final/20260727_115222_menu_replacement_pixel_53ae1513`.

The native panel, title, rows, stock texture, and geometry match visually in
that pair. The capture also exposed a separate replacement chat-layout gap:
the replacement chat used a smaller X origin and larger line step and
overlapped the menu title. See
`docs/re/windows_menu_chat_pixel_pair_20260727.md` for the static R5 evidence
and follow-up correction.

The D3DX emergency fallback still uses hard-coded Return/Escape semantics and
is not input-parity complete.

## TextDraw state

Implemented or corroborated in this pass:

- selectable TextDraw Escape sends click ID `65535` and clears selection mode;
- native CFont passes are suppressed while GTA's frontend or the scoreboard is
  active, matching the legacy draw gate;
- model-preview resources and native menu state are released on session reset;
- normal fonts and Font 5 use the existing GTA/CFont and cached RenderWare
  paths when those paths are available.

Open:

- Font 4 now has the native CTxdStore/RwTexture/CSprite2d path for the observed
  R5 library forms; `mdl<decimal>:texture` remains open because the replacement
  lacks R5's download-manager hash contract;
- Font 5 now includes the statically observed ped/vehicle/train/generic
  dispatch special cases, but still needs runtime goldens for skins, vehicles,
  vanilla objects, and SA-MP custom objects, including device reset and GMX
  cleanup;
- exact CFont wrapping, proportional widths, outline/shadow ordering, and
  selectable hit boxes still need pixel/trace comparison;
- the shaped proxy must remain a fallback, not be described as Font 5 parity.

## `/fpslimit`

`STATIC_037`:

- command parser: `samp.dll+0x688D0`;
- setter: `samp.dll+0xA0BB0`;
- frame pacing consumer: `samp.dll+0xA1C10`;
- constructor default: `samp.dll+0x9FF80`;
- startup config path: `samp.dll+0xC4E0C`.

Observed static behavior:

- accepted range is 20 through 90;
- the setter stores the wrapper value at `+0x5D`;
- the setter writes GTA DWORD `0xC1704C = 200`;
- it does **not** write GTA limiter-enable byte `0xBA6794`;
- constructor value is 90;
- absent or zero config becomes 48 and calls the setter;
- a valid 20-90 config calls the setter;
- an invalid non-zero config leaves 90 and skips the setter.

The replacement implements the same QPC-millisecond pacing branches, including
the swimming task type `0x10C` cases. Runtime artifact
`20260727-001418-replacement-player-340214` read `fpslimit=90` from the test
prefix and logged the expected setter state.

`PROBE_TRACE`: `/fpslimit 61` was also written immediately to `sa-mp.cfg` in
the replacement prefix, survived the running process, and was restored to
`/fpslimit 90` after the check. Runtime persistence is therefore covered for
the replacement. A matching original command run remains desirable.

Still required:

- original-vs-replacement timing histograms at limits 20, 48, 60, and 90;
- limiter-disabled and swimming tests;
- original-side command persistence confirmation.

## Resolution handling

`STATIC_037` found no references from R5 to the replacement's seven
video-mode-list widening patches. Those patches are modernization, not parity,
and are now disabled by default. They require explicit
`SAMPDLL_RESOLUTION_EXTENSIONS=1`.

All patch sites have exact GTA 1.0 US byte guards. The replacement's
select-device helper hook is also opt-in and byte guarded. The original client
does contain an Alt+Enter path around `samp.dll+0x61310`.

`PROBE_TRACE`: Windows run
`20260727_121645_altenter_no_windowedmode_12fff7fa`, replacement SHA256
`341956316018663d5f6a15850fefb28197469a3e509f6677c684b5390d378a2a`,
contained no `III.VC.SA.WindowedMode.asi`. A real held Alt+Enter chord changed
the live 800x600 client from fullscreen to a decorated window and a second
chord returned it to fullscreen. GTA remained responsive throughout, no dump
or exception was emitted, and the replacement D3D hook logged successful
`Reset #1` and `Reset #2` calls (`hr=0x00000000`) with lazy resource
recreation.

The directly comparable original R5 run
`20260727_122006_altenter_original_r5_30444d85` performs the same
fullscreen -> decorated 800x600 window -> fullscreen transition and also
remains responsive without a dump. The transition geometry therefore matches.
The pair exposed one small difference: R5 names the window `GTA:SA:MP`.
`STATIC_037` traced the title string at `samp.dll+0xE98E4`, the
`SetWindowTextA` IAT entry at `+0xE53BC`, and its startup call at
`+0x61F3F..+0x61F4B`. The replacement now applies that title once the first
valid GTA root window exists. Integrated Windows run
`20260727_124112_integrated_ui_parity_47f5b927` observed `GTA:SA:MP`
immediately and retained it through the UI checks without a dump.

## Quit, GMX, and network cleanup

Implemented:

- GMX increments a session generation and clears snapshot-consumer sequence
  latches;
- legacy GTA menu panels are hidden;
- TextDraws, objects, remote-player state, dialogs, audio, camera interpolation,
  checkpoints, pickups, and relevant overlay state are reset;
- local OnFoot, InCar, Passenger, Unoccupied, Trailer, Aim and Bullet sender
  cadence/counters are reset, including Passenger entry/exit latches and the
  BulletSync ammunition baseline;
- the cached armed weapon is cleared with its RPC sequence, preventing a
  pre-GMX weapon from leaking into the first sync packet of the next mode;
- jetpack, camera targeting, widescreen, controls, interior, gravity, and the
  local interior network value are restored to neutral state;
- the WinSock wrapper is now restartable and idempotent, so repeated shutdown
  cannot issue an extra owned `WSACleanup`.

Automated lifecycle coverage lives in `tools/reloop/lifecycle_probe.py`. It
grades initial connect/spawn, RPC 40 GMX reset, second InitGame/spawn, object
and menu cleanup, real `/q`, native process exit, and WinSock cleanup. Visual
TextDraw disappearance and physical remote-ped destruction remain explicit
manual checks when the fixture has no corresponding oracle.

Normal `ExitProcess(0)` does not guarantee a full non-termination
`DLL_PROCESS_DETACH` teardown; this must not be reported as a leak solely
because the runner cannot observe `process_detach: done` during process
termination.

`PROBE_TRACE`: coordinated run
`artifacts/runs/20260727-104505-replacement-all-391817` completed all 11
scripted cases, including 10 visual cases, with no `exception_filter`.
The report was `PASS_WITH_WARNINGS` only because the runner stopped the final
process and therefore did not observe a normal `process_detach`. This covers
one complete regression cycle; repeated long-duration GMX/quit stress remains
open.

`PROBE_TRACE`: the focused lifecycle run
`artifacts/runs/20260727-190810-replacement-lifecycle-gmx-849440`, replacement
SHA256
`39031a3ab89d1d531674ec607a5564dac1369b633916455c218f3b9d139a9b68`,
completed connect, initial spawn, active TextDraw/menu/object preconditions,
RPC 40 reset, second InitGame, second class selection/spawn, real `/q` and
native `ExitProcess(0)`. The adapter reported
`session_probe_reset=1 transport_preserved=1`; the analyzer found two
`spawn_finalize` markers, no client exception, no remaining GTA process and
no failed `WSACleanup`. Its verdict is `PASS_WITH_MANUAL_VISUAL` only because
the fixture cannot automatically prove pixel-level TextDraw disappearance or
physical destruction of a remote ped that was never streamed.

## AFK, pause, and background operation

Both Proton prefixes use:

```ini
[game]
autoPause=0
```

The replacement retains the seven-byte GTA anti-pause patch at `0x561AF0`,
corroborated by the 0.2x legacy code. Networking and sync processing continue
while the game window is unfocused.

The replacement previously sampled `GetAsyncKeyState` globally for local sync,
fire, scoreboard, and TextDraw suppression. That could treat a key typed into
another application as GTA input. Those reads are now accepted only when the
GTA root window is foreground. This does not pause network processing.

Open:

- runtime original-vs-replacement packet cadence while foreground, unfocused,
  and inside the GTA pause menu;
- original AFK/status icon and timeout behavior in remote name tags;
- exact pre-connect Escape behavior and whether the original connect delay
  continues or pauses behind the frontend;
- focus-loss handling for dialog/text input and device-reset transitions.

## Remaining high-priority compatibility gaps

1. Repeated long-duration lifecycle stress across GMX, second spawn, `/q`,
   and native exit; one 11-case coordinated cycle and one focused full GMX
   lifecycle pass.
2. Font 4 sprite TXD loading and Font 5 visual/device-reset goldens.
3. Resolution-list visual comparison beyond the now-matching Alt+Enter path.
4. AFK icon runtime placement, focus-loss cadence, and pause-menu network
   behavior.
5. Original-observer/visual parity for unoccupied and trailer playback, plus
   exact authority/cadence arbitration. Original-sender to replacement-receiver
   decode, application and GTA readback now have a focused live trace; outgoing
   209/210/211 and RPC 26/154 remain conservative implementations.
6. Complete surfing collision semantics, train edge cases, spectator
   lifecycle, virtual worlds, and outgoing interior RPC 118.
7. Two-client visual closure of remote BulletSync impacts/muzzle flash.
8. Final password-dialog pixel rerun for the reconstructed skin/layout.
9. SA-MP custom AtomicModelInfo expansion above vanilla model 14000.
10. Strict PE shape parity: entry point, section/import layout, and TLS.
