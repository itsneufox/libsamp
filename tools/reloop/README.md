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
on-foot firearm, car, and Rustler-driver scenarios:

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

Crash verdicts use a three-attempt policy by default. A single
`PRECONNECT_CRASH` or `RUNTIME_CRASH` is retried automatically with the same
scenario; only three consecutive crash attempts are treated as reproducible.
Every attempt keeps its own artifact and the final attempt contains
`retry-series.json`. `--crash-attempts N` may raise the limit but never lowers
it below three.

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
