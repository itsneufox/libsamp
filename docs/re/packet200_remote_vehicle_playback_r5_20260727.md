# Packet 200 remote-vehicle playback (R5)

Reference binary:

- `artifacts/binaries/samp_installer.dll`
- SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- PE image base `0x10000000`

## Static result

`STATIC_037` was taken from the existing full Ghidra R5 analysis and
cross-checked against direct instruction windows.

| R5 RVA | Role |
| --- | --- |
| `samp.dll+0xAA10` | Packet 200 handler |
| `samp.dll+0x17340` | Store 63-byte driver sync, mark fresh state |
| `samp.dll+0x168E7` | Fresh normal-driver branch |
| `samp.dll+0x155E0` | Cache target quaternion/position/speed and set exact move speed |
| `samp.dll+0x15140` | Position deadband/correction/snap |
| `samp.dll+0x16E8E` | Every-frame normal-driver branch |
| `samp.dll+0x15460` | Turn clamp and full-attitude feedback |
| `samp.dll+0xAF340` | Copy Packet 200 keys/LR/UD into the remote GTA `CPad` |
| `samp.dll+0xAE270` | Mirror the remote horn key to live `CVehicle+0x514` |
| `samp.dll+0xB7540` | Replace live siren bit `CVehicle+0x42D` bit 7 |
| `samp.dll+0x9EBC0` | Full matrix field copy; no `UpdateRwFrame` |
| `samp.dll+0x9ED10` | Direct CPhysical move-speed setter |
| `samp.dll+0x9EE60` | Direct CPhysical turn-speed setter |
| `samp.dll+0xB5480` | `D3DXQuaternionSlerp` wrapper |
| `samp.dll+0xB5500` | `D3DXQuaternionNormalize` wrapper |

The normal-driver algorithm is:

1. Normalize and retain the complete `w,x,y,z` target quaternion, target
   position and target move speed.
2. Set the exact target move speed.
3. Position deadband is `0.05` on every axis.
4. Snap at `abs(X/Y error) > 8.0`. The Z limit is `0.5`, or `2.0` for
   helicopter, boat and plane subtypes.
5. Otherwise add `position_error * 0.06` to each target-speed component whose
   axis error exceeds `0.05`. Write the corrected vector only if at least one
   resulting component exceeds `0.01` in magnitude.
6. Every frame, clamp every turn-speed component to `[-0.02, +0.02]`, Slerp
   current complete attitude toward the retained target with `t=0.75`,
   normalize it, and write all three matrix axes while retaining position.
7. After the optional attitude call, every normal-driver frame loads Packet
   200 UD/LR/keys from remote-player offsets `+0x1D/+0x1B/+0x1F` and calls
   `CPlayerPed::SetKeys` at `samp.dll+0xAF340`. Train models skip the attitude
   call but still take this key path. It is separate from the on-foot key
   cache at `+0xC5/+0xC7/+0xC9`.
8. Immediately afterwards, the call at `samp.dll+0x16FA7` reaches
   `samp.dll+0xAE270` and writes exactly one horn byte:
   `CVehicle+0x514 = (CPad key index 18 != 0)`.
9. Fresh Packet 200 playback calls `samp.dll+0xB7540` from
   `samp.dll+0x16A1E`. It preserves `CVehicle+0x42D` bits 0..6 and replaces
   bit 7 with the wire siren bit.

`CPlayerPed::SetKeys` suppresses Packet key bit 4 only when the live ped is on
foot with an actual `CTaskSimpleJetPack` in `CPed+0x47C/+0x10`. The packet
SpecialAction byte is not sufficient evidence for that decision.

Packet playback does **not** call `CPhysical::ApplyMoveSpeed`, GTA yaw opcode
`0175`, or `CEntity::UpdateRwFrame`. The optional vehicle ProcessControl
context hook represents the separate R5 path at `samp.dll+0xA3100`.

## Replacement status

`reimpl/src/runtime_bridge.c` now implements the normal-driver behavior above.
Passenger and on-foot updates invalidate the retained driver target. Live
driver-pointer, pool, matrix, vtable and finite-value checks guard every raw GTA
access.

The retained driver controls are advanced once per remote-driver frame, after
the attitude feedback in the same order as R5 and before the class-specific
vehicle `ProcessControl` context consumes the resulting state. This fixes a
previously confirmed replacement divergence where a received steering input
such as `keys=0x0008, LR=-128` was retained in the logical slot but GTA physics
continued with an old or zero `CPad`. Construction no longer advances a fresh
driver or passenger control state a second time before its first frame.

The replacement also applies the exact live siren bit and one-byte horn latch.
An older inferred RPC 164 path incorrectly treated `CVehicle+0x514` as a
32-bit alternate siren field. That write has been removed. RPC 164's
`addSiren` byte is a constructor capability retained by R5 on its wrapper
(`samp.dll+0xB84AA..+0xB84C5`), not the Packet 200 live siren state; the
remaining constructor-capability path is explicitly deferred.

Packet 200 now participates in the shared Packet 207/200/209/210/211
arrival-order cursor with an explicit `APPLIED`/`DEFER`/`DROP` result. A
pending towing vehicle or advertised trailer retains the movement head until
both GTA objects and the live tow-link readback exist. Pool, transform and
opcode-0893 failures are retried rather than being marked consumed. The retry
is bounded to 2000 ms, below the approximate 2.1-second capacity of the
128-entry ring for a normal combined Packet 200/210 stream; an exhausted or
overwritten head is explicitly logged and dropped so it cannot deadlock all
remote players.

Train models 449, 537 and 538 are intentionally excluded from the normal
per-frame attitude path. R5 uses its separate `samp.dll+0x15650` train routine;
the replacement currently keeps a conservative direct position/speed fallback
and records this as `TODO_VERIFY`.

## Checks

- Host quaternion test covers normalization, R5 `t=0.75` Slerp, and the
  equivalent `q`/`-q` shortest path.
- Host tests pass `14/14`, including the pure shared-cursor
  applied/deferred/retry/timeout/gap/sequence-wrap test.
- Win32 DLL build succeeds; current tested-at-build artifact SHA256 is
  `ded014d1775e116dade95f75460d43bef591e4b0ca34f2f1c130fece1d951736`.
- The same hash was deployed to the single replacement prefix. Vehicle
  create/enter/spawn-callback/respawn passed 4/4 without a crash in
  `artifacts/runs/20260727-231629-replacement-vehicle-1142907`; the runner
  still warns that forced shutdown did not expose `process_detach`.
- A comparable live trailer run remains required with the current topology:
  original R5 pilot in the single host prefix and native-Windows replacement
  observer, retaining Packet 200 target/delta/mode and frame attitude markers.
  The Windows host was unreachable (`No route to host`) at the end of this
  build, so this hash has not yet received a distributed trailer verdict.
