# Windows SA-MP Remote Test Lab

This kit installs a small, auditable automation layer under `C:\samp-test`.
It is intended for a dedicated Windows test machine with an already installed
GTA San Andreas/SA-MP tree. It does not copy proprietary game assets into the
repository.

## Security model

- `sshadmin` controls scripts, configuration, incoming DLLs, and deployments.
- SSH password login and forwarding are disabled. The Windows firewall and the
  authorized key both restrict access to source addresses in `192.168.0.0/16`.
- The logged-on desktop user can write command results, run artifacts, dumps,
  screenshots, and agent state, but cannot modify installed agent scripts.
- The interactive queue accepts only `ping`, `screenshot`, constrained named
  keys/clicks inside the active GTA window, `start`, `collect`, and `stop`. It
  cannot execute arbitrary command lines or arbitrary key strings.
- Deployment requires an x86 PE image, refuses to run while GTA/SA-MP is
  active, backs up the installed DLL, and verifies SHA-256 after installation.
- Windows Error Reporting writes full dumps for `gta_sa.exe` and `samp.exe`.

## Installation

From an elevated 64-bit PowerShell:

```powershell
.\Install-SampTestLab.ps1 `
  -Root 'C:\samp-test' `
  -GameDir 'C:\Program Files (x86)\Rockstar Games\GTA San Andreas' `
  -InteractiveUser 'DESKTOP-7PGINHC\defaultusr'
```

The installer registers the `SampTestInteractiveAgent` scheduled task with an
interactive-token logon. The task runs in the visible user's desktop session,
which is required for DirectX startup and screenshots.

## Common operations

From the Linux workspace, the passwordless wrapper uses
`~/.ssh/id_default` and `sshadmin@192.168.3.180` by default:

```bash
tools/windows/remote_lab/samp_lab.sh ping
tools/windows/remote_lab/samp_lab.sh screenshot-burst combat-m4 60 50
tools/windows/remote_lab/samp_lab.sh key ENTER language_english
tools/windows/remote_lab/samp_lab.sh key TAB scoreboard-hold
tools/windows/remote_lab/samp_lab.sh key F6 chat-edge
tools/windows/remote_lab/samp_lab.sh key F7 chat-mode-edge
tools/windows/remote_lab/samp_lab.sh key MENUTEST create-menu-golden
tools/windows/remote_lab/samp_lab.sh key TPASSWORD password-dialog-golden
tools/windows/remote_lab/samp_lab.sh key TPASSWORDVALUE password-dialog-type
tools/windows/remote_lab/samp_lab.sh key ACTORS actor_cycle
tools/windows/remote_lab/samp_lab.sh key RPC176RAW actor_position_raw
tools/windows/remote_lab/samp_lab.sh click 1176 674 spawn
tools/windows/remote_lab/samp_lab.sh validate build-win32/samp.dll
tools/windows/remote_lab/samp_lab.sh deploy build-win32/samp.dll local-build
tools/windows/remote_lab/samp_lab.sh start connect_spawn samp 192.168.3.181 7778 WinDebug
tools/windows/remote_lab/samp_lab.sh collect
tools/windows/remote_lab/samp_lab.sh stop
tools/windows/remote_lab/samp_lab.sh probe-profile actor-heavy
tools/windows/remote_lab/samp_lab.sh overlay-profile shadow
tools/windows/remote_lab/samp_lab.sh overlay-kill on
tools/windows/remote_lab/samp_lab.sh autopause-disable
tools/windows/remote_lab/samp_lab.sh favorite-port 3 192.168.3.181 7778 7798
tools/windows/remote_lab/samp_lab.sh favorite-endpoint 3 192.168.200.149 7798 192.168.3.181 7798
tools/windows/remote_lab/samp_lab.sh fetch-run RUN_ID /tmp/samp-runs
```

Override `SAMP_LAB_HOST` or `SAMP_LAB_KEY` when the machine address or key
changes. The wrapper never stores or accepts a password.

From Windows directly, use the commands below.

Validate a candidate without modifying the game directory:

```powershell
C:\samp-test\scripts\Deploy-SampDll.ps1 -ValidateOnly
```

Deploy `C:\samp-test\incoming\samp.dll`:

```powershell
C:\samp-test\scripts\Deploy-SampDll.ps1 -Label local-build
```

Verify the interactive agent:

```powershell
C:\samp-test\scripts\Submit-SampTestCommand.ps1 -Action ping
C:\samp-test\scripts\Submit-SampTestCommand.ps1 -Action screenshot -Label desktop
```

Start, collect, and stop a test:

```powershell
C:\samp-test\scripts\Submit-SampTestCommand.ps1 `
  -Action start `
  -Scenario connect_spawn `
  -Target samp `
  -ServerHost 192.168.3.181 `
  -ServerPort 7778 `
  -Nickname WinDebug
C:\samp-test\scripts\Submit-SampTestCommand.ps1 -Action collect
C:\samp-test\scripts\Submit-SampTestCommand.ps1 -Action stop
```

Each run records the installed `samp.dll` hash and the pre-run byte length of
every known log. Collection keeps both complete logs and `latest_log_bytes`, so
older `process_attach` blocks are not mistaken for the current run. Original
probe output is collected from the game root as `samp_probe.root.log`, because
`samp_probe.asi` writes next to itself rather than to `SAMPDLL_LOG_DIR`.

`screenshot-burst` captures all frames inside one interactive-agent command,
without one SSH/PowerShell round trip per frame. It accepts 1 through 120
frames and an interval of 25 through 10000 milliseconds. Every PNG has a
timestamp and frame index. During an active run, frames and `manifest.json`
are written under that run's `screenshot_bursts` directory; otherwise they
are written under `C:\samp-test\screenshots\bursts`. The completed command JSON
also contains the manifest path, per-frame timestamps, measured capture times,
paths, and hashes.

`TAB`, `F6`, and `F7` are fixed bounded actions, not a general key-injection
interface. The shell wrapper and both PowerShell parameter boundaries
allowlist them explicitly. `Send-SampTestInput.ps1` sends matching Win32
key-down/key-up events in a `try`/`finally`: TAB is held for 750 ms, while F6
and F7 are held for 100 ms. The target must be the single foreground GTA
window. These actions do not automate ESC or the GTA pause menu.

Module inventories use Toolhelp with both `TH32CS_SNAPMODULE` and
`TH32CS_SNAPMODULE32`; this lets the 64-bit PowerShell agent enumerate the
32-bit GTA process, including `samp.dll` and loaded ASIs.

The `ping` response also reports the configured GTA root, GTA/SA-MP/probe/
control hashes, active managed probe flag files, and the parsed
`III.VC.SA.WindowedMode.ini` auto-pause state. The same state and hashes are
persisted in the run manifest, allowing distributed runners to require
`[game] autoPause = 0` without changing the behavior of unrelated manual lab
starts.

`probe-profile` removes only the probe's fixed, known flag-file allowlist and
then enables the selected named profile. It refuses to change flags while a
GTA/SA-MP process is running; arbitrary flag names and arbitrary commands are
not accepted.

The `trailer-r5` probe profile enables only the timing-minimized original-R5
Packet-210 ring trace. The probe deliberately skips its normal Winsock/IAT and
unrelated code-hook sets in this profile.

The separate `vehicle-lifecycle` profile enables only the original-R5
`VehiclePool::New` and `CPlayerPed::PutDirectlyInVehicle` lifecycle ring
trace. It records bounded pre/post pool, GTA vehicle, driver, passenger-seat,
status, and flag snapshots without file I/O on either hooked thread. It also
skips the normal Winsock/IAT, render, trailer, and unrelated code-hook sets.

The `aim-bullet-jetpack` profile enables only the original-R5 aim-context,
remote key, shot/fire-dispatch, and jetpack-wrapper ring trace. Its eight
hooks are all-or-nothing, exact-R5/GTA-identity and entry/tail-byte guarded,
normalize the two guarded R5 HIGHLOW operands to the actual module base, and
write only bounded pre/post state into memory on the hooked thread. GTA
remains fixed-base guarded. The worker later emits the ped matrix, aim
buffers, weapon/task state, shot geometry, frame, thread, and caller RVA.

The `death-cleanup` profile enables only the original-R5 local Process,
Spawn, class-selection, GMX-reset, connection-loss, and `CNetGame` destructor
ring trace. Its six hooks are all-or-nothing and exact-R5/GTA-identity,
R5-relocation-normalized, fixed-GTA-base, entry-byte, and return-tail guarded.
Only the documented HIGHLOW operand in the Spawn entry is rebased; every
surrounding byte remains exact. Hook threads capture bounded local player,
ped/task, UI/camera, pool-count, representative entity, and
RemoveBuilding-counter snapshots; the worker performs the file logging.

The `pickup-r5` profile enables only the original-R5
`CPickupPool::PickedUp`/`CPickupPool::Process` ring trace plus the existing
bounded outgoing RakClient RPC observer for RPC 131/97. It records pickup
handles, raw GTA indices, notification timers, dropped/player metadata, types,
process cadence, and pre/post state without hook-thread file I/O.

The `ui-latches-r5` profile enables only the original-R5 chat-mode,
chat-open/close, scoreboard-show/hide, cursor-mode/restore, menu-query, and
remote-player Process ring trace. Its nine hooks are all-or-nothing and
exact-R5/GTA-identity, relocation-normalized for R5, fixed-GTA-base,
entry/tail, cursor-return, and AFK-transition-byte guarded. Hook threads never
inject input or write files.
TAB/chat/cursor calls capture bounded pre/post state, menu records are
edge-only, and remote AFK records use a bounded tracker with a one-second
heartbeat. The worker logs raw frontend/input-gate/cursor values and Win32
focus/capture observations; fields not directly proven by R5 static analysis
remain explicitly `TODO_VERIFY`.

`overlay-profile` selects only `bypass`, `shadow`, or `replace` for
`samp_re.asi` and refuses changes while GTA/SA-MP is running. The interactive
starter validates the managed profile again, sets the fixed
`SAMP_RE_FUNCTIONS=rpc175_set_actor_facing_angle,rpc178_set_actor_health`
tokens, and records the effective
mode, function token, overlay hash, and both kill-switch states in each run
manifest. If no managed profile exists, the starter explicitly uses `bypass`;
malformed profile state aborts the launch. `bypass` can be selected even when
the overlay is absent; active profiles require an installed `samp_re.asi`.

`overlay-kill on` creates only the fixed `samp_re_disabled.flag`. During an
active run this changes the installed overlay to permanent original-trampoline
passthrough for the rest of that process. `overlay-kill off` removes only that
managed flag and refuses to do so while GTA/SA-MP is running.

`favorite-port` changes only the little-endian port of one expected endpoint in
the interactive user's SA-MP R5 `USERDATA.DAT`. It refuses to run while a
GTA/SA-MP process exists, validates the header and declared endpoint count,
requires the old host and port to match, and creates a timestamped backup
before writing.

If the game directory is protected and its existing trace files were created
by an administrator, grant the configured interactive test user access only to
the fixed trace-file allowlist (`samp_runtime.log`, `samp_net_trace.log`,
`samp_hook_trace.log`, `samp_probe.log`, `reloop_control.log`, and
`samp_re.log`) before starting a traced run:

```powershell
C:\samp-test\scripts\Enable-SampTestLogging.ps1 -Root C:\samp-test
```

After changing those ACLs, `samp_lab.sh logcheck` appends one fixed diagnostic
marker to `samp_re.log` through the limited interactive agent. It does not
accept a path or arbitrary content.

`deploy-probe` and `deploy-overlay` accept only the fixed ASI names
`samp_probe.asi` and `samp_re.asi`. Deployment refuses while GTA/SA-MP is
running, validates x86 PE identity, backs up an existing target, stages via a
temporary file, verifies SHA-256 after install, and writes a deployment
manifest.

## Result layout

```text
C:\samp-test
|-- backups
|-- commands
|   |-- pending
|   |-- processing
|   |-- done
|   `-- failed
|-- deployments
|-- dumps
|-- incoming
|-- runs
|-- screenshots
|-- scripts
|-- state
`-- tools\sysinternals
```

WinDbg may remain an AppX application rather than a command on `PATH`.
`Install-Sysinternals.ps1` installs signed ProcDump binaries and adds their
directory to the machine `PATH`; all downloaded executables are checked with
Authenticode before use.
