# Legacy GTA SA address cross-reference

Date: 2026-06-09

Scope: addresses used by the 0.2x-era client code under `samp/client/game/`
that call or patch `gta_sa.exe` directly. The old code uses GTA SA 1.0 US
absolute virtual addresses. The RVA column below subtracts the normal
`gta_sa.exe` image base (`0x400000`).

Evidence tags:

* `GTA_REVERSED_REF`: direct match in gta-reversed source/install metadata.
* `SAMPFUNCS_REF`: local SAMPFUNCS/ASI SDK reference in this tree.
* `ALT_02X_CODE`: direct use in this repository's legacy 0.2x client code.
* `INFERRED`: plausible match; still needs Ghidra/runtime confirmation.
* `TODO_VERIFY`: do not treat as final 0.3.7 behavior yet.

Important: these names are GTA SA names, not SA-MP 0.3.7 proof by
themselves. Use them as naming and control-flow evidence. Any compatibility
claim for the replacement DLL still needs `STATIC_037`, `OBSERVED_037`, or
`PROBE_TRACE` evidence.

## High-confidence vehicle matches

| VA | RVA | Name | Legacy use | Evidence |
| --- | --- | --- | --- | --- |
| `0x6A3440` | `gta_sa.exe+0x2A3440` | `CAutomobile::Fix` | `vehicle.cpp` comments this as `CAutomobile::RepairDamageModel`; called when synced damage says fully repaired but GTA state has panel/door/light damage. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6B3E90` | `gta_sa.exe+0x2B3E90` | `CAutomobile::SetupDamageAfterLoad` | `vehicle.cpp` comments this as `CAutomobile::UpdateDamageModel`; called after assigning panel/door/light damage fields. | `ALT_02X_CODE`, `GTA_REVERSED_REF`, `TODO_VERIFY` naming/semantics |
| `0x6B1880` | `gta_sa.exe+0x2B1880` | `CAutomobile::ProcessControl` | `hooks.cpp` dispatches vehicle process hook by vtable. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6AE850` | `gta_sa.exe+0x2AE850` | `CAutomobile::TankControl` | Tank turret hook saves/restores camera/aim around this call for remote drivers. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x729B60` | `gta_sa.exe+0x329B60` | `CAutomobile::FireTruckControl` | Firetruck/SWAT water turret hook saves/restores camera/aim around this call for remote drivers. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6F1770` | `gta_sa.exe+0x2F1770` | `CBoat::ProcessControl` | Same process-control dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6B9250` | `gta_sa.exe+0x2B9250` | `CBike::ProcessControl` | Same process-control dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6C9260` | `gta_sa.exe+0x2C9260` | `CPlane::ProcessControl` | Same process-control dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6C7050` | `gta_sa.exe+0x2C7050` | `CHeli::ProcessControl` | Same process-control dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6BFA30` | `gta_sa.exe+0x2BFA30` | `CBmx::ProcessControl` | Same process-control dispatch; old comment says pushbike/BMX. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6C8250` | `gta_sa.exe+0x2C8250` | `CMonsterTruck::ProcessControl` | Same process-control dispatch; old code marks this as `UNKNOWN2`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6CDCC0` | `gta_sa.exe+0x2CDCC0` | `CQuadBike::ProcessControl` | Same process-control dispatch; old code marks this as `UNKNOWN1`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x6F86A0` | `gta_sa.exe+0x2F86A0` | `CTrain::ProcessControl` | Same process-control dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |

## Vehicle vtable matches

| VA | RVA | Name | Legacy use | Evidence |
| --- | --- | --- | --- | --- |
| `0x871120` | `gta_sa.exe+0x471120` | `CAutomobile` vtable | `vehicle.cpp` subtype detection; `hooks.cpp` process dispatch. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x8721A0` | `gta_sa.exe+0x4721A0` | `CBoat` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x871360` | `gta_sa.exe+0x471360` | `CBike` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x871948` | `gta_sa.exe+0x471948` | `CPlane` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x871680` | `gta_sa.exe+0x471680` | `CHeli` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x871528` | `gta_sa.exe+0x471528` | `CBmx` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x8717D8` | `gta_sa.exe+0x4717D8` | `CMonsterTruck` vtable | Same; resolves old `UNKNOWN2`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x871AE8` | `gta_sa.exe+0x471AE8` | `CQuadBike` vtable | Same; resolves old `UNKNOWN1`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x872370` | `gta_sa.exe+0x472370` | `CTrain` vtable | Same. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |

## Vehicle audio matches

| VA | RVA | Name | Legacy use | Evidence |
| --- | --- | --- | --- | --- |
| `0x4F5700` | `gta_sa.exe+0x0F5700` | `CAEVehicleAudioEntity::JustGotInVehicleAsDriver` | `vehicle.cpp` and `hooks.cpp` remote-driver audio path. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x4FCF40` | `gta_sa.exe+0x0FCF40` | `CAEVehicleAudioEntity::JustGotOutOfVehicleAsDriver` | Exit/remote-driver hook path. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x501E10` | `gta_sa.exe+0x101E10` | `CAEVehicleAudioEntity::ProcessVehicle` | Called with vehicle audio entity as `ecx` and vehicle as argument after setting `s_pPlayerDriver`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0x502280` | `gta_sa.exe+0x102280` | `CAEVehicleAudioEntity::Service` | Hooked/called in vehicle audio processing. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |
| `0xB6B990` | `gta_sa.exe+0x76B990` | `CAEVehicleAudioEntity::s_pPlayerDriver` | Old code writes the active driver ped before `ProcessVehicle`. | `ALT_02X_CODE`, `GTA_REVERSED_REF` |

## Pool and camera addresses

| VA | RVA | Name | Legacy use | Evidence |
| --- | --- | --- | --- | --- |
| `0xB74490` | `gta_sa.exe+0x774490` | `CPools::ms_pPedPool` | `address.h` ped table pointer; ASI probe watches this. | `ALT_02X_CODE`, `PROBE_TRACE`, `GTA_REVERSED_REF` |
| `0xB74494` | `gta_sa.exe+0x774494` | `CPools::ms_pVehiclePool` | `address.h` vehicle table pointer; replacement currently mirrors the old direct pool lookup path. | `ALT_02X_CODE`, `PROBE_TRACE`, `GTA_REVERSED_REF` |
| `0x404910` | `gta_sa.exe+0x004910` | likely direct ped-pool handle lookup helper | Old `ADDR_ACTOR_FROM_ID`; called as method-style helper on `[0xB74490]`, not the public `CPools::GetPed` wrapper. | `ALT_02X_CODE`, `SAMPFUNCS_REF`, `INFERRED`, `TODO_VERIFY` |
| `0x4048E0` | `gta_sa.exe+0x0048E0` | likely direct vehicle-pool handle lookup helper | Old `ADDR_VEHICLE_FROM_ID`; local SannyBuilder data also shows `call_function_method 0x4048E0 struct 0xB74494`. | `ALT_02X_CODE`, `SAMPFUNCS_REF`, `INFERRED`, `TODO_VERIFY` |
| `0x42C4B0` | `gta_sa.exe+0x02C4B0` | likely vehicle ref/id helper | Old `ADDR_ID_FROM_VEHICLE`. Needs Ghidra confirmation. | `ALT_02X_CODE`, `INFERRED`, `TODO_VERIFY` |
| `0x4442D0` | `gta_sa.exe+0x0442D0` | likely ped ref/id helper | Old `ADDR_ID_FROM_ACTOR`. Needs Ghidra confirmation. | `ALT_02X_CODE`, `INFERRED`, `TODO_VERIFY` |
| `0xB6F028` | `gta_sa.exe+0x76F028` | `TheCamera` object base | gta-reversed camera singleton. | `GTA_REVERSED_REF` |
| `0xB6F1A8` | `gta_sa.exe+0x76F1A8` | active camera mode byte inside `TheCamera` | Old hook and ASI probe use this as camera mode. Offset from `TheCamera` base is `0x180`. | `ALT_02X_CODE`, `PROBE_TRACE`, `GTA_REVERSED_REF`, `INFERRED` field name |
| `0xB6F99C` | `gta_sa.exe+0x76F99C` | camera subfield, not object base | Old `ADDR_CAMERA`. Since gta-reversed puts `TheCamera` at `0xB6F028`, this should not be used as the camera base without field-level verification. | `ALT_02X_CODE`, `GTA_REVERSED_REF`, `TODO_VERIFY` |

## Practical naming guidance

* Use the gta-reversed names for the process-control and audio addresses above.
  The matches are exact enough to rename local constants or comments.
* Keep old aliases in comments where they explain legacy intent, for example
  `CAutomobile::Fix` / old `RepairDamageModel`.
* Do not rename `0x4048E0`, `0x404910`, `0x42C4B0`, or `0x4442D0` as public
  `CPools::Get*` APIs yet. They appear to be lower-level pool helper calls.
  Ghidra should verify the calling convention and handle/ref arithmetic first.
* Treat `0xB6F99C` carefully. For current camera work, prefer naming
  `0xB6F028` as `TheCamera` and `0xB6F1A8` as the active mode byte; document
  `0xB6F99C` only after field-level static evidence.

## Sources checked

* Legacy code: `samp/client/game/address.h`, `samp/client/game/vehicle.cpp`,
  `samp/client/game/hooks.cpp`.
* Local ASI/SAMP resource: `sampfuncs/SAMPFUNCS SDK/SannyBuilder Data/opcodes.txt`.
* Local probe/reimpl references: `tools/asi_probe/src/samp_probe_asi.c`,
  `reimpl/src/runtime_bridge.c`.
* gta-reversed online source:
  * https://github.com/gta-reversed/gta-reversed
  * `source/game_sa/Entity/Vehicle/Automobile.cpp`
  * `source/game_sa/Entity/Vehicle/Boat.cpp`
  * `source/game_sa/Entity/Vehicle/Bike.cpp`
  * `source/game_sa/Entity/Vehicle/Bmx.cpp`
  * `source/game_sa/Entity/Vehicle/Plane.cpp`
  * `source/game_sa/Entity/Vehicle/Heli.cpp`
  * `source/game_sa/Entity/Vehicle/MonsterTruck.cpp`
  * `source/game_sa/Entity/Vehicle/QuadBike.cpp`
  * `source/game_sa/Entity/Vehicle/Train.cpp`
  * `source/game_sa/Audio/Entities/AEVehicleAudioEntity.cpp`
  * `source/game_sa/Audio/Entities/AEVehicleAudioEntity.h`
  * `source/game_sa/Pools.cpp`
  * `source/game_sa/Camera.cpp`
