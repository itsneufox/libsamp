# Original-R5 aim, bullet, and jetpack memory probe

Date: 2026-07-28

Status: `STATIC_037` + `OBSERVED_037` + `PROBE_TRACE`; the guarded original-R5
profile has run successfully, and one replacement angle regression has been
captured. Fine-grained visual and task parity remains `TODO_VERIFY`.

## Scope

This focused profile passively records the original client's aim-context,
remote-key, shot-dispatch, weapon/task, and jetpack transitions. It is meant
to distinguish packet parity from the GTA-side state changes that produce
visible looking direction, muzzle flash, firing, impact, hit, animation, and
jetpack behavior.

It does not inject input, synthesize a shot, alter a task, or write a log from
a hooked thread. Each wrapper calls the original routine through a trampoline
and publishes a bounded pre/post record to the existing worker.

## Binary identities and relocation policy

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

Both PE identity proxies must match. For R5 that includes i386, the
preferred-image-base header, relocations-not-stripped, and a non-empty base
relocation directory. GTA has relocations stripped and must remain at its
fixed preferred base because snapshots read its fixed addresses. R5 may be
loader-relocated, as observed on the native Windows test machine. The
preflight normalizes only these statically confirmed HIGHLOW operands:

| Relocation RVA | Guarded instruction | Preferred operand | Meaning |
| --- | --- | --- | --- |
| `+0x9C964` | entry at `+0x9C960`, operand offset 4 | `0x101039C8` | `samp.dll+0x1039C8` aim-context global |
| `+0xACD4B` | tail at `+0xACD49`, operand offset 2 | `0x10113978` | `samp.dll+0x113978` jetpack-related global |

For an observed load base of `0x03F80000`, the required operands are
`0x040839C8` and `0x04093978`. Opcodes, RVAs, all other bytes, decoded patch
lengths, and all non-relocated tails remain exact. The relocated entry bytes
are copied into the generic hook's expected buffer only after validation, so
the resulting trampoline replays the loader-adjusted absolute instruction.

`objdump -p artifacts/binaries/samp_installer.dll` confirms HIGHLOW entries at
`+0x9C964` and `+0xACD4B`. The GTA constant `0x008705C4` in the jetpack query
success tail has no R5 PE relocation and is deliberately not rebased.

## Hook set

All eight hooks and every tail guard must pass before the first byte is
changed:

| RVA | Static role | ABI |
| --- | --- | --- |
| `+0x9C9C0` | install one remote 0x30-byte aim context | `stdcall(player_index)`, `ret 4` |
| `+0x9C960` | restore the saved local aim context | `cdecl()`, `ret` |
| `+0xAF340` | map remote sync keys into GTA pad state | `thiscall`, three stack arguments, `ret 0x0C` |
| `+0xAF280` | store the internal shot context | `thiscall`, one stack argument, `ret 4` or local tail jump |
| `+0xAFA70` | dispatch the remote GTA fire path | `thiscall`, integer return |
| `+0xACD10` | start jetpack | `thiscall`, void return |
| `+0xACD60` | stop jetpack | `thiscall`, void return |
| `+0xACDC0` | query jetpack mode | `thiscall`, integer return |

Entry spans contain complete instructions and no relative call or branch.
`+0x9C960` contains the one normalized absolute operand described above.
Preflight also validates both shot-context exits, both jetpack-query exits,
and the known epilogue of every other hook. Installation is all-or-nothing.
A partial install is restored in reverse order. Shutdown restores only a
current `E9`/NOP patch owned by this profile, using the exact saved bytes.
Trampoline storage remains process-lifetime memory.

## Bounded capture

Hook threads publish to a fixed 512-record ring and do no file I/O. The worker
emits:

- `aim_bullet_jetpack_r5`: event, tick, GTA frame, thread, caller and hook RVA,
  arguments, target, and original return value;
- `aim_bullet_jetpack_state_r5`: ped/entity/matrix, basis, weapon slot/state,
  and eleven raw task-root pointers before and after the call;
- `aim_bullet_jetpack_aim_r5`: active and per-player aim-context bytes plus
  bounded shot input/context bytes.

Packet 206 and Packet 207 are call-chain context only in this first profile;
their large packet handlers are not patched. Names inferred from static call
graphs or GTA layouts remain `STATIC_037` / `GTA_REVERSED_REF` /
`TODO_VERIFY`.

## Captured original-R5 evidence

The controlled native-Windows observer run is retained at:

```text
artifacts/runs/20260728-aim-r5-memory-observer/
```

The focused log is:

```text
windows/20260728_132302_aim_r5_memory_observer_a46fb663/logs/samp_probe.log
```

Its SHA256 is
`93a9f49e5b749a6ecdc6a29b2ded29115f3d16922fd322626c42b1abe40574ad`.
The manifest identifies the original R5 and GTA binaries listed above. All
eight guarded hooks installed; the run contains no partial-install condition.

`OBSERVED_037` + `PROBE_TRACE`:

- 17,120 `aim_install` events and 17,120 matching `aim_restore` events were
  captured.
- 29 remote shots each produced one `shot_context` and one `fire_remote`
  event. Every captured shot followed the ordered scope
  `shot_context -> aim_install -> GTA fire -> aim_restore -> return`.
- The fire wrapper installed the remote aim context at R5 `+0xAFAFA` and
  restored it at `+0xAFC52`. The Packet 206 call sites remained
  `+0x1658D` for shot-context storage and `+0x16598` for fire dispatch.
- Reconstructing the 0x30-byte camera basis from the trace produced a maximum
  component error of approximately `1.77e-7`. For front vector
  `(x, y, z)`, `h = sqrt(x*x + y*y)` and the observed up vector is
  `(-x*z/h, -y*z/h, h)`, with the guarded near-vertical fallback handled by
  the replacement helper.
- The probed BulletSync target resolution produced GTA entity targets for
  player and vehicle hits. Object/player-object hit records did not resolve
  to a GTA target in the captured original path; this is evidence for the
  original target dispatch, not evidence that object impacts are visually
  complete.
- The fire path did not consume the observed remote wrapper's ammunition or
  clip fields. It also dispatched the GTA fire routine for a captured sniper
  state with clip value zero. Remote ammo mutation must therefore not be
  inferred merely from a visible shot.
- Jetpack start and stop each occurred once. The query reads the intelligence
  task at offset `+0x10` and recognizes vtable `0x008705C4`. Start became
  visible to the query on the following frame in this run; stop cleared the
  query immediately. This is one captured timing sequence, not a universal
  scheduling guarantee.

## Corrected remote aim context model

`STATIC_037`:

- The remote ped path at R5 `+0xA2960` scopes GTA pad state, camera mode,
  camera mode 2, camera zoom, camera aspect, the 0x30-byte aim context,
  eleven weapon-skill values, and the current-player byte around one call to
  GTA `CPlayerPed::ProcessControl` at `0x60EA90`.
- The camera scalar helpers are R5 `+0x9C7C0` / `+0x9C850`; the aim helpers
  are `+0x9C940` / `+0x9C9C0`.
- `AimSync.aspect_ratio` is installed as
  `1.0f + aspect_byte / 255.0f`.

The ProcessControl body performs one GTA ProcessControl call. Earlier working
notes that described a two-pass ProcessControl sequence were incorrect and are
superseded by this static audit. The temporary GTA instruction suppression in
the R5 wrapper is separate choreography around that single call; it is not a
second ProcessControl pass.

There is also a separate `STATIC_037` path which the replacement does not yet
implement: GTA's `CTaskSimpleUseGun::SetPedPosition` vtable slot at
`0x0086D744` is redirected to R5 `+0xA2DE0` instead of the GTA original
`0x624ED0`. That wrapper repeats the remote pad/camera/aim/skill/current-player
scope around `SetPedPosition`. It can run after the ProcessControl scope has
already been restored, so it remains a plausible source of frame-edge or
weapon-specific pose differences even though the current coarse screenshot
regression is visually aligned.

## Replacement angle regression

The post-aspect replacement run is retained at:

```text
artifacts/runs/20260728-140456-distributed-sync-angles-1511727/
```

The installed replacement SHA256 was
`7881a4c810573d235ac3b227347963c257ffe246e91a03efd45cc4b3087a53d1`.
Its runtime trace recorded an incoming aspect byte of 198 and installed
`1.776471`, matching `1.0 + 198 / 255` within the logged precision. The same
samples had aim key `0x0080`, camera mode 53, and both `aim_valid=1` and
`aim_built=1`. This is `PROBE_TRACE` evidence for the replacement's installed
state; it does not by itself prove original parity.

Manual comparison of the baseline/left/right screenshots against
`artifacts/runs/20260728-angles-r5-original/` shows the same coarse aim pose
and the same left-to-right progression. This closes the previously reported
gross left/right inversion for that deterministic route at a visual
regression level. It is not a pixel-parity claim: the runner's machine verdict
remains `TRACE_CAPTURED_VISUAL_UNVERIFIED`, the three samples are not a
frame-locked image-diff oracle, and subtle bone/task/camera differences remain
possible. The replacement nameplate size/vertical placement still differs in
these images and is tracked as a separate rendering gap.

## Enablement

Environment:

```text
SAMP_PROBE_AIM_BULLET_JETPACK_HOOKS=1
```

Flag next to `samp_probe.asi`:

```text
samp_probe_aim_bullet_jetpack_hooks.flag
```

Managed Windows profile:

```bash
tools/windows/remote_lab/samp_lab.sh probe-profile aim-bullet-jetpack
```

The focused profile skips normal Winsock/IAT, render, trailer, and unrelated
code-hook sets.

## Remaining runtime matrix

The captured run covered ordinary remote aim, pistol/M4/sniper shot dispatch,
and one jetpack start/stop sequence. The remaining controlled matrix is:

1. frame-locked aim comparison at several pitch/yaw extremes, including the
   near-vertical basis fallback;
2. weapon switch, reload, crouch, enter/exit vehicle, and death boundaries,
   while correlating `SetPedPosition` and the GTA task tree;
3. single shots and held fire into ground, wall, vehicle, remote ped, and
   object, with GTA muzzle/impact/effect counters captured before and after;
4. jetpack idle, directional flight, fire while flying, landing, death, and
   reconnect;
5. the same scenarios at the preferred R5 base and a relocated native-Windows
   base where possible.

Comparisons must retain caller RVAs, matrix/basis vectors, aim buffers, target
entity, weapon/task changes, and visible muzzle/impact behavior. Screenshot
inspection alone is insufficient for task or effect parity.

## Open points

- `TODO_VERIFY`: implement and guard the separate R5
  `CTaskSimpleUseGun::SetPedPosition` context wrapper, then determine whether
  it changes frame-edge, pitch, reload, crouch, or weapon-specific pose parity.
- `TODO_VERIFY`: reproduce and test the remaining remote weapon-skill and
  temporary-instruction scope from R5 ProcessControl without assuming a
  second ProcessControl pass.
- `TODO_VERIFY`: exact GTA task and weapon-state edges responsible for remote
  muzzle flash and each visible impact type.
- `TODO_VERIFY`: relationship between shot-context storage, fire dispatch,
  damage handling, and local-only effects.
- `TODO_VERIFY`: complete jetpack task/animation lifecycle beyond the one
  observed start/query/stop transition.
- `TODO_VERIFY`: whether any relevant packet path bypasses one of the eight
  guarded functions.
- `TODO_VERIFY`: quantify the independent nameplate geometry gap; do not fold
  it into aim-sync conclusions.
