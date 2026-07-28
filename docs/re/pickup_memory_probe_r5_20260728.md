# Original-R5 pickup memory probe — 2026-07-28

## Status

This document records a narrowly scoped `STATIC_037` pickup probe. The hook
implementation and byte guards are built and source-tested, but no new
original-R5 runtime trace has been collected yet. All field interpretations
that require a live run therefore remain `TODO_VERIFY`.

Reference binaries:

- SA-MP 0.3.7-R5 `samp.dll`
  SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- GTA-SA 1.0 US `gta_sa.exe`
  SHA256 `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`.

The source module is `tools/asi_probe/src/samp_probe_pickup.c`. It changes no
replacement behavior and is inactive unless the focused pickup profile is
selected.

## Static R5 findings

### Pool layout

`STATIC_037`, for the supported R5 binary:

| `CPickupPool` offset | Shape | Static use |
|---|---:|---|
| `+0x0000` | `DWORD` | pool count |
| `+0x0004` | `DWORD[4096]` | full GTA pickup handles |
| `+0x4004` | `DWORD[4096]` | raw GTA pickup indices |
| `+0x8004` | `DWORD[4096]` | notification/debounce counters |
| `+0xC004` | 3 bytes per slot | dropped flag followed by a 16-bit player ID |
| `+0xF004` | `0x14` bytes per slot | model, type, and three position floats |

The probe logs position values as raw bits so no hook-thread formatting or
floating-point environment changes are introduced. It samples at most eight
active or focused slots per event while still counting all nonzero handles.

### `CPickupPool::PickedUp`

`STATIC_037`: `samp.dll+0x00013440` is a `thiscall` method with one 32-bit
stack argument and returns with `ret 4`.

The method:

1. searches the `+0x4004` raw-index array for its argument;
2. rejects an absent slot, zero handle, nonzero timer, or dropped pickup;
3. writes the signed 32-bit SA-MP pool slot to a BitStream;
4. sends RPC 131 with priority value 1, reliability value 9, and channel 0;
5. writes `15` to that slot's `+0x8004` counter.

The numeric RakNet values correspond to
`HIGH_PRIORITY`/`RELIABLE_ORDERED` in the project's validated legacy RakNet
headers. The probe logs both numeric values so the runtime record does not
depend on an enum-name inference.

Guarded entry bytes at `+0x13440`:

```text
64 A1 00 00 00 00
```

The complete known return tail begins at `+0x13500`:

```text
8B 8C 24 20 01 00 00 5F 5E 64 89 0D 00 00 00 00
81 C4 24 01 00 00 C2 04 00
```

### `CPickupPool::Process`

`STATIC_037`: `samp.dll+0x00013520` is a no-argument `thiscall` method and
returns with plain `ret`.

For each active slot:

- an ordinary non-dropped pickup whose type is not 14 only decrements a
  positive notification counter;
- a dropped pickup uses GTA script condition `0x0214` and sends RPC 97 with
  the stored 16-bit player ID when collected;
- a non-dropped type-14 pickup uses the same GTA condition and sends RPC 131
  with the signed 32-bit SA-MP pool slot.

Both `Process` sends use priority value 1, reliability value 10, and channel
0, corresponding to `HIGH_PRIORITY`/`RELIABLE_SEQUENCED`. Thus R5 deliberately
uses a different reliability for ordinary `PickedUp` RPC 131 (value 9) and
type-14 `Process` RPC 131 (value 10).

The ordinary path does not call `0x0214` inside this method. This distinction
is important: visual collection/respawn is driven by the GTA pickup type,
while the R5 counter suppresses repeated server notification.

Guarded entry bytes at `+0x13520`:

```text
64 A1 00 00 00 00
```

The complete known return tail begins at `+0x13655`:

```text
8B 8C 24 2C 01 00 00 5F 5E 5D 5B 64 89 0D 00 00
00 00 81 C4 28 01 00 00 C3
```

### Processing cadence

`STATIC_037`: the caller at `samp.dll+0x00008C8E` compares the global counter
at `samp.dll+0x00118A10` with 5. It calls `CPickupPool::Process` only when the
counter is greater than 5 and then resets the counter. This predicts one
process call per seven caller invocations, not per rendered frame in every
configuration.

The probe records the raw gate value, GTA frame, process ordinal, elapsed
milliseconds, and frame delta. A live run is still needed to confirm the
caller cadence under the target frame limiter and pause states.

## Probe contract

The profile atomically preflights both method entries and both tails before
patching either method. It additionally requires exact PE identity proxies for
R5 and GTA-SA 1.0 US, with GTA loaded at its non-relocatable preferred base.
A partial install restores every owned patch.

The two method hooks call the original through fixed trampolines and publish
only bounded snapshots to a 256-record ring. The existing outgoing RakClient
vtable hook observes RPC 131 and RPC 97 after the original RPC call returns
and publishes into the same event sequence. No hook performs file I/O.

The worker emits:

- `pickup_r5`: event order, tick/frame/caller, cadence, RPC payload and QoS;
- `pickup_pool_r5`: pool count, active count, and bounded sample count;
- `pickup_slot_r5`: slot, handle, raw index, timer, dropped/player metadata,
  model/type, and position bits.

The outgoing RakClient hook remains process-bound. Do not hot-unload the ASI
while the game or network thread can execute an installed hook.

## Activation and first golden run

Build and deploy the ASI, stop GTA, then select:

```bash
tools/windows/remote_lab/samp_lab.sh probe-profile pickup-r5
```

The first comparable original-R5 battery should create separate fixtures for:

1. an ordinary pickup that is not immediately destroyed by the server;
2. a type-14 pickup;
3. a dropped weapon pickup tied to another player;
4. pause/unpause while standing inside an ordinary pickup;
5. pickup destruction and recreation using the same SA-MP pool slot.

For each fixture, retain the run ID, server log, `samp_probe.log`, original DLL
hash, FPS limit, and exact pickup model/type. The trace must answer:

- whether the raw `PickedUp` argument equals the low 16 bits of the full GTA
  handle for every tested handle generation;
- the observed frame/time spacing of the 15 process-tick debounce;
- whether timer assignment occurs even if the RPC call reports failure;
- whether the visual GTA pickup disappears independently from the SA-MP slot;
- whether type 14 and dropped pickups bypass the ordinary timer path exactly
  as predicted statically.

Prior runtime evidence in
`docs/traces/special_action_pickup_death_parity_20260726.md` observed repeated
ordinary-pickup callbacks at roughly 1.5-second intervals, but it did not
capture the R5 pool memory transitions. It therefore corroborates the visible
symptom only, not the new field-level claims.

## Replacement impact

`STATIC_037 + TODO_VERIFY`: the current replacement helper
`samp_raknet_client_send_pickup_notification` sends every RPC 131 using
`RELIABLE_SEQUENCED`. That matches the R5 type-14 `Process` path but not the
ordinary `CPickupPool::PickedUp` path, which uses `RELIABLE_ORDERED`.
Replacement behavior is intentionally unchanged by this probe-only change.
After the golden run confirms both outgoing values, the replacement should
preserve the call-source distinction rather than using one QoS for both
paths.

## Evidence boundary

- `STATIC_037`: RVAs, method ABI/tails, pool array offsets, branch structure,
  RPC IDs/payload widths/numeric QoS, timer value 15, and the `>5` caller gate.
- `OBSERVED_037`: prior ordinary-pickup callback repetition described in the
  linked 2026-07-26 trace.
- `TODO_VERIFY`: live values, handle-generation relationship, exact cadence
  under each FPS/pause state, RPC return behavior, and type-14/dropped pickup
  state transitions.
