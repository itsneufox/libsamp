# Windows vehicle-entry and key-sync parity, 2026-07-24

## Scope

Native-Windows A/B run against the same local open.mp server and
`filterscripts/sync_pair.pwn` fixture. No Wine or Proton client was used.

- Server: `192.168.3.181:7798`
- Windows client: `192.168.3.180`
- Nickname/role: `SyncPilot`
- Reference `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`

Evidence classification: `OBSERVED_037 + PROBE_TRACE`.

## Vehicle-entry A/B

Reference run:

- Run ID: `20260724_150419_windows_original_solo_sync_b65448bf`
- Action: `/syncpair rustler`
- Result: `state=2`, `vehicle=25`
- Stable sample position: approximately
  `(206.006, 1885.122, 18.368)`

Pre-fix replacement run:

- DLL SHA256:
  `335e5c5e453cd553034c1af07173602c2a980de14db4372b2e20b64f372d2340`
- Run ID: `20260724_150624_windows_replacement_solo_sync_bca17715`
- Action: `/syncpair rustler`
- Result: remained `state=1`, `vehicle=0`
- Stable sample position: approximately
  `(202.684, 1887.101, 17.648)`, beside the Rustler

The replacement trace showed vehicle creation and RPC 70
`PutPlayerInVehicle` being applied before the pending `SetPlayerPos` reached
the GTA entity. The later position application ejected the already-seated
ped. The compatibility fix defers only that local put event until the
corresponding player-position sequence has been applied.

Post-fix replacement run:

- DLL SHA256:
  `4570da73dcdef9f62885092e4d217c85ef16d8fd388bcddaf27483d0b47bf3aa`
- Run ID: `20260724_151159_windows_replacement_vehicle_order_fixed_4a146332`
- Action: `/syncpair rustler`
- Result: transition `state=1 -> state=2`, `vehicle=25`
- Stable sample position: approximately
  `(205.991, 1884.885, 18.337)`

## Driver key matrix

Final key-sync run:

- DLL SHA256:
  `de766fb7c097112d2713ddd6cec4df2dd6c55b31ae4dfa73078788e42cf53525`
- Run ID: `20260724_151906_windows_replacement_incar_keys_0f244da0`

The Windows controller held each input for 750 ms. The server observed:

| Scenario | Input | Reference | Replacement after fix |
| --- | --- | ---: | ---: |
| On foot | primary fire | `0x4` | `0x4` |
| Rustler driver | gas | `0x8` | `0x8` |
| Rustler driver | primary fire | `0x1` | `0x1` |
| Rustler driver | gas + primary fire | `0x9` | `0x9` |
| Car driver | gas | `0x8` | `0x8` |

The Rustler and normal-car runs both remained in `state=2`, `vehicle=25`
while moving. This confirms that the vehicle key bits are context-specific:
on-foot fire remains `0x4`, while vehicle primary fire is `0x1`.

## Final robustness smoke

- DLL SHA256:
  `5cd68c19bf73cb89359aee43db858c33ad3ee4dd76a668fcb979c777df64fc32`
- Run ID: `20260724_152659_windows_final_vehicle_sync_smoke_5cb625a1`
- Rustler entry transitioned directly from `state=1`, `vehicle=0` to
  `state=2`, `vehicle=25`.
- Combined gas and primary fire was observed by the server as `keys=0x9`.
- This run includes the pending-position sequence robustness change
  (`applied_seq >= required_seq`).

## Remaining work

- `TODO_VERIFY`: recover and use the original GTA `CPad` control-set path
  instead of `GetAsyncKeyState`, especially for remapped controls and gamepads.
- Add reference/replacement coverage for secondary fire, passenger drive-by,
  siren, landing gear, and Hydra thrust.
- Repeat with a second native observer for visible Rustler projectile/effect
  parity; this run proves driver state and wire keys, not remote rendering.

## Incoming VehicleSync follow-up, 2026-07-25

### Fixture and sources

This follow-up used two clients concurrently:

- Original 0.3.7 `samp.dll` in the local reference Wine prefix as
  `SyncPilot`.
- Replacement `samp.dll` on native Windows as `SyncObserver`.
- The same open.mp server and `/syncpair car` route.

The packet layout was checked against open.mp commit
`f8058db80410b70f84c9089ec214530ca9784517`,
`Shared/NetCode/vehicle.hpp`, `PlayerVehicleSync::write`.

Evidence classification:

- Packet layout: `OPENMP_REF`.
- Wire values and runtime application: `PROBE_TRACE`.
- Equivalence to original remote interpolation and GTA control processing:
  `TODO_VERIFY`.

### Confirmed pre-fix gap

Run `20260725_092031_incoming_vehicle_observer_2b8f64ff` received the
original pilot's movement as RakNet packet ID 200, but the replacement logged
every packet as `UNKNOWN` and never decoded or applied it. The observer
therefore had no remote vehicle movement.

### Packet-200 bridge

Replacement DLL SHA256
`c4b5da4b37bc8122c91f96a303bb76f503b958831163f242f9224493b6fb859d`
added bounded server-to-client VehicleSync decoding and a runtime bridge for
the remote player and streamed GTA vehicle.

Run `20260725_092836_incoming_vehicle_observer_after_patch_806c7c7e`
decoded stable, plausible samples for player 1 / vehicle 25, including:

- position and compressed velocity,
- normalized quaternion,
- vehicle and player health,
- armour, weapon and additional-key bits,
- LR/UD controls, keys, siren, landing gear, Hydra and trailer optionals.

The runtime applied movement through at least sequence 256. This first run
then crashed at GTA address `0x00465cc8` when the fixture streamed the vehicle
out while the remote actor still owned its driver task.

### Stream-out lifecycle fix

Replacement DLL SHA256
`63388d8deeabc6063ba389652ab9b86665a4e2e09205df3f93caab2cdc70ea97`
detaches matching remote actors before destroying the GTA vehicle. A later
OnFoot packet only invokes the leave-car opcode while the old vehicle slot is
still active.

The first launch,
`20260725_093219_incoming_vehicle_lifecycle_retest_f83a5689`, crashed before
network initialization at GTA address `0x007f39fb`. No VehicleSync or
vehicle-lifecycle code ran, so this is retained as a preconnect-start
instability sample rather than evidence against the fix.

The clean retry,
`20260725_093600_incoming_vehicle_lifecycle_retry2_4dfc36a7`, observed:

1. packet 200 decoded for player 1 / vehicle 25;
2. remote vehicle sequences applied with `seated=1`;
3. `vehicle: detach_remote_driver`;
4. `vehicle: destroy`;
5. GTA and the launcher still responsive after the scenario stopped;
6. no exception filter event and no dump.

Representative decoded input during acceleration was `keys=0x0008`, matching
the original driver-key matrix.

Final rebuilt DLL SHA256
`056ea4a1188bcac2e7211580813ed07424ce3c554beb5d6143b0434f963c6e52`
was verified in
`20260725_093855_incoming_vehicle_final_smoke_bbc4b0f6`. The runtime named
packet 200 as `VehicleSync`, decoded and applied the movement, and remained
responsive without a dump after stream-out. This run exercised the alternate
safe ordering where the remote-player remove destroyed the actor before the
vehicle remove, so no explicit detach remained necessary.

### Remaining incoming-sync gaps

- The runtime currently applies authoritative transforms and derives yaw from
  the quaternion. Original smoothing, roll/pitch behavior and the remote
  `ProcessControl` path remain `TODO_VERIFY`.
- The test camera set by the fixture was not persistent on the replacement,
  so log evidence proves decode/application/lifecycle behavior but the current
  screenshots are not yet a reliable visual interpolation comparison.
- PassengerSync, TrailerSync, UnoccupiedSync and Aim/Bullet effects still need
  equivalent two-client golden traces.
