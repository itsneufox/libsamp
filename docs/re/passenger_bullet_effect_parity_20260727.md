# Passenger and remote BulletSync parity, 2026-07-27

## Reference builds

- Original SA-MP 0.3.7-R5 `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- GTA San Andreas 1.0 US `gta_sa.exe` SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`.

Claims below tagged `STATIC_037` come from static analysis of that exact R5
DLL. The replacement behavior added here still needs a paired visual/runtime
run and is therefore not `OBSERVED_037`.

## Passenger entry and sync

`STATIC_037`:

- `CLocalPlayer::Process` at `samp.dll+0x74C0` reaches passenger entry at
  `samp.dll+0x6FE0`.
- It consumes GTA control index 8 on the first pressed frame, selects the
  closest streamed vehicle and rejects a distance greater than or equal to
  4.0 units.
- Entry uses the passenger form of `CPlayerPed::EnterVehicle`; the underlying
  GTA script command is `05CA` with timeout 3000 and seat `-1`.
- It immediately emits RPC 26 through `samp.dll+0x5AD0`, with a 16-bit vehicle
  ID and passenger byte 1, `HIGH_PRIORITY`, `RELIABLE_SEQUENCED`, channel 0.
- `samp.dll+0x5590` emits packet 211 plus a packed 24-byte PassengerSync
  payload. Its send at `samp.dll+0x577E` is `HIGH_PRIORITY`,
  `UNRELIABLE_SEQUENCED`, ordering channel 1. This later bounded instruction
  read supersedes the 0.2x source and the initial channel-0 interpretation.
- Passenger flags store seat in bits 0..5, drive-by in bit 6 and cuffed state
  in bit 7. The following byte stores weapon in bits 0..5 and the additional
  key in bits 6..7.
- An identical 24-byte payload is suppressed until more than 500 ms elapsed.
- Exit RPC 154 at `samp.dll+0x5BF0` writes only the 16-bit vehicle ID and uses
  `HIGH_PRIORITY`, `RELIABLE_SEQUENCED`, channel 0.

The replacement now implements this G-entry and PassengerSync path. Drive-by,
cuffed and additional-key states remain zero instead of being guessed.
RPC 154 is sent after an observed seated-to-on-foot transition; its exact
original notification point is `TODO_VERIFY`.

## Remote BulletSync effects

`STATIC_037`:

- Packet 206 enters at `samp.dll+0x9B40`, stores shot context through
  `samp.dll+0xAF280`, then dispatches from `samp.dll+0xAFA70`.
- Weapon 34 calls GTA `CWeapon::FireSniper` at `0x73AAC0`. Other accepted
  instant-hit weapons call `CWeapon::FireInstantHit` at `0x73FB10` with
  muzzle effects enabled.
- `samp.dll+0xAF9C0` uses ped bone 24. `samp.dll+0xACAC0` resolves
  `CWeaponInfo::GetWeaponInfo(weapon, skill=1)` and its fire offset at `+0x24`.
  The shot origin receives `fireOffset.z + 0.15`.
- R5 patches only three GTA `CWorld::ProcessLineOfSight` call sites. For the
  USA 1.0 executable their RVAs and original bytes are:

| GTA RVA | Original bytes |
|---|---|
| `0x00340721` | `E8 DA B2 E2 FF` |
| `0x00340B69` | `E8 92 AE E2 FF` |
| `0x00336247` | `E8 B4 57 E3 FF` |

`samp.dll+0xA5600` transforms the synchronized entity-local offset through the
target matrix and substitutes `2 * targetWorld - start` as the LOS endpoint.
For an unresolved target it suppresses an incidental hit on the local ped or
the local occupied vehicle.

The replacement now reproduces that bounded path on the GTA game thread. All
GTA entry signatures and all three call-site bytes must match before it is
enabled. Installation is all-site validated, restores already-owned sites on
partial failure, never replaces a newly observed foreign hook, and uses
guarded saved-byte restoration. It can be disabled with
`SAMPDLL_REMOTE_BULLET_EFFECTS=0`.

## Verification status and open points

- `git diff --check`: passed for the touched implementation files.
- GTA call-site bytes: verified against the reference executable above.
- Integrated Win32 compile: passed; final coordinated candidate SHA256
  `acb5edd84e5c634309d50cb68213dffd9d575ccb59fae454c66242df4977168b`.
- Replacement PassengerSync seating now has a focused original-sender runtime
  trace and GTA seat readback in
  `docs/re/sync_edge_states_r5_20260727.md`; paired original-observer visuals
  and BulletSync visual runs remain pending.
- `TODO_VERIFY`: exact RPC 154 timing; passenger drive-by/cuffed/additional-key
  sources; player-object hit target resolution; untyped/world-hit trajectory;
  remote ProcessControl timing around recoil/sway/audio.
- TrailerSync and conservative UnoccupiedSync senders were implemented in the
  subsequent focused pass documented in
  `docs/re/sync_edge_states_r5_20260727.md`.
