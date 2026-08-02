# R5 edge-state sync: passenger, unoccupied, trailer, spectator, surfing

Date: 2026-07-27

Reference binary:

- File: `artifacts/binaries/samp_installer.dll`
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- Image base: `0x10000000`
- Evidence: `STATIC_037`

The focused Ghidra exporter is
`tools/ghidra/InspectSyncEdgeStates.java`. Its local, generated metadata is in
`analysis/generated/ghidra_sync_edge_states_20260727/` (that directory is
intentionally gitignored). The export contains bounded instructions,
references, scalars, function identities and selected raw constants; it does
not contain decompiler pseudocode.

## Static observations

| Behavior | R5 evidence | Conclusion |
| --- | --- | --- |
| Surf-state update | `samp.dll+0x3730` | R5 performs a collision-driven surfing update. It is more extensive than the legacy standing-contact path. |
| Unoccupied sender | `samp.dll+0x4D30`; packet byte at `+0x4E7F`; payload length at `+0x4E89`; send at `+0x4EA6` | Packet 209, packed 67-byte payload, `HIGH_PRIORITY`, `UNRELIABLE_SEQUENCED`, ordering channel 1. |
| Trailer sender | `samp.dll+0x53D0`; 500-ms compare at `+0x54C6`; packet byte at `+0x5513`; payload length at `+0x551D`; send at `+0x5539` | Packet 210, packed 54-byte payload, `HIGH_PRIORITY`, `UNRELIABLE_SEQUENCED`, ordering channel 1. An identical 54-byte state is suppressed for at most 500 ms. |
| Passenger sender | `samp.dll+0x5590`; packet byte at `+0x574C`; payload length at `+0x5756`; send at `+0x577E` | Packet 211, packed 24-byte payload, `HIGH_PRIORITY`, `UNRELIABLE_SEQUENCED`, ordering channel 1. |
| Spectator processing | `samp.dll+0x6540`; camera matrix call at `+0x6599`; packet byte at `+0x6628`; payload length at `+0x6632`; send at `+0x6659` | Packet 212, packed 18-byte payload every more than 200 ms, `HIGH_PRIORITY`, `UNRELIABLE`, ordering channel 1. Position is the camera matrix position. |
| Unoccupied authority | `samp.dll+0x6E00`; calls to sender at `+0x6F15` and `+0x6FB3`; float at `samp.dll+0xE5908` is 90.0 | R5 checks all eight passenger pointers. The first network-player passenger owns the send; with no player passenger, a nearest-player arbitration path is bounded to 90 units. |
| Trailer dispatch | in-car sender `samp.dll+0x7080`; trailer call at `+0x744D` | Trailer sync follows the towing-vehicle sync path when it carries a trailer ID. |
| Unoccupied receive | dispatcher `samp.dll+0xB260`; handler `+0x9A40`; store/apply `+0x158D0` | Packet 209 is player ID plus the raw 67-byte payload. R5 validates its axes, position and speeds, then uses 0.1 no-op, 6/6/3 snap and `delta*0.06` correction thresholds. |
| Trailer receive | dispatcher `samp.dll+0xB260`; handler `+0x9E20`; store/apply `+0x15C90` | Packet 210 is player ID plus the raw 54-byte payload. R5 resolves the remote player's current towing wrapper independently of the cached Packet-200 trailer ID, accepts the nine trailer models or Towtruck model 525, then uses 0.5 no-op, 6/6/3 snap and `delta*0.025` correction thresholds. |
| Passenger receive | dispatcher `samp.dll+0xB260`; handler `+0x9D30`; store `+0x17440` | Packet 211 is player ID plus the raw 24-byte payload. R5 commits passenger state even when its vehicle wrapper cannot yet be resolved. |
| Camera backing matrix | copy helper `samp.dll+0x9D460`; constructor literal at `samp.dll+0x9FFAE` contains `0xB6F99C` | The R5 camera wrapper points at GTA SA 1.0 US camera matrix storage; the spectator payload uses matrix position at offset `+0x30`. |

The Ghidra function report identifies exact entries for `+0x3730`, `+0x4D30`,
`+0x53D0`, `+0x6540`, `+0x6E00`, `+0x7080` and `+0x9D460`. Ghidra did not
create a function at the requested constructor address `+0x9FF60`; the raw
bytes at `+0x9FFAE` nevertheless directly contain the matrix-pointer store.
Passenger send arguments were additionally checked against the original
instructions at `+0x5770..+0x577E`; a refreshed Ghidra export including that
function remains a tooling TODO because the current host only exposes a JRE,
not the JDK required to compile the changed script.

The ordering-channel result differs from the 0.2x source, which passes channel
zero. The R5 instructions push channel 1 for all four edge-state packet sends,
so the R5 observation wins.

## Wire layouts

`UnoccupiedSync` is packed to 67 bytes:

| Offset | Field |
| ---: | --- |
| 0 | `uint16 vehicle_id` |
| 2 | `uint8 seat_id` |
| 3 | `float roll[3]` |
| 15 | `float rotation[3]` |
| 27 | `float position[3]` |
| 39 | `float move_speed[3]` |
| 51 | `float turn_speed[3]` |
| 63 | `float vehicle_health` |

`TrailerSync` is packed to 54 bytes:

| Offset | Field |
| ---: | --- |
| 0 | `uint16 vehicle_id` |
| 2 | `float position[3]` |
| 14 | `float quaternion[4]` in wire order `w,x,y,z` |
| 30 | `float move_speed[3]` |
| 42 | `float turn_speed[3]` |

The adapter has `sizeof` and `offsetof` assertions for these ABI-relevant
layouts.

## Implemented compatibility behavior

- `STATIC_037`: packet 209 and 210 serialization, priority, reliability and
  ordering channel now match R5.
- `STATIC_037`: passenger and spectator ordering channel was corrected from
  zero to one.
- `STATIC_037`: attached trailers are resolved from the vehicle-slot attachment
  state, included in vehicle sync and sent after successful towing-vehicle
  sync. Identical trailer payloads use the observed 500-ms suppression window.
- `STATIC_037 + GTA_REVERSED_REF`: live entity matrices are converted to the
  full trailer quaternion; a normalized yaw-only value remains a defensive
  fallback.
- `STATIC_037 + ALT_02X_CODE`: spectator sync reads the GTA camera matrix
  position instead of the watched ped/vehicle position.
- `STATIC_037 + INFERRED`: unoccupied sync is sent only when the local player is
  the first network-player passenger, the driver is absent, the vehicle is
  moving and the vehicle is not a train. This is deliberately narrower than
  R5's full authority algorithm.
- `STATIC_037`: inbound packets 209/210/211 are decoded with their exact
  70/57/27-byte server layouts and appended to the runtime snapshot.
- `STATIC_037`: the shared runtime ordering ring now preserves the
  `Receive()` arrival order across packets 207, 200, 209, 210 and 211.
  Packets 207/200 use channel 0 and 209/210/211 use channel 1; replaying fixed
  per-type batches can therefore produce a different final state than RakNet
  delivered across the two channels.
- `STATIC_037`: UnoccupiedSync copies the two transmitted matrix axes exactly:
  matrix `+0x00` to/from `roll`, matrix `+0x10` to/from `rotation`, while the
  matrix `+0x20` axis and flags remain untouched.
- `STATIC_037`: inbound unoccupied and trailer transforms use R5's observed
  no-op, correction and snap thresholds. Trailer quaternion order is
  `w,x,y,z`. Packet 210 uses the SA-MP vehicle-wrapper matrix setter at
  `samp.dll+0x9EBC0`; that R5 setter only copies the 0x40-byte matrix and does
  not call GTA `CEntity::UpdateRwFrame` or an extra `ApplyMoveSpeed`.
- `STATIC_037 + ALT_02X_CODE`: PassengerSync caches state before vehicle
  resolution, uses seats 1 through 8 without evicting an occupant, and performs
  physical seating as a best-effort GTA operation.
- `STATIC_037 + ALT_02X_CODE`: driver/trailer transitions check the live GTA
  trailer pointer at `CVehicle+1224`, attach a changed trailer and detach the
  previous trailer when packet 200 reports none.
- `STATIC_037`: Packet 210 publishes the owner/towing-slot attachment only
  after the live `CVehicle+1224` pointer matches the expected trailer. A
  command failure or mismatching/unreadable pointer remains deferred for a
  later sync update instead of being reported as applied.
- `STATIC_037`: Packet 210 no longer depends on a previously cached matching
  Packet-200 trailer ID or an already-seated remote ped. Packet 209 records
  its sender before wrapper resolution and skips physics correction when
  `samp.dll+0xB7CF0` resolves a live tractor via `CVehicle+1220`.
- `STATIC_037`: Packet 209 reproduces the narrower `samp.dll+0xB70E0`
  occupied-transition check instead of rejecting every non-null GTA driver:
  correction is skipped only when driver `+0x46C` bit 8 is set while
  driver `+0x598` is null.
- `GTA_REVERSED_REF + ALT_02X_CODE + TODO_VERIFY`: vehicle surfing uses
  `CPed::m_standingOnEntity` at offset `+0x568`, requires an occupied SA-MP
  vehicle within five units, and sends ped-minus-vehicle offsets.
- Runtime counters, first/error traces and session/GMX reset paths were added
  for the new packet state.

## Runtime evidence: original sender to replacement receiver

`OBSERVED_037 + PROBE_TRACE`:

- Artifact:
  `artifacts/runs/20260727-193437-sync-edge-all-881592`
- Original R5 pilot:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- Replacement observer:
  `3f6bce2f8c55b16778e4d528591554f3e9ded4f8c6517a17f74a3dd9acca15f1`
- The server verified Passenger as vehicle 25/seat 1/state 3, Unoccupied as
  vehicle 25/seat 1/state 3, and Trailer as vehicle 25/driver seat/state 2
  with trailer 26 actually attached.
- The replacement decoded packets 211, 209 and 210 and consumed all three
  packet types through the shared movement ring. Passenger readback reported
  `seated=1 seat_read=1`; Unoccupied correction reported successful movement,
  turn-speed and GTA transform readback; Trailer reported
  `attached=1 readback=1`.
- All three scenario drivers returned zero, no client crash marker was
  captured, and all ASI hashes remained unchanged. The clients were terminated
  by the harness and did not emit `process_detach`, so this is not evidence of
  graceful shutdown.
- The resulting verdict is `TRACE_PASS_VISUAL_UNVERIFIED`. It closes the
  original-outbound to replacement-inbound decode/application contract only.
  It does not establish pixel-identical passenger placement, matching
  interpolation, articulated trailer motion, replacement-outbound parity, or
  an original-observer readback.

Packet 209 arrived once before the passenger setup had settled and was
deferred; later seat-1 updates applied successfully. Consequently this run
does not prove exact first-packet seat-field or authority timing. The original
prefix also used an older, functional control-ASI build than the current
replacement prefix, so the run does not claim control-helper binary identity.

## Deliberately open

- `TODO_VERIFY`: reproduce R5's complete surfing collision query, including
  object surfing and its sticky transition behavior. The present implementation
  covers only the conservative vehicle-contact subset.
- `TODO_VERIFY`: implement the no-player-passenger nearest-player authority
  branch and confirm the exact unoccupied cadence. The present cadence reuses
  the negotiated in-car interval.
- `TODO_VERIFY`: capture paired original-observer/replacement-observer visuals
  for all three inbound paths. Passenger seating, driverless correction and
  articulated trailer motion now have replacement GTA readback evidence, but
  visual and original-observer parity remain open.
- `TODO_VERIFY`: the current vehicle-slot convention treats trailer ID zero as
  "none"; verify whether a server vehicle in slot zero can be a trailer in the
  original client.
- `TODO_VERIFY`: run the reverse direction (replacement pilot to original
  observer), then extend the two-client matrix to spectator camera motion,
  surf transitions, disconnect and GMX.
- GTA SA addresses used here target the 1.0 US executable. Record the exact GTA
  executable hash and RVAs in a future runtime trace before treating those
  engine addresses as independently observed evidence.

## Checks completed

- Focused Ghidra headless analysis completed successfully for the reference
  DLL and produced identity/function/instruction/reference/scalar metadata.
- Reference SHA256 in the Ghidra identity export matches the binary above.
- Original instruction bytes were checked for IDs 209--212, payload sizes,
  send arguments, trailer resend suppression, unoccupied call sites and camera
  matrix copy.
- Coordinated RakNet Win32 build passed and the live-tested candidate SHA256 is
  `3f6bce2f8c55b16778e4d528591554f3e9ded4f8c6517a17f74a3dd9acca15f1`.
- Host regression passed 13/13 tests. The new raw edge-sync test covers exact
  209/210/211 sentinel payloads, truncation, accepted trailing bytes,
  timestamp normalization, flags, snapshot contents, all-five ordering and
  128-entry ring wrap/reset.
- ReLoop unit regression passed 28/28 tests, including deterministic UDP loss,
  reordering and edge-runner evidence cases.
- The no-RakNet host regression passed 7/7 tests and the no-RakNet Win32 DLL
  compiled successfully.
- The original-sender/replacement-observer live trace above passed all three
  edge states. Reverse-direction, original-observer and visual A/B evidence
  remain required.
