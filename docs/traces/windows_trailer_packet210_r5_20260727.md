# Windows trailer Packet 210 parity, 2026-07-27

## Topology

The stable comparison topology is:

- one original-R5 pilot in the single active host Wine/Lutris prefix;
- one native-Windows observer;
- original `samp.dll` and replacement `samp.dll` are deployed to the Windows
  observer in separate, otherwise comparable runs.

Two simultaneous host prefixes are not a supported test topology because they
interfere with focus/window scheduling and have produced unstable runs.

Reference identities:

- original R5 SHA256
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- GTA SA US 1.0 SHA256
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`.

## Comparable runs

### Original golden

`OBSERVED_037 + PROBE_TRACE`

Run:

`artifacts/runs/20260727-213058-windows-sync-edge-trailer-1001101`

The focused R5 probe captured 376 complete Packet 210 applications:

- `noop`: 354;
- `correct`: 22;
- `snap`: 0;
- residual median: `0.300 m`;
- residual p95: `0.563 m`;
- residual maximum: `0.989 m`;
- mean cadence: `27.94 Hz`.

The first Packet 210 target was approximately
`(205.988, 1894.459, 18.226)`. The live trailer was already at
`(205.954, 1894.468, 18.259)`, only about `0.048 m` away.

### Bad replacement baseline

`PROBE_TRACE`

Run:

`artifacts/runs/20260727-214215-windows-sync-edge-trailer-1012402`

This run recorded 99 hard snaps and a maximum residual of `8.788 m`. RakNet
link state, packet order and cadence were healthy, while the tractor generally
remained within roughly `0.3 m`. The failure was therefore local replacement
playback/physics rather than transport loss.

### Quaternion-corrected replacement

`PROBE_TRACE`

Run:

`artifacts/runs/20260727-221340-windows-sync-edge-trailer-1069028`

Replacement SHA256:

`6080acffd529cb9b05547a9ffb809a45a0f65910f7b350f4529245574cb68203`

Results:

- complete matrix/quaternion readback stayed at `basis_dot=1.000000`;
- hard snaps fell from 99 to 2;
- snap at Packet 210 sequence 137: residual `5.886 m`;
- snap at sequence 444: residual `6.896 m`;
- sequence 448 recovered to a residual of about `0.177 m`;
- no crash or transport/reassembly fault was observed.

This is a material improvement but not original parity. In particular, the
first Packet 210 already found the local replacement trailer about `1.259 m`
too high:

- target Z: approximately `18.238`;
- live Z: `19.497`.

The tractor and trailer were queued and created in the expected pair order and
RPC 148 attach succeeded before the first Packet 200/210. The remaining first
frame error therefore arises after create/attach and before Packet 210
correction. At sequence 128 the replacement residual was about `2.328 m`,
versus `0.330 m` in the original. The tractor itself remained comparatively
stable.

## GTA tow-link static result

`STATIC_037 + GTA_REVERSED_REF`

GTA opcode `0893` was followed from its handler-table entry through the
`0x4720BB` case:

- parameter 1 resolves to the trailer;
- parameter 2 resolves to the tractor;
- the handler invokes the trailer vtable slot `+0xF4` with the tractor and
  boolean argument `true`;
- `CTrailer` vtable slot `+0xF4` resolves to
  `gta_sa.exe+0x2CFDF0`, `CTrailer::SetTowLink`.

The replacement's existing opcode call therefore has the correct argument
order and explicitly takes the repositioning branch:

`trailer->SetTowLink(tractor, true)`.

This confirms that original RPC 148 and the replacement both select the same
true/`PlaceOnRoadProperly` branch; a wrong replacement boolean does not explain
the `+1.259 m` Z error. The remaining key difference is timing. In the bad
replacement trace, delayed attach replay, the first Packet 200 and the first
Packet 210 all ran in one runtime iteration before the trailer's first
`ProcessControl`. The original fixture leaves about 250 ms between StreamIn
and RPC 148 and then reaches Packet 210 on a later network/game tick.

A bounded opt-in probe now records the SetTowLink entry/return and the first
64 direct `CTrailer::ProcessControl` frames. It distinguishes an attach-time
position jump from stale Packet 210 replay before the first tow physics frame,
without changing gameplay. Both hooks are installed only after exact GTA US
1.0 identity and entry/tail-byte preflight. A dedicated gateway relocates the
relative call in the ProcessControl prologue. The debug ASI built successfully
at `build-asi-probe-trailer-physics/samp_probe.asi`; the local verification
build SHA256 was
`ffa90f692d7abc69213939888feaf287d304f1a70d0ebb5287047078d1d7154c`.

## Current interpretation

`STATIC_037 + PROBE_TRACE`

The Packet 210 deadband, correction and snap algorithm should not be loosened:
its observed thresholds and writes match R5. The complete quaternion path is
also no longer the primary suspect.

`INFERRED + TODO_VERIFY`

The remaining divergence is most likely in remote-driver prediction and/or
the GTA tow-link constraint state:

1. The replacement previously cached Packet 200 steering without advancing
   the remote GTA `CPad` once per driver frame. This can make tractor prediction
   disagree with the pilot between packets and destabilize the attached
   trailer.
2. The replacement trailer is already vertically wrong immediately after
   RPC 148. Original and replacement must be compared directly around GTA
   `CTrailer::SetTowLink` (`gta_sa.exe+0x2CFDF0`) and the first
   `CTrailer::ProcessControl` frames (`gta_sa.exe+0x2CED20`).

The replacement's deferred vehicle creation now retains a dependent RPC 148
at the vehicle-event cursor. It creates no more than one globally oldest
vehicle through the normal hold/100-ms gate, retries the same attach event,
and advances the cursor only once both dependencies are active. This removes
the previous unsafe path that could synchronously drain a large pending pool
or consume the attach before its trailer existed. It is a crash-safety bridge
and remains `TODO_VERIFY` against the synchronous R5 construction timing.

The first run with the new `trailer-r5` profile will record, before and after
`SetTowLink` and for the first 64 trailer frames:

- tractor `CVehicle+0x4C8` and trailer `CVehicle+0x4C4` associations;
- both complete matrices and positions;
- move and turn speeds;
- `SetTowLink` arguments/result;
- the trailer state around Packet 210 sequences 128..137.

The shared movement consumer also previously advanced its cursor after a
runtime `DEFER`. This permanently lost an early Packet 200/209/210 when its
GTA vehicle did not yet exist. The current implementation retains the head,
does not advance the packet-specific cursor, and retries it after creation.
Packet 200 now waits for both its towing vehicle and advertised trailer;
Packet 210 waits for live pool, tow-link, position, quaternion and speed
dependencies. A 2000-ms safety bound and ring-gap trace prevent a permanent
global head-of-line stall. This is `PROBE_TRACE + INFERRED` and still needs the
distributed Windows verdict.

## Pending distributed verdict

The current replacement build adds per-frame R5 driver controls, exact
one-byte horn state, exact live siren-bit handling, RPC 164 creation-order
replay with retained dependent events, and exact constructor dirt/door-lock
fields. Attach and Packet 210 diagnostics now include each GTA vehicle's local
activation age so the replay collapse can be measured directly. Its SHA256 is:

`ded014d1775e116dade95f75460d43bef591e4b0ca34f2f1c130fece1d951736`

It built successfully, host tests pass `14/14`, and the same deployed hash
passed the single-prefix Vehicle regression 4/4 without a crash in
`artifacts/runs/20260727-231629-replacement-vehicle-1142907`. The native
Windows host remained unreachable with `No route to host`, so neither this DLL
nor the new physics probe has a distributed trailer verdict yet. This is an
infrastructure limitation, not a parity pass.
