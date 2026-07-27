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
- `GTA_REVERSED_REF + ALT_02X_CODE + TODO_VERIFY`: vehicle surfing uses
  `CPed::m_standingOnEntity` at offset `+0x568`, requires an occupied SA-MP
  vehicle within five units, and sends ped-minus-vehicle offsets.
- Runtime counters, first/error traces and session/GMX reset paths were added
  for the new packet state.

## Deliberately open

- `TODO_VERIFY`: reproduce R5's complete surfing collision query, including
  object surfing and its sticky transition behavior. The present implementation
  covers only the conservative vehicle-contact subset.
- `TODO_VERIFY`: implement the no-player-passenger nearest-player authority
  branch and confirm the exact unoccupied cadence. The present cadence reuses
  the negotiated in-car interval.
- `TODO_VERIFY`: incoming/remote application of packets 209 and 210 was not
  added by this sender-focused change.
- `TODO_VERIFY`: the current vehicle-slot convention treats trailer ID zero as
  "none"; verify whether a server vehicle in slot zero can be a trailer in the
  original client.
- `TODO_VERIFY`: run original/replacement two-client A/B scenarios for passenger
  entry, driverless push, towing, spectator camera motion, surf transitions,
  disconnect and GMX.
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
- Coordinated Win32 build passed; final candidate SHA256
  `acb5edd84e5c634309d50cb68213dffd9d575ccb59fae454c66242df4977168b`.
- Host regression passed 12/12 tests. A live original/replacement two-client
  A/B for these edge states is still required.
