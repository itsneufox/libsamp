# Original R5 Death, Respawn, F4, And Cleanup Memory Probe

Date: 2026-07-28

Status: `STATIC_037` probe implementation complete, including a guarded
terminal clean-quit checkpoint; one normal
death-to-respawn path, one F4-after-death class-selection path, and one
populated GMX/rejoin path are `OBSERVED_037` + `PROBE_TRACE`. Connection loss,
final-destructor cleanup, terminal ring drain, and clean hook restore remain
`TODO_VERIFY`.

## Scope

This note defines the focused, passive ASI profile used to observe two related
compatibility areas:

1. the local death, respawn, and F4 class-selection state machine;
2. pool, entity, and UI cleanup during GMX, connection loss, reconnect, and
   final `CNetGame` destruction.

The probe does not modify gameplay state or replace any original result. Each
wrapper takes bounded pre/post snapshots, calls the original routine through a
complete-instruction trampoline, and publishes the record to a fixed ring.
Only the probe worker writes the records to disk. The clean-quit wrapper can
wait on that worker for at most 1500 ms; it never performs file I/O itself.

The original runtime traces now cover one health-zero death followed by an
ordinary respawn and one F4-latched health-zero death followed by class
selection. Field names backed by those traces are identified below as
`OBSERVED_037` + `PROBE_TRACE`. Unexercised fields remain either `STATIC_037`,
raw fields deliberately left unnamed, or `TODO_VERIFY`.

## Supported Binary Identities

Original SA-MP R5:

- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- PE timestamp: `0x6372C39E`
- entry RVA: `0x000CBC90`
- image size: `0x0027E000`
- preferred image base: `0x10000000`
- base-relocation directory: RVA `0x272000`, size `0x9DA0`

GTA San Andreas 1.0 US:

- SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`
- PE timestamp: `0x427101CA`
- entry RVA: `0x00424570`
- image size: `0x01177000`
- PE checksum: `0x00DC5BEA`
- required load base: `0x00400000`

The ASI cannot hash a loaded module without adding synchronous file work, so
the runtime gate uses the listed PE identity values, the R5 relocation-table
presence, and GTA's fixed preferred base. R5 is allowed at a loader-selected
base. The known hashes document which files supplied those identity values and
the static bytes.

## Hook Table

All six entries, all six return tails, and the terminal callsite/import guards
must match before the first patch is installed. A failed partial install is
restored in reverse order.

| Routine | RVA | ABI | Entry bytes replaced | Guarded return tail |
|---|---:|---|---|---:|
| `CLocalPlayer::Process` | `0x74C0` | `thiscall int()` | `83 EC 10 53 55 56 8B F1` | `0x7E37`, plain `ret` |
| `CLocalPlayer::Spawn` | `0x3C20` | `thiscall int()` | `64 A1 00 00 00 00 6A FF 68 0B FF 0D 10` | `0x3EA7`, plain `ret` |
| `CLocalPlayer::HandleClassSelection` | `0x4080` | `thiscall void()` | `56 8B F1 8B 8E 04 01 00 00` | `0x40CA`, plain `ret` |
| `CNetGame::ShutdownForGameModeRestart` | `0xA540` | `thiscall void()` | `53 55 56 57 33 DB 33 FF 8B F1 33 ED` | `0xA730`, plain `ret` |
| `CNetGame::Packet_ConnectionLost` | `0xACF0` | `thiscall void(Packet *)` | `57 8B F9 8B 0F 85 C9` | `0xAD6E`, `ret 4` |
| `CNetGame::~CNetGame` | `0x9880` | `thiscall void()` | `53 56 57 8B F1 8B 0E` | `0x9A31`, plain `ret` |

Evidence: `STATIC_037`, R5 image identified above. The runs below observe
Process, Spawn, class-selection, and GMX-reset call counts and callers.
Connection-loss, destructor, and transition interpretations not explicitly
listed as observed remain `TODO_VERIFY`.

The Spawn entry's immediate DWORD at operand RVA `+0x3C29` is a PE HIGHLOW
relocation for preferred VA `0x100DFF0B`. The preflight normalizes only this
four-byte operand to `loaded samp.dll base + 0xDFF0B`; every other entry byte
and every return-tail byte remains exact. The trampoline copies the already
loader-relocated entry bytes. GTA has relocations stripped, so its absolute
memory sources remain gated to `0x00400000`.

The class-selection hook is intentionally the small state-transition routine,
not a render or input hook. The GMX and connection-loss hooks can nest because
the latter calls the former in the statically observed path; separate event
sequence numbers preserve that ordering.

## Terminal Clean-Quit Checkpoint

`STATIC_037`, original R5 hash documented above:

- the clean main-loop path calls `CNetGame::~CNetGame` at
  `samp.dll+0xC5076`; the destructor hook therefore sees caller
  `samp.dll+0xC507B`;
- the caller frees the returned object at `+0xC507C`, writes the zero held in
  `EDI` to the global NetGame pointer at `+0xC5084`, then executes
  `push edi; call [KERNEL32!ExitProcess]` at `+0xC508A`;
- the import call's exact return address is `samp.dll+0xC5091`;
- the R5 ExitProcess IAT slot is `samp.dll+0xE5188`.

The guarded callsite span is:

```text
RVA +0xC508A
57 FF 15 88 51 0E 10 61 5F 5E 5B C3
```

The absolute operand at `+0xC508D` is normalized to the loaded R5 base plus
`0xE5188`; all surrounding bytes remain exact. The slot must still equal the
current `KERNEL32!ExitProcess` export. Installation changes the aligned
four-byte slot to the ASI wrapper with an atomic compare/exchange. Restoration
uses the inverse compare/exchange and refuses to overwrite a slot no longer
owned by the probe.

Only caller `+0xC5091` requests terminal handling. Every other caller through
the shared import slot immediately reaches the saved original function. The
clean caller records the exit code, thread/tick, global NetGame pointer,
latest death-cleanup ring sequence, and clean-destructor sequence. It then
signals the existing worker stop event and waits at most 1500 ms. The worker:

1. drains the focused ring through the captured sequence;
2. restores the owned ExitProcess slot and six entry hooks;
3. finishes its normal stop logging;
4. writes `death_cleanup_exit_r5` and signals the completion event.

The game thread calls the saved real `ExitProcess` after the completion event
or after the timeout. A terminal marker with `drain=completed`,
`netgame=0x00000000`, nonzero `destructor_seq`, equal-or-newer
`flushed_seq/requested_seq`, `exit_iat_restored=1`, and caller `+0xC5091` is
the intended clean-quit oracle. None of those runtime claims have been
observed yet; they remain `TODO_VERIFY`.

## Captured Local State

The local snapshot starts at the `CNetGame` and pool chain, then records:

- local-player active/wasted state at `+0xF0/+0xF4`;
- local `CPlayerPed` wrapper at `+0x104`;
- spectating and cleared-to-spawn state at `+0x108/+0x143`;
- the 46-byte SpawnInfo region at `+0x14F` as a bounded FNV-1a hash plus its
  first 16 raw bytes;
- has-SpawnInfo at `+0x17D`;
- F4 wants-another-class at `+0x2FA`;
- class-selection/input-ownership state at `+0x302/+0x306`;
- raw class-selection ticks at `+0x147/+0x14B/+0x30A`;
- current vehicle wrapper at `+0x310`.

From the player wrapper it follows the GTA ped pointer at `+0x2A4`. The GTA
snapshot records the entity matrix/RW object/flags/status, ped flags,
intelligence, raw action, health bits, ped state, and eleven root task
pointers. The `CPed+0x530` action offset is corroborated statically by the R5
`CPlayerPed::GetActionTrigger` wrapper. Values 1, 54, and 55 occur in the
normal-death trace below; semantic names for 54 and 55 remain `TODO_VERIFY`.

The same record contains scoreboard, dialog, textdraw-selector, chat,
class-selection GUI, input/cursor raw fields, two camera values, and three raw
frontend bytes. These are captured as raw transition evidence so an
original/replacement diff need not assume their semantics prematurely.

`CLocalPlayer::Process` is hot. Its record is emitted only when the pre/post
snapshot differs, the post-state differs from the last published post-state,
or one second has elapsed. Spawn and class-selection calls always publish.

## Captured Cleanup State

`CNetGame+0x3DE` supplies the pool aggregate used by the R5 destructor and GMX
paths. The profile records all nine raw pool pointers and bounded occupancy
counts for:

- vehicles: 2000 listed slots and wrappers;
- remote players: 1004 auxiliary slots and wrappers;
- pickups: 4096 raw GTA handles, server-ID entries, and timers;
- objects: 1000 listed slots and wrappers;
- actors: 1000 listed slots and wrappers;
- gang zones: 1024 listed slots;
- textdraws: 2048 listed slots;
- 3D text labels: 2304 listed slots;
- menus: 128 listed slots and the raw current-menu byte.

For the first nonempty vehicle slot it also records wrapper, entity/GTA
vehicle, matrix, RW object, and entity flags. The first nonempty object and
actor chains are recorded in the same bounded fashion. This is sufficient to
detect a stale representative wrapper or GTA entity while keeping the hook
bounded; a later profile may add a full slot dump if a trace proves that is
needed. A count of `0xFFFFFFFF` means that the corresponding array was not
readable; it must not be interpreted as an empty pool.

The raw DWORD at `samp.dll+0x14FD88` is logged as
`remove_building_count`. Existing static/lifecycle evidence suggests that the
RemoveBuilding list is process-lifetime rather than GMX-lifetime state.
Whether the value actually persists across the target GMX scenario is
`TODO_VERIFY` and is one of the explicit questions for the first GMX run.

## Trace Contract

The hook-side ring contains 256 fixed records. It uses monotonic ring and
event sequence numbers and reports an explicit overflow count if the worker
falls more than one ring behind. The worker emits:

- `death_cleanup_r5`: event, thread, frame, caller/hook RVA, object, argument,
  and original return value;
- `death_cleanup_local_r5`: local/player/ped state;
- `death_cleanup_tasks_r5`: GTA intelligence and root task pointers;
- `death_cleanup_ui_r5`: UI, input, camera, and frontend raw state;
- `death_cleanup_pools_r5`: pool pointers and occupancy counts;
- `death_cleanup_entities_r5`: representative entity chains.
- `death_cleanup_exit_r5`: terminal caller/exit code, final global NetGame
  pointer, destructor/ring boundary, drain result, timeout bound, and IAT
  restoration state.

Pointers, ticks, frames, and caller addresses must be normalized before
original/replacement diffing. The event and phase fields should remain intact.

## Activation

Select the focused Windows profile:

```bash
tools/windows/remote_lab/samp_lab.sh probe-profile death-cleanup
```

Equivalent direct toggles are:

```text
SAMP_PROBE_DEATH_CLEANUP_HOOKS=1
samp_probe_death_cleanup_hooks.flag
```

This focused mode skips normal Winsock/IAT and unrelated code-hook sets. It
must be run only against the documented original binaries, for a short
controlled scenario, without hot-unloading the ASI while a hook may execute.

## Original R5 Normal-Death Capture

Artifact:

```text
artifacts/runs/20260728-141552-distributed-sync-death-1526481/
```

Topology:

```text
native_windows_pilot+local_original_r5_observer
```

The Windows pilot used the original R5 DLL and GTA executable documented
above. The deployed Death/Cleanup ASI SHA256 was
`2c8cf403cc7a5e15373abc1b766ec26da5fd4f04e096b6d7806ce565a9dab2c5`.
The focused probe log is:

```text
windows/20260728_141608_dist_sync_death_pilot_e67f84f9/logs/samp_probe.log
```

Its SHA256 is
`2c9c57f60b922335affcdd98f4f70d88bb18cff332de73ae7c3f0aa69f4fc106`.
The server set the pilot's health to zero and recorded the matching
client-originated death. It later recorded the pilot as spawned again without
the test driver injecting a respawn key.

### Probe Integrity

`PROBE_TRACE`:

- all six guarded hooks installed against the expected original identities at
  relocated R5 base `0x03EA0000`;
- the log contains 58 focused records: 55 `local_process`, two `spawn`, and
  one `class_selection`;
- there is no focused-ring overflow marker, exception marker, or crash marker;
- no GMX, connection-loss, or destructor event occurred, and every emitted
  record has `cleanup=0`;
- there is no hook-restore or process-detach marker. The lab stopped the still
  responsive GTA and launcher processes after collecting the run, so this
  artifact is not evidence for clean shutdown restoration.

The absence of cleanup events in this run is expected from its narrow
death-only scenario. It must not be interpreted as cleanup parity.

### Death-to-Respawn Timeline

The table is ordered by hook tick rather than output sequence. The respawn
`Spawn` hook is nested inside the `CLocalPlayer::Process` event numbered 893,
so the inner record (`seq=40`, event 894) is published before the outer record
(`seq=41`, event 893). Task roots use zero-based indices into the eleven raw
root slots; omitted slots are zero.

| Tick / frame | Hook phase | Active / wasted | Action | Health / dead | Camera raw | Nonzero task roots |
|---|---|---|---:|---|---|---|
| `53011687 / 906` | last throttled live baseline, `local_process` pre/post | `1 / 0` | 1 | `100.0` (`0x42C80000`) / 0 | `4,0` | `[4]=101D60D8 [8]=101D6258 [10]=101D6158` |
| `53012578 / 952` | death edge, `local_process` pre | `1 / 0` | 1 | `0.0` (`0x00000000`) / 1 | `4,0` | `[4]=101D62D8 [8]=101D6258` |
| `53012578 / 952` | death edge, `local_process` post | `0 / 1` | 1 | `0.0` / 1 | `4,0` | `[4]=101D62D8 [8]=101D6358` |
| `53012609 / 953` | next `local_process` | `0 / 1` | 54 | `0.0` / 1 | `4,0` | `[2]=101D64D8 [4]=101D62D8 [8]=101D6358` |
| `53013187 / 983` | wasted camera/task phase | `0 / 1` | 55 | `0.0` / 1 | `29,0` | `[2]=101D76D8 [4]=101D62D8 [8]=101D6358` |
| `53014187 / 1034` | sustained wasted phase | `0 / 1` | 55 | `0.0` / 1 | `29,0` | `[2]=101D76D8 [4]=101D62D8 [8]=101D6358` |
| `53015187 / 1086` | sustained wasted phase | `0 / 1` | 55 | `0.0` / 1 | `29,0` | `[2]=101D76D8 [4]=101D62D8 [8]=101D6358` |
| `53016250 / 1138` | outer `local_process` pre | `0 / 1` | 1 | `100.0` / 1 | `29,0` | `[4]=101D64D8 [8]=101D65D8 [9]=101D66D8` |
| `53016265 / 1138` | nested `spawn` post | `1 / 0` | 1 | `100.0` / 0 | `29,0` | `[4]=101D66D8 [8]=101D6958` |
| `53016250 / 1138` | outer `local_process` post | `1 / 0` | 1 | `100.0` / 0 | `29,0` | `[4]=101D66D8 [8]=101D6958` |
| `53016281 / 1139` | following `local_process` | `1 / 0` | 1 | `100.0` / 0 | `4,0` | `[4]=101D6758 [8]=101D6A58` |

`OBSERVED_037` + `PROBE_TRACE`:

- the health/dead edge is visible before R5 flips its local fields from
  `active=1,wasted=0` to `active=0,wasted=1` in the same Process call;
- action 54 follows 31 ms and one GTA frame later; action 55 and raw camera
  value 29 are visible 609 ms and 31 frames after the death edge;
- the nested successful `Spawn` occurs 3687 ms and 186 frames after the death
  edge. Raw health is already 100.0 and action is already 1 on entry, while
  `dead_or_wasted` and the local active/wasted pair still retain the dead
  state until the Spawn body returns;
- raw camera value 29 remains installed through Spawn, then returns to 4 on
  the following frame;
- `ped_wrapper=0x0FE841E0`, `gta_ped=0x1011B540`,
  `intelligence=0x10207F10`, `matrix=0x11FB598C`, and `rw=0x1212F260`
  remain stable across this captured death and respawn. These concrete
  pointers are run-local identities and must be normalized in diffs;
- `cleared_spawn=1` and `has_spawn=1` remain set. `wants_class`,
  `class_selection`, and `class_input` remain zero throughout the death
  interval;
- scoreboard, dialog, textdraw selector, chat input, and class GUI are
  inactive in every death sample. This does not answer how an already-open UI
  latch is cleared.

### Screenshot Review

The Windows burst contains 120 frames at a requested 50 ms interval,
800x600, from `2026-07-28T12:16:42.7612643Z` through
`2026-07-28T12:16:49.9876199Z`. A 14-frame overview and an 11-frame respawn
contact sheet were inspected locally.

`OBSERVED_037` + `PROBE_TRACE`:

- frame 001 already shows the falling/death pose, and frames 040-046 show the
  body in the sustained wasted-camera view;
- frame 048 (`12:16:45.580Z`) is the dark transition;
- frame 050 (`12:16:45.689Z`) shows the new player/camera view, frames 050-052
  still contain the short camera/character transition, and frame 054
  (`12:16:45.925Z`) shows the fully standing character;
- the HUD changes from the death-state fist display to the respawn weapon and
  restored health. No class-selection GUI appears.

This is a qualitative visual description of one original run, not a
replacement comparison or a pixel-parity verdict. The machine verdict remains
`TRACE_CAPTURED_VISUAL_UNVERIFIED`.

## Original R5 F4-After-Death Capture

Artifact:

```text
artifacts/runs/20260728-142159-distributed-sync-death-1536077/
```

The topology, original DLL/GTA identities, and deployed focused ASI are the
same as in the normal-death run. The focused probe log is:

```text
windows/20260728_142215_dist_sync_death_pilot_2df975bd/logs/samp_probe.log
```

Its SHA256 is
`4af7a6e12374ead4e408caea135b0c6cdf5ee909d4d82d1336ddda0c60f9319c`.
The driver sent the existing allowlisted `CLASS` input action while the
Windows original client was alive, then issued the request-scoped health-zero
scenario. The server observed the matching client death. It did not inject a
respawn or class-selection action.

### Probe Integrity

`PROBE_TRACE`:

- all six guarded hooks installed against the expected identities at relocated
  R5 base `0x03DD0000`;
- the log contains 65 focused records: 62 `local_process`, one initial
  `spawn`, and two `class_selection` calls;
- there is no focused-ring overflow, exception, crash, GMX, connection-loss,
  destructor, or hook-restore marker;
- the lab stopped the responsive process after collection, so this run also
  does not establish clean detach or hook restoration.

### F4-to-Class-Selection Timeline

The first class-selection call belongs to initial join. The relevant
post-death call is nested in event 1060, so its inner event 1061 record is
published first.

| Tick / frame | Hook phase | Active / wasted | Spawn flags | Wants class / input | Health / action | GUI / input depth | Camera raw |
|---|---|---|---|---|---|---|---|
| `53379390 / 901` | live `local_process` pre | `1 / 0` | cleared `1`, has `1` | `0 / 0` | `100.0 / 1` | hidden / `0,-1` | `4,0` |
| `53379390 / 901` | same Process post, F4 edge | `1 / 0` | cleared `1`, has `1` | `1 / 0` | `100.0 / 1` | hidden / `0,-1` | `4,0` |
| `53383609 / 1115` | death Process pre | `1 / 0` | cleared `1`, has `1` | `1 / 0` | `0.0 / 1` | hidden / `0,-1` | `4,0` |
| `53383609 / 1115` | death Process post | `0 / 1` | cleared `1`, has `0` | `1 / 0` | `0.0 / 1` | hidden / `0,-1` | `4,0` |
| `53384203 / 1146` | wasted phase | `0 / 1` | cleared `1`, has `0` | `1 / 0` | `0.0 / 55` | hidden / `0,-1` | `29,0` |
| `53387281 / 1301` | nested `HandleClassSelection` pre | `0 / 0` | cleared `1`, has `0` | `1 / 0` | `100.0 / 1` | hidden / `0,-1` | `29,0` |
| `53387281 / 1301` | nested `HandleClassSelection` post | `0 / 0` | cleared `0`, has `0` | `1 / 0` | `100.0 / 1` | hidden / `0,-1` | `29,0` |
| `53387281 / 1301` | outer Process post | `0 / 0` | cleared `0`, has `0` | `0 / 0` | `100.0 / 1` | hidden / `0,-1` | `29,0` |
| `53387296 / 1302` | following Process post | `0 / 0` | cleared `0`, has `0` | `0 / 1` | `100.0 / 1` | visible / `2,-1` | `4,0` |
| `53387312 / 1303` | next Process | `0 / 0` | cleared `1`, has `1` | `0 / 1` | `100.0 / 1` | visible / `2,-1` | `4,0` |
| `53387343 / 1304` | settled selection scene | `0 / 0` | cleared `1`, has `1` | `0 / 1` | `100.0 / 1` | visible / `2,-1` | `15,0` |

`OBSERVED_037` + `PROBE_TRACE`:

- F4 is consumed by `CLocalPlayer::Process` while alive: `wants_class` flips
  from zero to one in that call without opening the class GUI or changing the
  active state;
- death still performs the ordinary `active 1->0`, `wasted 0->1` transition
  and reaches action 55/camera 29;
- 3672 ms and 186 frames after the death edge, the outer Process clears the
  wasted flag before calling `HandleClassSelection` from
  `samp.dll+0x7DE1`. There is no `CLocalPlayer::Spawn` call on this branch;
- the class-selection call clears the raw `cleared_spawn` field. The outer
  Process then clears `wants_class`;
- on the next frame, class input becomes one, the class GUI becomes visible,
  input depth changes from zero to two, and the raw camera value returns from
  29 to 4. One frame later a new SpawnInfo hash appears
  (`0x147E70C9 -> 0xC19D308A`) while the local player remains inactive. The
  class scene settles on raw camera value 15;
- the local wrapper, GTA ped, intelligence, matrix, and RW object remain the
  same run-local pointers across death and entry into class selection.

The raw field currently logged as `class_selection` remains zero even while
the GUI is visibly active. Its semantic label therefore remains
`TODO_VERIFY`; `class_input`, the GUI byte, and input depth are the directly
observed activation signals.

### Screenshot Review

The Windows burst contains 120 800x600 frames at a requested 75 ms interval
from `2026-07-28T12:22:53.6413383Z` through
`2026-07-28T12:23:03.5320648Z`. Frames 001-040 show the death fall and wasted
camera. By frame 050 the original class-selection interior, preview ped, and
the three legacy buttons are visible; that scene remains stable through frame
120.

This establishes the visible branch outcome, not replacement pixel parity.
The machine verdict remains `TRACE_CAPTURED_VISUAL_UNVERIFIED`.

## Replacement Death/Respawn Regression

Replacement DLL:

```text
build-win32/samp.dll
SHA256=c03d14beb6d1b0ab5dc0f3d47e7f85518f226c94ada1a6b3440913fe3d88458d
```

The manifest of each Windows run records that exact installed hash. The
Death/Cleanup ASI remained present but its focused hook flag was disabled, so
the following results are replacement runtime/network traces and screenshot
evidence, not original-hook memory snapshots.

### Normal respawn

Artifact:

```text
artifacts/runs/20260728-142801-distributed-sync-death-1554847/
```

Run-local Windows runtime log:

```text
windows/20260728_142815_dist_sync_death_pilot_281c54a7/
  latest_log_bytes/samp_runtime.log
SHA256=690ef04a57255dcb68ceb548a328887044ca5f327607c7181db1947f9906f8b0
```

`PROBE_TRACE`:

- the isolated run-local log has one current `process_attach` and no exception
  or fatal marker;
- health zero produces one local Death report at runtime line 918 and the
  server observes the matching player death;
- when GTA recovers health/action after the wasted interval, the replacement
  schedules the full shared spawn application at line 1064, completes it at
  line 1093, and only then sends RespawnNotify at line 1094;
- the run-local net trace records RespawnNotify followed by health-100
  OnFootSync. The server's post-respawn position/health updates are then
  applied without a second death report;
- the 120-frame, requested-50-ms burst shows the death pose through frame 51,
  a short low/ground-occluded camera transition in frames 52-62, and a fully
  visible standing ped with stable camera from frame 63 through frame 120.

This closes the earlier functional defect where health recovery could notify
the server without executing the complete local spawn application. The short
replacement camera transition has not yet been frame/pixel-diffed against the
original transition and remains `TODO_VERIFY`.

### F4-after-death branch

Artifact:

```text
artifacts/runs/20260728-143147-distributed-sync-death-1575191/
```

Run-local Windows runtime log:

```text
windows/20260728_143201_dist_sync_death_pilot_ad6fb1bd/
  latest_log_bytes/samp_runtime.log
SHA256=a9ff84831bc87084beb34ca431a7e17325f9d4057143980b338212e3d6d9d924
```

`PROBE_TRACE`:

- the controlled `CLASS` input latches F4 while alive at runtime line 882;
- death still emits one local Death report at line 927;
- after the wasted interval, line 1071 consumes the F4 latch and explicitly
  suppresses the normal respawn application;
- the net trace records exactly one post-death RequestClass, the replacement
  enables the class-selection overlay at runtime lines 1074-1075, and no
  `respawn_apply_*` marker occurs on this branch;
- the 120-frame screenshot burst shows the death scene through frame 40 and
  the class-selection interior, preview ped, and three legacy buttons by frame
  50. The scene remains stable through frame 120, matching the branch outcome
  and approximate transition point of the original capture.

There is no exception marker. This establishes functional branch parity for
the tested F4 latch and confirms that the normal-respawn fix does not bypass
class selection. Pixel parity of the class-selection renderer remains a
separate visual question.

## Original R5 Populated-GMX Capture

Artifact:

```text
artifacts/runs/20260728-144428-distributed-sync-gmx-1646159/
```

The Windows pilot used the documented original R5 DLL. The deployed integrated
ASI SHA256 was
`0b6b1a8d8a2d551fd2e17bf6cbb37ce6e6747f34661a3ed811bd36ba936a4440`.
The isolated focused log is:

```text
windows/20260728_144443_dist_sync_gmx_pilot_ee1502b0/
  latest_log_bytes/samp_probe.log
SHA256=7474fe5d3e5f0b0c1a7ea4d8332daeb446dbbdf119d02e320a8673fc953d3b8f
```

The server-console driver issued `gmx` only after the native Windows pilot and
the sole local original-R5 observer were spawned and mutually streamed. The
server then emitted a second gamemode banner and accepted a second
`RPC137 ServerJoin` from `SyncPilot`.

### Probe Integrity And Runner Note

`PROBE_TRACE`:

- all six guarded hooks installed at relocated R5 base `0x04130000`;
- the focused ring published one `gmx_reset` event with complete pre/post
  cleanup snapshots and no overflow or parse error;
- the current Windows slice contains no crash or exception marker;
- the first runner verdict was `FAIL` only because its R5 branch incorrectly
  required replacement-only `rpc-in id=139/40/139` log strings. The server
  restart, pilot rejoin, original hash, and `kind=gmx_reset` were all present.
  The runner contract now uses those original-compatible predicates when the
  `death-cleanup` profile is selected;
- the lab stopped the responsive process after collection, so clean hook
  restoration and the final `CNetGame` destructor are still not established.

### Synchronous GMX Reset

The GMX wrapper entered at `samp.dll+0xA540`, caller
`samp.dll+0x3AEBC`, tick `54727953`, frame 940. Its original body nested one
`CLocalPlayer::Process` event; consequently event 697 was published before the
outer GMX record for event 696.

| State | Pre | Post |
|---|---:|---:|
| NetGame raw state | 5 | 11 |
| local active / has SpawnInfo | `1 / 1` | `0 / 0` |
| health / dead-or-wasted | `100.0 / 0` | `0.0 / 1` |
| vehicles listed / wrappers | `4 / 4` | `0 / 0` |
| objects listed / wrappers | `19 / 19` | `0 / 0` |
| textdraws listed | 1 | 0 |
| remote auxiliary / wrappers | `6 / 6` | `6 / 6` |
| RemoveBuilding rule count | 15 | 15 |

`OBSERVED_037` + `PROBE_TRACE`:

- R5 synchronously destroys the populated vehicle, object, and textdraw
  entries during `+0xA540`;
- the six remote-player/NPC wrapper entries are not destroyed inside this
  immediate reset call. This does not prove that they survive later network
  processing, so delayed remote-pool lifetime remains `TODO_VERIFY`;
- the append-only RemoveBuilding count is unchanged at 15, corroborating the
  static process-lifetime rule-store interpretation;
- pickups, actors, gang zones, labels, and menus were empty in this fixture.
  Their zero deltas are not evidence for populated cleanup behavior;
- the local ped wrapper, GTA ped, intelligence, matrix, and RW-object pointers
  remain allocated across the synchronous reset. R5 instead zeroes health,
  marks the ped dead/wasted, changes task roots, and makes the local player
  inactive;
- scoreboard, dialog, textdraw selection, chat input, class GUI, input depth,
  and frontend bytes are unchanged inside the reset call because each was
  inactive. Raw camera mode changes from 4 to 15 immediately after the hook
  returns.

### Rejoin Timeline

The original keeps the same `CNetGame`, local-player wrapper, and GTA ped
through the restart. Approximately 12,000 ms after the GMX hook, the second
InitGame path invokes `HandleClassSelection`: health returns to 100, the
dead/wasted test clears, class input becomes active, and the class GUI/input
depth become `visible / 2`. A new SpawnInfo appears on the next frame.

At tick `54741453`, 13,500 ms after GMX and 1,500 ms after class selection,
`CLocalPlayer::Spawn` succeeds. It changes local active `0 -> 1`, closes class
input/GUI, and returns the camera from raw mode 15 to mode 4 on the following
frame. This fixture's server automatically selected and spawned the returning
player; the timing is therefore evidence for this exact server sequence, not
a universal R5 reconnect timeout.

The 120-frame burst began just after the console command and shows the original
restart/reconnect camera plus `The server is restarting..`/reconnection chat
sequence without a crash. It ends before the later class-selection and spawn
events, so those outcomes are established by the memory/server traces rather
than by this short visual burst.

### Replacement GMX Comparison

The comparable replacement run is:

- artifact:
  `artifacts/runs/20260728-145211-distributed-sync-gmx-1657080`;
- replacement DLL SHA256:
  `c03d14beb6d1b0ab5dc0f3d47e7f85518f226c94ada1a6b3440913fe3d88458d`;
- result: `TRACE_CAPTURED_VISUAL_UNVERIFIED`.

`PROBE_TRACE`: the replacement receives the expected
`RPC 139 -> RPC 40 -> RPC 139` sequence, destroys 19 objects, four vehicles,
and the listed remote player, clears its UI state, reconnects, and completes a
new spawn without a crash.

The run also exposed one concrete parity defect. Its GMX reset logged only
`records_persisted=9`, while original R5 retained 15. The fixture sends repeated
RemoveBuilding rules; the replacement's former equality filter collapsed them
while R5's `samp.dll+0x9D3D0` appends each RPC. The filter has therefore been
removed under `OBSERVED_037 + PROBE_TRACE + STATIC_037`, while the replacement's
defensive 256-record capacity remains intentionally conservative.

The corrected replacement was then rerun:

- artifact:
  `artifacts/runs/20260728-145828-distributed-sync-gmx-1669162`;
- replacement DLL SHA256:
  `693a78e7f40e5d579997f9a126bd0082ddf2495c56d78bce8b657421b259e712`;
- result: `TRACE_CAPTURED_VISUAL_UNVERIFIED`.

`PROBE_TRACE`: the reset now logs `records_persisted=15`, matching the
original fixture. The runner also confirms the full
`RPC 139 -> RPC 40 -> RPC 139` cycle, server restart, Windows pilot rejoin,
and no crash marker. This closes duplicate-rule count parity for the exercised
GMX sequence; it does not close later IPL stream-hook timing or capacity
parity.

The replacement synchronously removes its listed remote player, whereas the
original hook retained all six remote/NPC wrappers at its immediate return.
This is not corrected yet: the original's delayed cleanup point has not been
captured, so changing ownership timing now would be speculative.

## Remaining Runtime Matrix

The remaining controlled original runs should capture one occurrence of each:

1. select a class and spawn from the post-death F4 scene;
2. open dialog/chat/TAB state immediately before death and observe which
   latches the original clears;
3. populated actor/pickup/menu/label pools and active UI immediately before
   GMX; also follow remote-wrapper cleanup after the synchronous reset;
4. connection loss followed by reconnect;
5. clean quit through the actual `CNetGame` destructor and confirmed terminal
   marker/ring drain/hook restore; `process_detach` is not required as the
   evidence source;
6. frame-diff the short original and replacement normal-respawn camera
   transitions under an identical capture cadence.

The captured death paths are evidence for their exercised branches, not a
blanket death-system or pixel-parity conclusion. Only the fields directly
exercised in each future trace may be upgraded to `OBSERVED_037` or
`PROBE_TRACE`.

## Implementation Checks

Completed locally on 2026-07-28:

- built the complete ASI as MinGW i686 `Release` with `-Wall -Wextra`;
- verified the result is a PE32 Intel i386 DLL;
- checked the six original entry and tail byte sequences directly against the
  documented R5 file;
- checked the terminal `push edi; call [ExitProcess]` span at
  `samp.dll+0xC508A`, return address `+0xC5091`, and IAT slot `+0xE5188`
  directly against that file;
- verified the R5 relocation table contains HIGHLOW entries `+0x3C29` and
  `+0xC508D` and made both guarded operands ASLR-aware;
- inspected the generated wrapper code: Process, Spawn, class selection, GMX,
  and destructor return with plain `ret`; connection loss returns with
  `ret 4`;
- ran `git diff --check` and `bash -n` on the lab wrapper.
- built the checkpoint-enabled integrated ASI with MinGW i686 and ran the five
  terminal source-contract tests.

The original death/F4 captures used integrated ASI SHA256
`2c8cf403cc7a5e15373abc1b766ec26da5fd4f04e096b6d7806ce565a9dab2c5`;
the later GMX capture used
`0b6b1a8d8a2d551fd2e17bf6cbb37ce6e6747f34661a3ed811bd36ba936a4440`.
The Death/Cleanup translation unit also compiles separately with
`-Wall -Wextra -Werror`. The GMX hook is now runtime exercised; the
connection-loss/destructor hooks, terminal marker, and clean restore path
remain `TODO_VERIFY`.
