# Windows incoming combat-sync parity, 2026-07-25

## Scope

Two clients used the same local open.mp server and
`filterscripts/sync_pair.pwn` fixture:

- Original SA-MP 0.3.7-R5 in the local reference Wine prefix as
  `SyncPilot`.
- Replacement `samp.dll` on native Windows as `SyncObserver`.
- Server: `192.168.3.181:7798`.
- Original DLL SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.

Only the reference Wine prefix was active locally. The Windows observer ran
in parallel.

## Packet discovery

Baseline run
`20260725_094231_incoming_combat_sync_baseline_1388188a` used original-pilot
on-foot rifle fire. The replacement already decoded packet 207
`PlayerSync`, but reported packet 203 and packet 206 as unknown.

The layouts were checked against open.mp commit
`f8058db80410b70f84c9089ec214530ca9784517`,
`Shared/NetCode/core.hpp`, `PlayerAimSync::write` and
`PlayerBulletSync::write`.

Evidence:

- Packet layout: `OPENMP_REF`.
- Packet occurrence and decoded values: `PROBE_TRACE`.
- Original remote GTA aim/fire/effect task behavior: `TODO_VERIFY`.

## Bounded decoders

Build SHA256
`6ef0834dd31efdfc190ce447fe341eda07cc6d8294de2987557f45dc36275051`
added bounded server-to-client decoding and snapshot rings for:

- packet 203 `AimSync`;
- packet 206 `BulletSync`.

Verification run
`20260725_094813_incoming_combat_decode_verify_27af3292` decoded 49
consecutive bullet events without a decode failure. Representative values
were:

- player `0`, weapon `31`, hit type `3`, hit ID `11`;
- origin approximately `(206.230, 1885.206, 18.371)`;
- hit approximately `(206.225, 1923.487, 18.270)`;
- offset approximately `(-0.573, -8.156, 1.819)`.

Aim samples used camera mode `4`, a normalized forward vector near
`(0.0000, 0.9988, -0.0500)`, and plausible camera positions near the pilot.
The runtime now names both packet IDs and preserves the tuples for later
remote-player processing.

That decoder build deliberately observed and traced these packets without
applying speculative GTA damage, muzzle, tracer, impact or aim tasks. The
later guarded aim-task experiment below supersedes only the aim-pose part;
matching the original `CRemotePlayer`/weapon call path remains `TODO_VERIFY`.

## Rustler behavior and lifecycle defect

The Rustler driver-fire route confirmed that vehicle primary fire is carried
by packet 200 keys (`0x0001`); it does not emit packet 206 or
`OnPlayerWeaponShot`.

A follow-up switched the native Windows observer to the original DLL and used
the local original client as pilot:

- Run: `20260725_100412_original_037_rustler_observer_visual_a9a49c69`.
- Observer DLL SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- Eight screenshots were captured while the pilot key remained held.
- Server samples from `10:07:50` through `10:08:04` continuously confirmed
  `keys=0x0001`, player state `2`, vehicle `25`.
- None of the eight original-observer frames showed a muzzle flash, tracer or
  projectile effect.

This is `OBSERVED_037 + PROBE_TRACE` for the exact stationary fixture:
replacement silence already matches the original observer. It does not prove
the same result for an airborne/moving Rustler or other armed vehicles.

The same route exposed a reproducible stream-out crash in the replacement.
Three fresh runs with the same build and scenario produced a dump:

1. `20260725_094813_incoming_combat_decode_verify_27af3292`;
2. `20260725_095323_incoming_rustler_lifecycle_retry2_ad645851`;
3. `20260725_095516_incoming_rustler_lifecycle_retry3_17cf5265`.

Each trace ended in the same order:

1. `vehicle: detach_remote_driver`;
2. `vehicle: destroy`;
3. access violation at GTA address `0x0047CB8D`, reading address `0x0000046C`.

This establishes the defect as `PROBE_TRACE` under the three-attempt policy.
Opcode 05CD did not complete the aircraft exit task before the vehicle was
deleted.

## Lifecycle fix and regression checks

Lifecycle-fix build SHA256
`3aedced34e2eb9934515c5dc2e85df3d57f04cbdeeebc956fde205b5f549a190`
removes a matching compatibility remote actor while the streamed vehicle is
still valid, then destroys the vehicle. The first following OnFoot or
VehicleSync packet bootstraps the actor again from retained scoreboard
metadata.

Run `20260725_095734_incoming_rustler_lifecycle_fix_verify1_b1ce0873`
showed:

1. remote actor GTA ID `257` seated in the Rustler;
2. actor `257` destroyed with reason `vehicle_streamout_driver`;
3. the Rustler destroyed;
4. OnFoot sync bootstrap;
5. replacement actor GTA ID `513` created;
6. no exception event, no dump, and both Windows processes responsive.

The same long-lived client then completed a normal-car route and a second
Rustler route. It remained responsive and produced no dump after either
stream-out.

The final rebuild tightened the decoder minimum lengths to the exact
34-byte AimSync and 43-byte BulletSync layouts. DLL SHA256
`83e247cb006a4408a6dd3d79595e2a5fd2d4ee0645f0ac840bd827ac8e56460f`
was installed and verified in the fresh run
`20260725_100209_incoming_combat_sync_final_smoke_fc96d705`. That run again
completed Rustler stream-out, recreated the remote actor from OnFoot sync,
left both Windows processes responsive and produced no dump.

Evidence classification for this fix is `PROBE_TRACE + TODO_VERIFY`: it is a
validated compatibility safety path, but the exact original 0.3.7 actor
lifecycle still needs a static or runtime call trace.

## Camera RPC 157/158 parity

The first corrected combat A/B exposed a camera defect rather than a combat
decoder defect: the replacement only applied RPC 157/158 before local spawn,
while the fixture sends a post-spawn observer camera.

Static R5 evidence for
SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`:

- RPC 157 handler: `samp.dll+0x19AA0`, 96-bit/12-byte position payload,
  wrapper at `samp.dll+0x9D780`;
- RPC 158 handler: `samp.dll+0x19B70`, 104-bit/13-byte position/type payload,
  wrapper at `samp.dll+0x9D7E0`;
- registrations: `samp.dll+0xE62C0` and `samp.dll+0xE62BC`;
- each wrapper immediately executes opcode 0925, clears the active scriptable
  camera source, then executes its own 015F or 0160 command;
- look-at type preserves only values 1 and 2; every other value becomes 2.

This is `STATIC_037`. The replacement now retains an ordered RPC157/158 event
ring, replays every retained event in arrival order, and clears its
attach/interpolation latches between 0925 and 015F/0160. Malformed payloads
are bounds checked rather than reproducing the original handler's unchecked
reads (`STATIC_037 + safety_divergence=original_unchecked + TODO_VERIFY`).

The corrected three-weapon A/B used:

- original: `20260725_122642_onfoot_original_reference_ce4e0c54`;
- replacement camera-fix:
  `20260725_125008_onfoot_replacement_camera_fix_85006f55`,
  DLL SHA256
  `2732a4f8b58a0b47a535a77f32966d044b50d5529d4f3ca758bda3bdeffc46f7`.

All pistol, M4 and sniper bursts show the same fixture framing. After
normalizing the different viewports (original 800x600, replacement
1280x720), the remote-player health-bar center is at 24.00% versus 23.91% of
viewport width, and the target vehicle is near 76% in both. Environment,
remote player and target vehicle remain visually aligned in all three
bursts. This supports camera/framing parity for this fixture
(`OBSERVED_037 + PROBE_TRACE`), not exact pixel parity.

The hardened build
SHA256 `617527f3ddce245119805d0dfbfbf64a01115bea7d0b7acf82374c6614932759`
passed a fresh Windows pistol smoke run
`20260725_130531_onfoot_camera_hardened_a3d100e0`.

The final ordering/reset build
SHA256 `3ce02ed8bef9fb7a9f729f1983ba7ba0b3f83a462b3abfc7c58dccdaa88e9876`
also:

- uses an explicit write cursor/count so camera history survives 32-bit
  sequence wrap;
- resets attach/interpolation consumer sequences across reconnect/GMX;
- defers the camera batch until after spawn finalization in the same graphics
  frame, preventing spawn camera opcodes from overwriting a later RPC157/158
  from the same network pump.

Run `20260725_131302_onfoot_camera_ordered_8a48db24` applied camera events
1/2 during class selection and post-spawn events 3/4 in exact `157 -> 158`
order. It produced no event gap, exception or dump; both Windows processes
were responsive at collection and the fixture framing remained correct.

## Remote on-foot combat visual diff

The corrected A/B establishes a real observer-side application gap:

- all 120 replacement frames (40 pistol, 40 M4, 40 sniper) show the remote
  player in the same arms-down idle silhouette, without a visible weapon;
- all 120 matching original frames show the expected weapon and aim stance:
  extended pistol arm, shouldered M4, and sniper aim pose;
- the capture windows contain at least 10 pistol, 26 M4 and 3 sniper shots in
  the server trace, so the result is not caused by missing the firing window;
- replacement traces contain the matching OnFoot weapon IDs 22/31/34,
  incoming AimSync 203 and BulletSync 206, with no decode failures.

Therefore packet ingress and decoding are working, while remote weapon/aim
application is not. The replacement currently emits only
`remote_aim: observe` and `remote_bullet: observe`; it has no successful
remote combat apply path. This is `OBSERVED_037 + PROBE_TRACE`.

No original burst resolved an unambiguous muzzle flash, so muzzle-flash
parity remains open even though the missing replacement weapon and aim pose
are conclusive.

## Guarded remote aim-task experiment

The replacement now has a deliberately bounded on-foot aim-pose bridge. It:

- applies the synchronized weapon before creating an aim task;
- accepts only spawned, on-foot compatibility actors with firearm IDs 22..34,
  valid AimSync and the on-foot target bit `0x0080`;
- derives a finite target 50 units along the normalized AimSync camera-front
  vector;
- leaves an occupied GTA secondary-attack slot untouched;
- allocates a 0x3c-byte `CTaskSimpleUseGun`, installs it as secondary attack
  slot 0, updates target position at task offset `+0x20`, and retains ownership
  only while the manager slot still points to that exact task;
- uses command `AIM` only. It does not intentionally fire, apply damage,
  synthesize BulletSync geometry, or claim muzzle/tracer/impact parity.

The target-only gate is intentional. Legacy 0.2x code maps SA-MP fire `0x0004`
and target `0x0080` to different GTA pad controls; turning fire-only hipfire
into an aim-only task would be a known semantic mismatch
(`ALT_02X_CODE + INFERRED + TODO_VERIFY`).

Direct GTA calls are restricted to the locally verified US 1.0 executable:

- GTA SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`;
- task pool allocate/free:
  `gta_sa.exe+0x21A5A0` / `gta_sa.exe+0x21A5B0`;
- `CTaskSimpleUseGun` ctor/dtor/control:
  `gta_sa.exe+0x21DE60`, `+0x21DF30`, `+0x21E040`;
- `MakeAbortable`: `gta_sa.exe+0x224E30`;
- `CTaskManager::SetTaskSecondary`: `gta_sa.exe+0x281B60`;
- `CTaskSimpleUseGun` vtable: `gta_sa.exe+0x46D724`, including the observed
  abort and `SetPedPosition` entries.

The final source guard checks the exact leading bytes of all seven functions
and the first nine vtable entries before any task-pool or thiscall operation.
A mismatch disables the path. The raw allocation failure path now frees an
unconstructed block without calling the destructor, and a temporarily invalid
ped/task-manager context retains ownership tracking instead of forgetting a
possibly live task. These signatures were independently read from the GTA
binary above (`GTA_REVERSED_REF`; runtime validation of the final guarded
build is still `TODO_VERIFY`).

## Aim-pose A/B result

The first runtime-tested aim-task build was:

- DLL SHA256:
  `9d9deef4486c952d5a3d9b425d0ac8e7744ecec353a557f40862135fa097607a`;
- Windows run:
  `20260725_134520_onfoot_remote_aim_task_77962a5e`;
- valid bursts:
  `20260725_134907_580_aim-task-valid-pistol`,
  `20260725_135116_606_aim-task-valid-m4`, and
  `20260725_135146_568_aim-task-valid-sniper`.

The pilot automation now spaces chat `WM_CHAR` messages by 40 ms. This was
required because original 0.3.7 consumed an unpaced `/syncpair pistol` as a
truncated command in slower runs.

The run produced four clean install/stop cycles (pistol twice, M4, sniper).
Every stop was `reason=aim_inactive`. There was no ownership loss,
abort/clear/install failure, exception or dump, and both Windows processes
remained responsive. Subsequent car and Rustler routes also stayed responsive,
but started only after the active aim task had already stopped; they are not
proof of active-task transition safety (`PROBE_TRACE`).

Visual evaluation against original run
`20260725_122642_onfoot_original_reference_ce4e0c54` shows:

- pistol: the extended one-hand aim stance is now close to the original;
- M4: the expected shouldered two-hand stance is present;
- sniper: the expected shoulder/long-gun stance is present;
- all 120 valid replacement frames show the appropriate weapon/aim pose,
  replacing the earlier 120/120 idle-pose failure.

The captures used different viewports and intervals (original 800x600 at
50 ms; replacement 1280x720 at 75 ms), so direct pixel/SSIM parity is not
valid. Actor-region diversity also exposes remaining differences:

| Weapon | Original unique actor regions | Replacement unique actor regions |
|---|---:|---:|
| Pistol | 40/40 | 40/40 |
| M4 | 25/40 | 2/40 |
| Sniper | 4/40 | 2/40 |

M4 therefore lacks much of the original subtle sway. Five replacement sniper
frames show a repeatable longer barrel/pose pop that has no equivalent in the
original burst. No burst from either DLL contains an unambiguous muzzle flash,
smoke, tracer, impact or recoil sequence. The result is consequently
`OBSERVED_037 + PROBE_TRACE` for coarse weapon/aim-pose parity only, not full
combat parity.

## R5 combat call-path evidence

Static analysis of original R5 SHA256
`b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
explains the remaining animation/effect gap:

- incoming OnFoot sync runs through `samp.dll+0xA740` to
  `CRemotePlayer` storage at `samp.dll+0x17260`;
- `CRemotePlayer::Process` at `samp.dll+0x166B0` calls remote
  `CPlayerPed::SetKeys` at `samp.dll+0xAF340`;
- the key mapper sends fire `0x0004` to GTA `CPad::ButtonCircle` and target
  `0x0080` to `CPad::RightShoulder1`;
- hook installation at `samp.dll+0xA62E0` replaces GTA vtable entries
  `0x86D190` and `0x86D744` with `samp.dll+0xA2960` and
  `samp.dll+0xA2DE0`;
- the first hook swaps remote pad, camera, aim, weapon-skill and current-player
  context around GTA `CPlayerPed::ProcessControl` at `0x60EA90`;
- the second performs the same context swap around
  `CTaskSimpleUseGun::SetPedPosition` at `0x624ED0`.

GTA's normal ProcessControl/task manager therefore owns original aim/fire task
lifecycle and its visible sway/recoil/audio timing. R5 does not primarily
drive firing by repeatedly issuing an isolated `CTaskSimpleUseGun` command.
The ProcessControl hook is not a simple one-call wrapper: it performs two
passes through `0x60EA90`. During the first pass it temporarily NOPs the
`0x5E92F4` call to `CPed::UpdatePosition` (`0x5E1B10`). For the second pass it
temporarily restores the instruction at `0x6884C4`/`0x688200`
(`D9 96 5C 05 00 00`), calls ProcessControl again, then returns those sites to
their NOP state. Reproducing this exact patch choreography is materially
riskier than a guarded single-pass context wrapper and requires its own
byte-validated experiment (`STATIC_037 + TODO_VERIFY`).

BulletSync is a second, separate layer. Packet 206 enters at
`samp.dll+0x9B40`, stores shot context through `samp.dll+0xAF280`, then calls
`samp.dll+0xAFA70`, which dispatches GTA `CWeapon::FireInstantHit` at
`0x73FB10` or the sniper path at `0x73AAC0`. R5 hooks installed from
`samp.dll+0xA7010` suppress autonomous inner remote hits while retaining the
outer GTA fire timing/task behavior; its LOS hook at `samp.dll+0xA5600`
substitutes synchronized hit geometry. More precisely, this remote execution
path does not use the packet's raw origin/hit-position vectors as direct
`FireInstantHit` arguments. `samp.dll+0x16370` stores all three vectors, but
the LOS hook consumes only the resolved target entity at shot-context `+0x28`
and target-relative offset at `+0x1C`. It transforms the offset into target
world space and extends the LOS endpoint to `2 * hitPoint - origin`; with no
resolved target it also suppresses an accidental hit on the local ped.
`samp.dll+0xAFA70` derives the actual muzzle/origin from the remote ped through
`samp.dll+0xAF9C0` before invoking GTA fire (`STATIC_037`).

This is `STATIC_037`. It establishes the next implementation direction:
guarded remote ProcessControl/context emulation for pose/recoil/audio, plus a
separately validated BulletSync trajectory/effect bridge. The current
aim-only task remains a useful compatibility fallback, not the final R5 path.

## Rustler same-observer repeat

The stationary Rustler comparison was repeated on the same native Windows
observer with 20 frames per DLL at a requested 75-ms interval:

- replacement burst:
  `20260725_135714_310_aim-task-regression-rustler-fire`;
- original run:
  `20260725_140036_rustler_original037_reference_95f1cce4`;
- original burst:
  `20260725_140220_736_original037-rustler-fire`.

Both clients showed the streamed Rustler and its movement without an exception
or dump. Neither 20-frame contact sheet resolved a muzzle flash or tracer.
This confirms stability and agrees with the earlier eight-frame stationary
reference, but the distant camera makes the effect test underpowered. It must
not be reported as general armed-vehicle fire parity (`OBSERVED_037 +
PROBE_TRACE + TODO_VERIFY`).

## Deterministic transition coverage

`sync_pair_client.py` can now keep RMB/LMB held while atomically queuing the
existing `test_cmds_request.txt` fixture:

- `--active-transition vehicle` asynchronously puts `SyncPilot` in a vehicle,
  targeting the `reason=vehicle_sync` cleanup path;
- `--active-transition streamout` changes the pilot virtual world,
  targeting the WorldPlayerRemove/`reason=remove` path;
- the held action window is at least five seconds even when screenshot capture
  is enabled, so the transition cannot silently occur after key release.

The same code audit found that graceful RakNet terminal packets skipped the
remote-player pool reset taken by connection loss/GMX. The partial terminal
cleanup now resets remote players explicitly, preventing a compatibility
actor or owned GTA aim task from surviving the transport
(`INFERRED + TODO_VERIFY`).

The byte-guarded build was subsequently exercised in native-Windows run
`20260725_161658_aim_guard_active_transitions_f395156e`. Active pistol aim was
interrupted by the automated vehicle transition and by an explicit player
stream-out; later M4 and sniper aim cycles also installed and stopped cleanly.
The observer stayed responsive, no exception/dump or ingress decode failure
was recorded, and the weapon/aim pose remained visible before each
transition. This closes the previously untested automated vehicle/stream-out
items as `PROBE_TRACE`; weapon change, death, GMX and connection-loss
transitions remain open.

## Open points

- First reproduce a byte-guarded, single-pass remote
  pad/camera/aim/skills/current-player context around GTA ProcessControl and
  UseGun `SetPedPosition`, with the current aim-only task retained as fallback.
  Only after an original/replacement transition trace matches should the exact
  two-pass/NOP choreography be attempted. Do not call original SA-MP wrappers
  on the raw compatibility actor.
- Reproduce the original BulletSync instant-hit/LOS path separately, with
  bounds-checked synchronized geometry and without guessed damage semantics.
- Run active-aim transitions for weapon change, death, GMX, graceful
  disconnect and connection loss. Vehicle and streamout are now runtime
  covered; the other fixture triggers still need to be added.
- Repeat original/replacement pistol, M4 and sniper at identical resolution,
  camera distance, synchronized single shots and at most 16-ms capture
  intervals. M4 sway and the sniper barrel pop remain measurable differences.
- Add a targeted GMX/reconnect trace for the first post-reset attach and
  interpolate camera event. The stale-sequence bug is fixed structurally but
  has not yet been exercised by a dedicated runtime fixture.
- Repeat the original/replacement visual burst with an airborne/moving
  Rustler and other armed vehicles. The stationary Rustler reference showed
  no observer-visible gun effect despite continuous fire keys.
- Compare aircraft stream-out against an original-DLL actor/vehicle teardown
  trace; the current destroy-and-bootstrap path is stable but not yet proven
  instruction-equivalent.
- Investigate the separate fixture teardown/world-placement issue in which
  the replacement observer fell below the map after target-vehicle cleanup.
- Strict PE ABI parity is still open: the replacement has nine sections,
  different imports, TLS and `.eh_frame`, while the reference has five
  sections.
