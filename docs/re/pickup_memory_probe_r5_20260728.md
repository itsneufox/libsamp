# Original-R5 pickup memory probe — 2026-07-28

## Status

This document records a narrowly scoped pickup probe. Its ordinary type-1 path
is now `OBSERVED_037 + PROBE_TRACE`; the type-14 and dropped branches remain
`STATIC_037 + TODO_VERIFY`.

Reference binaries:

- SA-MP 0.3.7-R5 `samp.dll`
  SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- GTA-SA 1.0 US `gta_sa.exe`
  SHA256 `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`.

The pool hook source module is `tools/asi_probe/src/samp_probe_pickup.c`; its
RakClient observation hook is integrated in `samp_probe_asi.c`. Both remain
inactive unless the focused pickup profile is selected.

### Original-R5 golden result — 2026-08-02

The first prepared run,
`20260802-112137-distributed-sync-pickup-41774`, collected the server-side
pickup event but correctly ended as analyzer `MISMATCH`: the probe had hooked
RakClient vtable slot 26, the extended RPC overload, so it observed no nested
outgoing RPC.

Direct analysis of the supported R5 DLL then established that the call at
`samp.dll+0x134DE` uses vtable slot 25, whose exact target is
`samp.dll+0x34620` and whose ABI is the short six-argument BitStream overload.
Slot 26 instead targets `samp.dll+0x345B0` and is the extended overload. The
probe now guards both slot 25 and the exact `+0x34620` target. Corrected ASI
SHA256:
`d87fc3c7d91297dc87e1a38c8ec02e5dc4637f256d60a1f638d1c4dadecd7ca9`.

The identical repeat run,
`20260802-112802-distributed-sync-pickup-57189`, was assessed
`OBSERVED_ORDINARY`:

- both pickup hooks installed with the exact R5/GTA identities;
- one ordinary slot-0 pickup, model 1240/type 1, used GTA handle generation 2
  and raw index 0;
- `PickedUp` sent RPC 131 with a signed 32-bit slot payload, priority 1,
  reliability 9, channel 0, and successful return;
- the notification timer changed from 0 to 15;
- 160 `Process` calls followed the predicted seven-frame gate cadence;
- the bounded ring reported no overflow, orphan RPC, or parse error.

The fixture destroyed the ordinary pickup immediately after the server
callback. It therefore did not cover the complete 15-tick countdown,
type 14, a dropped pickup, pause behavior, RPC failure, or slot recreation.

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
milliseconds, and frame delta. The ordinary golden run observed all 160 calls
at the predicted seven-frame spacing (approximately 125 to 141 ms in that
fixture). Pause/unpause and other frame-limit configurations remain
`TODO_VERIFY`.

## Probe contract

The profile atomically preflights both method entries and both tails before
patching either method. It additionally requires exact PE identity proxies for
R5 and GTA-SA 1.0 US, with GTA loaded at its non-relocatable preferred base.
A partial install restores every owned patch.

The two method hooks call the original through fixed trampolines and publish
only bounded snapshots to a 256-record ring. The outgoing RakClient vtable
hook observes RPC 131 and RPC 97 through guarded slot 25
(`samp.dll+0x34620`) after the original short-overload call returns and
publishes into the same event sequence. No hook performs file I/O.

The worker emits:

- `pickup_r5`: event order, tick/frame/caller, cadence, RPC payload and QoS;
- `pickup_pool_r5`: pool count, active count, and bounded sample count;
- `pickup_slot_r5`: slot, handle, raw index, timer, dropped/player metadata,
  model/type, and position bits.

The outgoing RakClient hook remains process-bound. Do not hot-unload the ASI
while the game or network thread can execute an installed hook.

## Activation and remaining golden runs

Build and deploy the ASI, stop GTA, then select:

```bash
tools/windows/remote_lab/samp_lab.sh probe-profile pickup-r5
```

The ordinary type-1 fixture is complete. The remaining comparable
original-R5 battery should create separate fixtures for:

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

`STATIC_037 + OBSERVED_037 + PROBE_TRACE`: the replacement now preserves the
RPC 131 call-source distinction. Its ordinary GTA collection hook sends
`RELIABLE_ORDERED` (numeric 9); the stored type-14 `Process` path sends
`RELIABLE_SEQUENCED` (numeric 10). When the GTA collection hook is installed,
generic processing no longer polls ordinary pickups through opcode `0x0214`.

The replacement retains its prior wall-clock notification guards as a safety
measure. They are not presented as original parity: the ordinary R5 path uses
a 15-Process-call counter and the type-14 branch statically leaves that timer
unchanged. Type-14 runtime behavior remains `TODO_VERIFY` before removing or
retuning those guards.

## Evidence boundary

- `STATIC_037`: RVAs, method ABI/tails, pool array offsets, branch structure,
  RPC IDs/payload widths/numeric QoS, timer value 15, and the `>5` caller gate.
- `OBSERVED_037 + PROBE_TRACE`: the ordinary type-1 payload/QoS, successful
  RPC result, `0->15` timer transition, handle/raw-index relationship for
  generation 2/index 0, and seven-frame Process cadence in run
  `20260802-112802-distributed-sync-pickup-57189`.
- `TODO_VERIFY`: the complete 15-tick countdown under each FPS/pause state,
  RPC-failure timer behavior, additional handle generations, and type-14 or
  dropped-pickup state transitions.
