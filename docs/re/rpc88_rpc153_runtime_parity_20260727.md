# RPC 88 / RPC 153 runtime parity notes — 2026-07-27

## Evidence scope

Reference DLL:

- SA-MP 0.3.7-R5 `samp.dll`
- SHA256
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`

The statements tagged `STATIC_037` below were checked against that binary.
Existing runtime evidence is called out separately. No post-change runtime run
yet proves delayed local jetpack task creation or a live RPC 153 remote skin
transition.

## RPC 88: SetPlayerSpecialAction

### Original R5 path

`STATIC_037`: `samp.dll+0x18690` reads one action byte and dispatches it to the
local-player special-action method at `samp.dll+0x30F0`. RPC 88 does not carry a
player ID; remote special actions arrive through player sync.

For jetpack action 2, the relevant CPlayerPed paths are:

- `samp.dll+0xACD10`: `StartJetpack`
- `samp.dll+0xACD60`: `StopJetpack`
- `samp.dll+0xACDC0`: `IsInJetpackMode`

`STATIC_037`: `StartJetpack` requires a live GTA ped and performs this sequence:

1. It writes the CPlayerPed GTA player-slot byte through the selector pointer
   stored at `samp.dll+0x113978`.
2. It reads the current position from the ped matrix at offsets
   `+0x30/+0x34/+0x38`.
3. It calls `samp.dll+0x9F040`, whose normal entity path dispatches GTA
   `SetPosition` through the entity vtable at `+0x38`.
4. It invokes GTA `CCheat::JetpackCheat` at `0x439600` exactly once.
5. It resets the selected GTA player slot to zero.

`STATIC_037`: the wrapper does not immediately read the task slot after
`0x439600`. Jetpack task creation is therefore asynchronous from the wrapper's
point of view; successful dispatch is not equivalent to an immediately visible
task.

`STATIC_037`: `StopJetpack` and `IsInJetpackMode` first reject the task path
while `CPed+0x46C` contains the in-vehicle bit `0x100`. Otherwise they resolve
`CPed+0x47C`, inspect the task pointer at `+0x10`, and require task vtable
`0x8705C4`. `StopJetpack` calls GTA scalar destructor `0x6801D0` with deleting
flag 1 and then clears the `+0x10` task pointer. `StartJetpack` itself has no
equivalent in-vehicle test in the inspected wrapper.

### Replacement implementation

`STATIC_037`:

- The adapter decodes the one-byte RPC payload into
  `special_action` plus `special_action_seq`.
- `gta_ped_start_jetpack_compat` mirrors the selector, current-position,
  vtable-`+0x38`, GTA `0x439600`, and selector-reset sequence.
- Start now reports dispatch success without requiring an immediate jetpack
  task readback.
- Task detection and stop use `CPed+0x47C -> +0x10`, vtable `0x8705C4`, the
  in-vehicle guard, destructor `0x6801D0`, and explicit slot clearing.
- Local RPC 88 action 2 uses GTA player index zero. Remote sync action 2 is
  applied only to the GTA-player-backed remote route, which has a real GTA
  player index.

`OBSERVED_037 + PROBE_TRACE`: an original client sends on-foot
`special_action=2`, and an earlier replacement observer visibly instantiated
the remote jetpack.

### Deliberately open

- `PROBE_TRACE + TODO_VERIFY`: before the asynchronous-dispatch correction, a
  replacement local client logged `special_action=jetpack start_failed=1`,
  stayed visually without a jetpack, and sent special action 0. A fresh
  original/replacement run must now prove that the task appears on a later GTA
  tick and that outgoing on-foot sync changes to action 2.
- `TODO_VERIFY`: flight controls, vertical velocity, landing, removal, death,
  vehicle-entry, GMX, and observer interpolation still need paired runtime
  coverage.
- `TODO_VERIFY`: RPC 88 currently exposes only the latest action and sequence,
  not an event ring. Multiple action transitions arriving between two
  game-thread snapshot reads can collapse.
- `STATIC_037 + TODO_VERIFY`: R5's dispatcher handles an action-byte table up to
  `0x44`. The replacement implements a conservative subset. Unknown or custom
  action IDs remain diagnostic-only instead of receiving guessed behavior.
- `TODO_VERIFY`: the actor-based remote fallback is not a CPlayerPed and does
  not receive jetpack creation. Only the GTA-player-backed route has the
  selector semantics observed in R5.

## RPC 153: SetPlayerSkin

### Original R5 path

`STATIC_037`: `samp.dll+0x19190` reads:

```text
uint32 player_id
int32  skin
```

The handler validates the skin, compares the target against the local SA-MP
player ID, and resolves one of two CPlayerPed paths:

- local: local-player state followed by its CPlayerPed pointer at `+0x104`;
- remote: an existing remote slot, its active-state guard, then the CPlayerPed
  pointer at remote offset `+0x1DD`.

If no corresponding CPlayerPed exists, the handler returns without applying a
model. The static remote-ID check uses a 16-bit target comparison against 1004.

`STATIC_037`: both local and remote targets call
`CPlayerPed::SetModelIndex` at `samp.dll+0xAFF50`. That wrapper:

1. validates the CPlayerPed and requested model;
2. applies the original lazy `CClothes::RebuildPlayer` guard at `0x5A82C0`;
3. stops the follow-task path at `samp.dll+0xAE020`;
4. calls the base model-change path at `samp.dll+0x9EF50`;
5. reinitializes ped audio through GTA `0x4E68D0`.

### Replacement implementation

`STATIC_037 + PROBE_TRACE`:

- The adapter validates the eight-byte payload, a replacement player target
  below 1000, and normal ped skins `0..311` excluding 74.
- Local RPC 153 requests/loads the model, applies opcode `09C7` to GTA player
  index zero, and resets the local ped audio attributes.
- An active and spawned GTA-player-backed remote is now handled through its
  owned GTA player index and opcode `09C7`.
- Before remote mutation, the runtime verifies the SA-MP slot ID, GTA slot
  owner, slot range `2..209`, pool-ped identity, exact CPlayerPed vtable, and a
  readable PlayerInfo. On success it updates the compatibility slot's skin and
  resets that ped's audio attributes.
- A missing/non-streamed remote follows R5's no-CPlayerPed outcome and is
  ignored.

### Deliberately open

- `STATIC_037 + TODO_VERIFY`: the actor fallback is not the CPlayerPed path
  resolved by R5 at `samp.dll+0x19190`. It is logged and left unchanged rather
  than being destroyed/recreated or directly patched without evidence.
- `TODO_VERIFY`: RPC 153 also stores only the latest value and sequence. It
  needs an event ring if multiple skin changes within one game-thread snapshot
  interval must all be observable.
- `STATIC_037 + TODO_VERIFY`: R5 compares remote IDs against 1004, while the
  replacement pool currently stops at 1000. Reserved/custom targets
  `1000..1003` remain unsupported until their original purpose and layout are
  confirmed.
- `STATIC_037`: custom SA-MP object model IDs are not valid player skins. The
  accepted skin domain remains `0..311` excluding 74.
- `TODO_VERIFY`: a paired two-client run must exercise local and active remote
  skin changes, repeated changes, vehicle occupancy, death/respawn, stream-out,
  reconnect, and GMX cleanup before runtime parity is claimed.

## Current parity status

- RPC 88 wire decoding and the R5 jetpack dispatch sequence are implemented.
  Delayed task appearance and the full flight lifecycle remain runtime-open.
- RPC 153 local behavior and the guarded GTA-player-backed remote path are
  implemented. Actor fallback, burst-event preservation, and R5-only remote
  IDs remain intentionally open.
