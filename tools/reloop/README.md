# reloop: unattended SA-MP compatibility runs

`reloop` drives the existing bare open.mp server and `test_cmds` fixture through
the original and replacement Lutris prefixes. It records each run beneath
`artifacts/runs/` without truncating the append-only client or server logs.

## Quick start

```bash
tools/reloop/reloop doctor
tools/reloop/reloop build
tools/reloop/reloop install-device-helper
tools/reloop/reloop run --client replacement --group all
tools/reloop/reloop matrix --group all
```

Add `--interaction` to `run` or `matrix` to install
`reloop_control.asi` and drive the T/chat and TAB/scoreboard state machine.
The run then contains `ui-interaction-states.json`, which can be reduced to
explicit checks with:

```bash
python3 tools/reloop/analyze_interaction.py artifacts/runs/<run>
```

For targeted dialog probes, `control_client.py type-enter --text VALUE` sends
the value through `WM_CHAR` and submits Enter without first opening chat. This
lets `/tpassword` verify that the client masks the visible field while RPC 62
still returns the original test value.

`--companion` additionally launches `ReLoopPeer` from the other prefix for
RPC23 scoreboard-click work. On Wayland the second Wine window may steal
effective focus, so companion runs are not freeze/camera evidence unless the
primary trace proves that T and TAB became active.

## GMX and clean-quit lifecycle probe

The replacement-only lifecycle probe keeps a TextDraw, the stock-style
`CreateMenu`, objects and remote-player metadata active while open.mp receives
`gmx`. It then requires RPC40, a complete session-generation reset, another
InitGame and spawn, and finally the client's real delayed `/q`/`ExitProcess`
path:

```bash
python3 tools/reloop/lifecycle_probe.py run
python3 tools/reloop/lifecycle_probe.py analyze artifacts/runs/<lifecycle-run>
```

`lifecycle-verdict.json` treats invalid `WSACleanup`, crashes, missing
menu/object reset markers, missing reinitialization, and a surviving native
game process as hard failures. Pixel-level TextDraw disappearance and physical
remote-ped cleanup remain explicit manual checks when the logs contain no
post-reset render count or streamed companion ped. A missing
`process_detach: done` is classified as expected when `/q` reached
`ExitProcess(0)`.

## Two-client sync fixture

`filterscripts/sync_pair.pwn` assigns the fixed test nicknames `SyncPilot` and
`SyncObserver`. Once both are spawned, the pilot-side control ASI can drive the
on-foot firearm, car, Rustler-driver, passenger, driverless-unoccupied and
articulated-trailer scenarios:

```bash
python3 tools/reloop/sync_pair_client.py all \
  --output artifacts/runs/<run>/sync-pilot-states.json
```

Short-lived observer effects can be sampled while the pilot input remains
held:

```bash
python3 tools/reloop/sync_pair_client.py rustler \
  --output artifacts/runs/<run>/sync-pilot-states.json \
  --observer-screenshot-label rustler-fire \
  --observer-screenshot-count 8 \
  --observer-screenshot-interval 0.1
```

Each screenshot is taken before the pilot key is released. Labels receive a
two-digit suffix when the count is greater than one.

The three edge-state cases can also be run as focused probes:

```bash
python3 tools/reloop/sync_pair_client.py passenger \
  --output artifacts/runs/<run>/passenger-pilot-states.json
python3 tools/reloop/sync_pair_client.py unoccupied \
  --output artifacts/runs/<run>/unoccupied-pilot-states.json
python3 tools/reloop/sync_pair_client.py trailer \
  --output artifacts/runs/<run>/trailer-pilot-states.json
```

`passenger` places the pilot in seat 1. `unoccupied` adds deterministic
server velocity to the same driverless setup so the first-player-passenger
authority path emits Packet 209. `trailer` attaches trailer model 435 to
tractor model 515 and holds forward input on the pilot, exercising Packet 210
after both vehicles have been confirmed streamed to both clients.

`passenger_g` is the separate client-originated entry case. It leaves a new
two-seat vehicle empty, places the on-foot pilot 2.4 units from its passenger
side, waits for that vehicle to be streamed to both clients, and then presses
VK_G for 150 ms:

```bash
python3 tools/reloop/sync_pair_client.py passenger_g \
  --output artifacts/runs/<run>/passenger-g-pilot-states.json
```

It is also selectable explicitly in the coordinated two-prefix runner:

```bash
python3 tools/reloop/sync_edge_probe.py run --scenario passenger_g \
  --server-mode replace --client-mode replace
```

The server writes a request-scoped `PASSENGER_ENTER_REQUEST` from
`OnPlayerEnterVehicle` (the semantic legacy RPC 26 receipt) and does not pass
the driver until `PASSENGER_ENTRY_RESULT` confirms the expected vehicle, seat
1, and `PLAYER_STATE_PASSENGER`. `PILOT_SYNC state=3` and observer Packet 211
application are separate verdict checks. The established `all` scenario list
is intentionally unchanged; request `passenger_g` explicitly.

For the one-host-prefix plus native-Windows-observer topology:

```bash
python3 tools/reloop/windows_sync_edge_probe.py --scenario passenger_g
```

The default remains host Original R5 as `SyncPilot` and native Windows as
`SyncObserver`. The Windows screenshot burst starts after the server has
verified the physical seat.

Use the explicit role swap to test local G handling in the Windows replacement:

```bash
python3 tools/reloop/windows_sync_edge_probe.py \
  --scenario passenger_g \
  --windows-role pilot \
  --deploy-windows-dll build-win32/samp.dll
```

This mode is rejected for every other scenario, including `all`. Windows
starts as `SyncPilot`; exactly one host prefix starts Original R5 as
`SyncObserver`. The host observer does not use the `reloop_control` API during
launch, setup, or the passenger action. After request-scoped `EDGE_SETUP`, the
runner invokes only the fixed `samp_lab.sh key PASSENGER` action, which holds
VK_G across multiple DirectInput frames, and then waits for
`PASSENGER_ENTRY_RESULT`.

Omit `--deploy-windows-dll` only when the intended replacement is already
installed on Windows. The fetched manifest must identify a non-original DLL;
an Original-R5 Windows pilot fails this replacement-probe verdict. The hard
checks are semantic RPC 26 receipt, the expected vehicle, seat 1, state 3,
both-client crash markers, candidate/installed hashes, and unchanged host
hashes. Because the observer is Original R5, its internal Packet 211 apply path
is unavailable; a successful swapped run is therefore reported as
`SERVER_TRACE_PASS_OBSERVER_INTERNALS_UNAVAILABLE`, with visual parity still
`TODO_VERIFY`. The Windows input action captures the pilot. After the verified
result the runner separately captures the host Original-observer desktop under
`observer/screenshots/passenger_g-after-entry.png`; failure to produce that
file fails the swapped run. Capture first tries the compositor and an input-free
X11 window grab. Only after those fail does the runner open the host control
endpoint and ask Original R5 to consume its strictly identity- and
byte-guarded screenshot-request flag; an F8 edge remains the compatibility
fallback for an older control ASI. This happens after the server has verified
the seat and therefore cannot contribute to the earlier Windows G action. Its
log slices are retained under `observer/client`.

Neither server callbacks nor screenshots are a raw wire capture, so retain
client net traces when the exact RPC 26 serialization itself is the question.

## Distributed Original-pilot sync runner

`distributed_sync_runner.py` reuses `sync_pair_client.py` for a conservative
one-host/one-Windows topology:

```text
local Original R5 + reloop_control = SyncPilot
native Windows                       = SyncObserver
```

The focused scenario set is `pistol`, `m4`, `sniper`, `angles`, `jetpack`,
`death`, and `pickup`; `all` runs exactly that order. Trailer is deliberately
outside this runner. GMX is a separate, explicit Windows-pilot scenario and is
not included in `all`. `ui_latches` is likewise an explicit Windows-pilot-only
scenario and is not included in `all`.

```bash
python3 tools/reloop/distributed_sync_runner.py --scenario all

python3 tools/reloop/distributed_sync_runner.py \
  --scenario angles \
  --screenshot-count 40 \
  --screenshot-interval 0.05
```

`angles` does not use absolute desktop cursor positions. Those positions were
observed to change while the sampled GTA `CCamera::InternalAim` camera
position stayed unchanged in the paired 20260728 Original-observer and
Replacement-observer runs. The current control ASI injects bounded relative
mouse pulses, and the driver stops on measured `CCamera::InternalAim` headings
approximately 35 degrees left and right of the post-setup baseline. If the
front vector is unavailable or does not move, the scenario fails before
labeling the screenshots as an angle comparison. The recorded states also
retain the local ped's matrix-forward heading, so camera-direction and
ped-direction differences remain separable.

By default the runner does not deploy a Windows DLL or ASI and does not change
probe-profile flags. Any pre-existing unmanaged probe flag is a preflight
failure, so the run cannot silently inherit an old invasive profile. Mutations
require their corresponding explicit options:

```bash
python3 tools/reloop/distributed_sync_runner.py \
  --scenario pistol \
  --deploy-windows-dll build-win32/samp.dll

python3 tools/reloop/distributed_sync_runner.py \
  --scenario jetpack \
  --deploy-windows-probe build-asi-probe/samp_probe.asi \
  --windows-probe-profile aim-bullet-jetpack

python3 tools/reloop/distributed_sync_runner.py \
  --scenario death \
  --windows-probe-profile death-cleanup

python3 tools/reloop/distributed_sync_runner.py \
  --scenario death \
  --windows-role pilot \
  --death-f4 \
  --windows-probe-profile death-cleanup

python3 tools/reloop/distributed_sync_runner.py \
  --scenario gmx \
  --windows-role pilot \
  --windows-probe-profile death-cleanup \
  --screenshot-count 120 \
  --screenshot-interval 0.05

python3 tools/reloop/distributed_sync_runner.py \
  --scenario ui_latches \
  --windows-role pilot \
  --windows-probe-profile ui-latches-r5
```

The death, GMX, and UI-latch forms are the supported reversed-role runs:
native Windows starts as `SyncPilot`, while the sole local Original-R5 prefix
starts as `SyncObserver` without using the control API. The death driver begins
a Windows screenshot burst, queues the existing request-file `death` scenario,
and waits for the request-scoped `PLAYER_DEATH` server event. The optional
`--death-f4` mode first sends the existing allowlisted Windows-lab `CLASS`
action, records its start/completion timestamps and a 0.75-second settle edge,
then captures and queues death normally. It is rejected unless both
`--scenario death` and `--windows-role pilot` are active. Forced respawn
remains outside this driver.

The GMX driver starts open.mp with the same stdin-owning process wrapper already
used by `lifecycle_probe.py`, captures Windows before and through the
transition, sends the existing `gmx` server-console command, waits for the new
gamemode banner and `SyncPilot` rejoin, then captures an explicit post-restart
frame. It rejects `--server-mode reuse`, because a reused server would give the
runner no verified console channel. After collection, the verdict requires the
current Windows log slice to contain `InitGame -> GameModeRestart (RPC 40) ->
InitGame` for replacement runs without the original probe. Original R5 does
not emit those replacement `rpc-in` lines. With
`--windows-probe-profile death-cleanup`, the verdict instead requires the
server restart, `SyncPilot` rejoin, `death_cleanup_r5 ... kind=gmx_reset`, and
the documented Original R5 DLL hash. The profile flag is restored to `passive`
during teardown. No Pawn command, gamemode API, or runtime bridge is added for
this path.

The `ui_latches` driver requires the documented Original R5 DLL and the
run-scoped `ui-latches-r5` profile. It performs exactly one bounded TAB hold,
two F6 edges, and three F7 edges. The verdict requires the nine-hook install
summary, scoreboard show/hide, chat open/close, at least three chat-mode
records, and no ring overflow. The action receipts provide screenshots, but
the verdict remains trace-only and visual parity stays `TODO_VERIFY`. ESC,
pause-menu, focus-loss, and arbitrary key automation are deliberately absent.

An explicitly selected probe profile is run-scoped: after Windows has stopped,
the runner restores the managed `passive` profile and verifies the resulting
empty flag set. Explicit DLL/ASI deployments use the remote lab's normal
hash-verified deployment and backup workflow; they are not silently rolled
back.

Preflight requires the documented local R5 DLL and requires the local control
ASI only while the local client is the pilot. It also requires
`[game] autoPause = 0` in both local and Windows
`III.VC.SA.WindowedMode.ini`, an idle Windows lab, no active local replacement
prefix, and (for a local pilot) an idle reloop-control port. It records local
and Windows DLL/ASI hashes, verifies explicit candidate hashes again from the
Windows run manifest, and checks that local hashes remain unchanged.

Every run creates an artifact beneath `artifacts/runs/` containing early/final
metadata, server and request-result slices, local pilot logs, per-scenario
driver state, Windows control receipts, the fetched Windows manifest and
current-run log slices, screenshot bursts, and the conservative verdict.
Cleanup verifies the Windows process inventory, removes only a pending
request ID proven to belong to the current driver artifact, stops only newly
created local-prefix processes, and stops the server only when the runner
started it.

The strongest successful verdict is
`TRACE_CAPTURED_VISUAL_UNVERIFIED`. Screenshots are retained evidence only;
the runner always writes `visual_parity=TODO_VERIFY` and never converts server
callbacks, logs, or image existence into a visual-parity claim.

## Original R5 death/cleanup artifact analyzer

Reduce an existing `death_cleanup_*` probe log without starting GTA, Wine, or
the Windows lab:

```bash
python3 tools/reloop/analyze_death_cleanup.py \
  artifacts/runs/<death-or-cleanup-run>
python3 tools/reloop/analyze_death_cleanup.py path/to/samp_probe.log \
  --output artifacts/runs/<run>/death-cleanup-analysis.json
```

The JSON reports GMX, connection-loss and quit-destructor pre/post pool
counts, UI latches, and `RemoveBuilding` counts. It also checks the statically
expected nested connection-loss to GMX publication order. Event pairing uses
only event kind plus event/ring sequence; pointers and ticks are excluded.
Missing target events or snapshots remain `TODO_VERIFY` and are never promoted
to `PASS`.

Run all three cases with coordinated prefix launch, log snapshots, physical
readback checks, and a conservative verdict:

```bash
python3 tools/reloop/sync_edge_probe.py run \
  --server-mode replace --client-mode replace

python3 tools/reloop/sync_edge_probe.py analyze \
  artifacts/runs/<sync-edge-run>
```

The runner launches and API-verifies the original pilot before starting the
replacement observer. Both prefixes must explicitly set `[game] autoPause=0`.
No ASI is installed or renamed; top-level ASI hashes are compared before and
after the run. `EDGE_SETUP` verifies the actual player vehicle, seat/state and
trailer relationship rather than merely confirming that the setup natives
returned. A successful automated result is deliberately named
`TRACE_PASS_VISUAL_UNVERIFIED`: packet decode, runtime application and GTA
readback are trace evidence, not a claim of pixel-identical motion.

The observer receives a fixed server camera for comparable screenshots. Server
markers record role spawn/streaming, player state, sampled input keys and
movement, and ordinary firearm bullet callbacks. Rustler driver weapons do not
produce `OnPlayerWeaponShot`; their parity verdict therefore requires an
observer screenshot/trace in addition to the pilot key marker.

## Deterministic UDP impairment

`udp_impairment_proxy.py` provides seeded loss, delay, jitter, and datagram
reordering without changing either client or server code. Run open.mp on
`127.0.0.1:7798`, bind the proxy to the second loopback address with the same
port, and point the client at `127.0.0.2:7798`:

```bash
python3 tools/reloop/udp_impairment_proxy.py \
  --listen 127.0.0.2:7798 \
  --upstream 127.0.0.1:7798 \
  --loss 0.05 --delay-ms 80 --jitter-ms 20 \
  --reorder 0.10 --reorder-hold-ms 60 --seed 37 \
  --log artifacts/runs/<run>/udp-impairment.jsonl \
  --stats artifacts/runs/<run>/udp-impairment-stats.json
```

The proxy intentionally keeps the upstream and downstream UDP port identical:
the legacy SA-MP transport transform depends on the peer port. It accepts one
client per process, records foreign senders, and emits direction-specific
receive/forward/drop counters. Use a separate temporary `reloop.toml` whose
`run.host` is `127.0.0.2` together with `--server-mode reuse` for a normal
artifact-producing run through the proxy.

For transport-only checks without GTA/Wine, build the
`samp_raknet_headless_probe` host target. It answers the SA-MP auth challenge
and can assert decoded packet IDs, including offline datagrams observed before
the public RakNet receive queue:

```bash
cmake --build build-host --target samp_raknet_headless_probe -j2
build-host/samp_raknet_headless_probe \
  --host 127.0.0.2 --port 7798 --duration-ms 10000 --expect-packet 34
```

For a fixture that is deliberately expected to reject before RakNet creates a
normal receive packet, add `--adapter-terminal`. This makes the expectation use
the same adapter drain/status path as the replacement runtime. Stop on any
unexpected normal packet rather than using this mode against a possibly
accepting server:

```bash
build-host/samp_raknet_headless_probe \
  --host 127.0.0.1 --port 7807 --duration-ms 3000 \
  --expect-packet 31 --adapter-terminal
```

See `docs/traces/network_adversity_headless_20260727.md` for the isolated
server-full fixture, the distinction between headless transport evidence and
original/replacement GUI evidence, and a seeded impairment result.

Client crash and streaming-hang verdicts use a three-attempt policy by default.
A single `PRECONNECT_CRASH`, `RUNTIME_CRASH`, `HANG_PRECONNECT_STREAMING`, or
`HANG_SPAWN_STREAMING` is retried automatically with the same scenario; only
three consecutive affected attempts are treated as reproducible. Every attempt
keeps its own artifact and the final attempt contains `retry-series.json`.
`--crash-attempts N` may raise the limit but never lowers it below three.

The default profiles are:

- original: `/home/chairman/Games/san-andreas-multiplayer-legacy-legacy`
  (Lutris game ID 55);
- replacement: `/home/chairman/Games/san-andreas-multiplayer-legacy-libsamp`
  (Lutris game ID 57).

`reloop run` compiles `test_cmds`, builds/deploys the replacement DLL when the
replacement profile is selected, restarts only the exact configured bare-server
executable, and launches `samp.exe` through
`GE-Proton10-34/files/bin/wine` with the exact selected prefix. It passes
`127.0.0.1:7778 -nReLoop` to the SA-MP launcher; Lutris is not involved at run
time.
The configured Lutris IDs/YAML files are optional diagnostics only.

Before every run, the MIT-licensed helper supplied at
`/home/chairman/Downloads/1483123471_SkipDeviceSelection/SkipDeviceSelection.asi`
is hash-verified and installed in the selected GTA root. Its only behavior is
to press Enter when GTA creates the `Device Selection` window. The standalone
`install-device-helper` command installs the same verified binary in both test
prefixes.

The server-side request is one line in
`scriptfiles/test_cmds_request.txt`:

```text
<request_id> <all|vehicle|player|pvars|ui|labels> <delay_ms> <autospawn 0|1> <player_name|*>
```

The filterscript consumes this file once and emits request-scoped markers:
`REQUEST_ACCEPTED`, `AUTO_SPAWN`, `RUN_START`, `RUN_DONE`, or `RUN_ABORT`.
Interactive `/tbatch` and `/testcmds ...` use remain available and have
`request=0`.

## Safety and lifecycle

- `--client-mode replace` (default) stops only processes whose environment
  contains the exact configured Wine prefix. `--client-mode fail` leaves them
  untouched and aborts the run.
- `--server-mode replace` (default) stops only a process whose executable is
  exactly `omp-server-bare/omp-server`.
- `--server-mode fail` never stops an existing server.
- `--server-mode reuse` attaches to an already running server; use this only
  when the newly compiled filterscript is already loaded.
- The client process group and only newly created processes carrying the exact
  configured prefix in their environment are stopped after the result marker.
- `--keep-client` leaves the client running for manual visual inspection.
- `--screenshots` captures the desktop at each `OBSERVE` record when
  `gnome-screenshot` or `grim` is available. Screenshots are evidence, not yet
  automatic visual parity verdicts. A portal/backend timeout disables further
  captures for that run instead of blocking the state machine.

## Verdicts

- `PASS`: all server-verifiable checks passed.
- `PASS_WITH_WARNINGS`: checks passed, with visual observations or a crash only
  after `RUN_DONE`.
- `INFRA_FAIL`: launch/connect/spawn did not reach a test marker.
- `PRECONNECT_CRASH`: the client exited before `RUN_START`.
- `RUNTIME_CRASH`: the client exited or logged an exception after start.
- `HANG_PRECONNECT_STREAMING`: timeout with no exception; the last
  `scene_prepare_step` is an open pre-connect call and no Join/NetGame marker
  was observed.
- `HANG_SPAWN_STREAMING`: timeout with no exception; Join/NetGame was observed
  and the last `scene_prepare_step` is an open class/spawn call.
- `PROTOCOL_MISMATCH`: a started run aborted or timed out.
- `STATE_MISMATCH`: `test_cmds` produced a failing result.
- `OPCODE_PARITY_UNVERIFIED`: state signatures match, but the selected
  scenarios do not yet have complete original handler/GTA-opcode trace tuples.

Each artifact contains `metadata.json`, `events.jsonl`, `verdict.json`, a short
`summary.md`, isolated server output, request-scoped test records, and only the
bytes appended to client logs during that run.

## Opcode parity contract

Matching server state is necessary but not sufficient. Compatibility requires
the same incoming RPC and, where the original handler delegates to GTA script,
the same GTA opcode path as SA-MP 0.3.7. Matrix output therefore reports a
separate `state_verdict` and `opcode_path_verdict`; a state-clean comparison is
`OPCODE_PARITY_UNVERIFIED` until original probe/static evidence covers its
opcode paths. See `docs/re/reloop_opcode_parity_contract_20260718.md`.

## Evidence scope

- `OPENMP_REF`: request polling and auto-spawn use the documented `fopen`,
  `fread`, `SetTimerEx`, `OnPlayerConnect`, `OnPlayerSpawn`, `SetSpawnInfo`,
  `SpawnPlayer`, and `IsPlayerSpawned` APIs.
- `INFERRED`: the default 1500 ms auto-spawn and 1000 ms post-spawn delay are
  deterministic fixture timing, not claims about original SA-MP behavior.
- Client compatibility verdicts still require `PROBE_TRACE` and visual review
  for `OBSERVE` steps; server-side state alone is not visual parity proof.
