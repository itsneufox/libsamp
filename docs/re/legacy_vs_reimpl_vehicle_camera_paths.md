# Legacy vehicle/camera paths vs replacement runtime

Date: 2026-06-09

This note compares the newly named 0.2x-era client paths with the current
replacement implementation in `reimpl/src/runtime_bridge.c`.

Evidence tags:

* `ALT_02X_CODE`: `samp/client/game/*`.
* `GTA_REVERSED_REF`: names from gta-reversed, mapped in
  `docs/re/legacy_gta_sa_address_crossref.md`.
* `PROBE_TRACE`: current replacement/original trace evidence already captured
  in comments or runtime logs.
* `INFERRED` / `TODO_VERIFY`: needs 0.3.7 static/runtime confirmation.

## Vehicle creation

Legacy path:

* `CVehicle::CVehicle()` requests and synchronously loads the model, then calls
  script `create_car` at `z + 0.1f`, `set_car_z_angle`, disables gas tank
  explosion, disables hydraulics, makes tyres invulnerable, reads the GTA pool
  pointer and stores the GTA handle.
* For normal cars it writes `dwDoorsLocked = 0` directly after creation.
* Train models branch into a dedicated train creation path instead of `create_car`.

Replacement path:

* `vehicle_compat_create_slot()` queues RPC-created vehicles and
  `vehicle_compat_apply_pending_slot()` creates them after spawn/session gates.
* It requests the model, calls `create_car`, sets angle, disables gas tank
  explosion/hydraulics/tyre vulnerability, unlocks the car, sets interior and
  health.
* It intentionally blocks trains and defers colors, paintjob, mods, siren and
  damage.

Current gap:

* `TODO_VERIFY`: legacy adds `+0.1f` to Z for `create_car`; replacement currently
  passes the server Z unchanged. This is worth checking against the floating
  vehicle observations, although gravity/streaming can also explain those.
* `TODO_VERIFY`: deferred color/mod/siren/damage state means replacement-created
  vehicles are visually incomplete compared with legacy.
* `TODO_VERIFY`: train creation remains intentionally unsupported.

## Vehicle pool lookup

Legacy path:

* `ADDR_VEHICLE_TABLE` points to `CPools::ms_pVehiclePool` at `0xB74494`.
* `ADDR_VEHICLE_FROM_ID` calls a lower-level pool handle lookup helper at
  `0x4048E0` method-style with `ECX=[0xB74494]`.

Replacement path:

* `vehicle_compat_game_pool_get_at()` mirrors that lower-level path with guards:
  read `[0xB74494]`, call `0x4048E0`, validate the returned pointer.

Current gap:

* This is one of the closest matches already. The remaining work is Ghidra
  confirmation of the helper's exact handle/ref arithmetic and failure cases.

## Damage state

Legacy path:

* `CVehicle::UpdateDamageStatus()` only runs automobile damage updates when the
  vtable identifies `CAutomobile`.
* If synced panel/door/light damage is all zero but GTA has existing damage, it
  calls `CAutomobile::Fix` (`0x6A3440`) and exits.
* Otherwise it writes `dwPanelStatus`, `dwDoorStatus1`, `dwLightStatus`, then
  calls `CAutomobile::SetupDamageAfterLoad` (`0x6B3E90`) to rebuild the visible
  damage model.

Replacement path:

* RPC vehicle create captures `door_damage`, `panel_damage`, `light_damage` and
  `tyre_damage`, but logs them as `extra_state_deferred`.

Current gap:

* This is a concrete missing behavior. The replacement should use the same
  guarded vtable/subtype check before touching automobile damage fields, then
  call the same GTA rebuild functions once layout offsets are verified.
* For all-zero damage, call the full `CAutomobile::Fix` path instead of just
  clearing fields.

## Remote-driver ProcessControl

Legacy path:

* `AllVehicles_ProcessControl_Hook()` replaces the virtual dispatch, resolves
  the class-specific ProcessControl function by vtable, then calls the original
  target.
* For a remote player driving a GTA player ped, it temporarily:
  * stores local keys;
  * installs remote-player keys;
  * sets the GTA current-player context byte;
  * changes the driver's `dwPedType` so `CPed::IsPlayer` returns false;
  * services the inline `CAEVehicleAudioEntity` at `CVehicle + 312`;
  * calls class-specific `ProcessControl`;
  * restores local keys and ped type.
* Tank and firetruck turret hooks additionally save/restore camera mode and aim
  state around `CAutomobile::TankControl` / `FireTruckControl`.

Replacement path:

* The current runtime creates vehicles and can put the local player into a
  driver seat, but it does not install a GTA `ProcessControl` hook or emulate
  the remote-driver key/aim context switch.

Current gap:

* This is the main semantic gap for remote-driven vehicles. If crashes or bad
  movement happen when remote players/vehicles enter scope, the legacy solution
  was not "just set transforms"; it let GTA run its own per-class control logic
  under a temporary remote input context.
* A replacement-safe version should start as instrumentation: log vtable,
  driver ped, `dwPedType`, current-player byte, audio entity bytes, and whether
  the vehicle has a remote driver, before attempting hooks.

## Vehicle audio

Legacy path:

* Vehicle audio entity is treated as inline at `CVehicle + 312`.
* Known calls:
  * `CAEVehicleAudioEntity::JustGotInVehicleAsDriver` (`0x4F5700`)
  * `CAEVehicleAudioEntity::JustGotOutOfVehicleAsDriver` (`0x4FCF40`)
  * `CAEVehicleAudioEntity::ProcessVehicle` (`0x501E10`)
  * `CAEVehicleAudioEntity::Service` (`0x502280`)
  * `CAEVehicleAudioEntity::s_pPlayerDriver` (`0xB6B990`)
* The remote-driver path services audio inside the same temporary key/ped
  context used for vehicle control.

Replacement path:

* Ped audio reset exists for spawn/model changes.
* Vehicle audio stream stop is observed but not wired; no vehicle audio entity
  service path exists.

Current gap:

* Vehicle audio/radio is not just cosmetic. Some GTA vehicle logic checks
  player-driver state through audio entity globals and current pad state. Keep
  this in mind when diagnosing `PutPlayerInVehicle` or remote-driver anomalies.

## PutPlayerInVehicle

Legacy-relevant behavior:

* The old code validates GTA vehicle existence through the SA-MP vehicle pool and
  lets GTA's own vehicle/task paths run when entering/exiting.
* After a ped becomes a driver, subsequent vehicle control and audio are handled
  by the ProcessControl hook described above.

Replacement path:

* `vehicle_compat_put_local_player()` resolves the active slot, resolves the GTA
  vehicle through `[0xB74494] -> 0x4048E0`, and uses script opcode `036A` for
  driver seat only.
* Passenger seats are intentionally blocked with `passenger_todo_verify`.

Current gap:

* Driver-seat `/vput` is present, but there is no follow-up equivalent of the
  legacy ProcessControl/audio context. If the player is placed into a car but
  control/audio/camera feels wrong, this is the next path to trace.
* Passenger seats need original-DLL evidence before enabling.

## Spawn/camera

Legacy-relevant behavior:

* Vehicle turret hooks show that SA-MP actively saves/restores `TheCamera` mode
  bytes while temporarily simulating remote aim.
* `0xB6F1A8` is the active camera mode byte inside `TheCamera`; `0xB6F99C` is
  not the camera object base.

Replacement path:

* Spawn finalize restores camera through script commands, unlocks the actor,
  releases UI mouse capture and after a delay writes gameplay mouse-camera
  values back.

Current gap:

* Spawn camera restore is now closer to legacy behavior, but it is still an
  inferred script/direct-memory repair rather than a traced copy of the 0.3.7
  spawn path.
* If mouse-look still fails after spawn, collect the same variables the legacy
  code manipulates: `TheCamera` active mode byte, secondary mode word, mouse
  accel/use-mouse bytes, frontend/menu bytes, and Win32 cursor capture/focus.

## Next implementation order

1. `STATIC_037`: confirm vehicle damage field offsets and the call order around
   `CAutomobile::Fix` / `SetupDamageAfterLoad` in original `samp.dll`.
2. Implement automobile damage application in the replacement, gated by vtable
   and pointer readability.
3. Instrument remote-driver vehicles before adding hooks: vtable, driver ped,
   current-player byte, key context, `dwPedType`, audio entity bytes.
4. Use that trace to decide whether to emulate the legacy ProcessControl context
   or leave vehicle movement purely server-transform driven.
5. Revisit `PutPlayerInVehicle` after instrumentation, because legacy behavior
   depends on the subsequent ProcessControl/audio path.
