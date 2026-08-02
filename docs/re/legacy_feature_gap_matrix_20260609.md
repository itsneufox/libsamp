# Legacy feature gap matrix

Date: 2026-06-09

Scope:

* Legacy source reviewed from
  `/home/chairman/Projects/sa-mp-legacy-rebuild/samp/client`.
* Current replacement reviewed from `reimpl/src/runtime_bridge.c`,
  `reimpl/src/net/raknet_client_adapter.cpp`, and
  `reimpl/include/sampdll/net/raknet_client_adapter.h`.
* This is a behavior-oriented gap list, not proof of exact 0.3.7 behavior.
  `STATIC_037` Ghidra evidence and/or `PROBE_TRACE` runs are still required
  before treating any legacy-only behavior as original-DLL native behavior.

Evidence tags used here:

* `ALT_02X_CODE`: behavior exists in the legacy source tree.
* `CURRENT_REIMPL`: behavior exists in the current replacement.
* `OPENMP_REF`: current RPC naming/semantics align with open.mp references or
  the current open.mp-oriented adapter table.
* `INFERRED`: current status inferred from local code inspection.
* `TODO_VERIFY`: needs focused original 0.3.7 static/runtime confirmation.

## Current replacement baseline

The replacement is no longer empty. The broad working surface is:

* RakNet bootstrap/autojoin, reconnect text, `/q` disconnect, chat send and
  command routing. (`CURRENT_REIMPL`, `PROBE_TRACE`)
* Class selection, left/right class requests, spawn request/response, spawn
  camera/mouse restore, and pause menu pass-through. (`CURRENT_REIMPL`,
  `PROBE_TRACE`, `TODO_VERIFY`)
* Basic local player placement, health/armour/armed weapon, controllable flag,
  time/weather/interior, camera pos/look-at/behind-player. (`CURRENT_REIMPL`)
* Dialogs, client messages, textdraw show/hide/set-string/select/click, partial
  D3D/GTA-font drawing. (`CURRENT_REIMPL`)
* Basic player pool events, score/ping updates, remote player add/remove/death,
  partial remote on-foot sync and markers. (`CURRENT_REIMPL`)
* Basic world vehicle create/remove/health/put-local-player and local on-foot /
  in-car sync send. (`CURRENT_REIMPL`)
* Basic object create/remove/set-pos/set-rot/move/stop plus partial object
  material observation/application. (`CURRENT_REIMPL`)
* Early custom asset/archive inspection and guarded model registration notes,
  not a full loader yet. (`CURRENT_REIMPL`, `PROBE_TRACE`, `TODO_VERIFY`)

## Missing or mostly absent legacy subsystems

| Area | Legacy behavior surface | Current status | Impact | First useful slice |
| --- | --- | --- | --- | --- |
| Pickup pool | `net/pickuppool.*` manages server pickups, dropped weapon pickups, pickup processing and `PickedUpPickup` flow. | `ScrCreatePickup` and `ScrDestroyPickup` are dummy; outgoing picked-up RPC exists only as metadata. | Pickup-heavy modes will not show or report pickups correctly. | Implement pool slots, create/destroy, local proximity pickup notification. |
| Gang zones | `net/gangzonepool.*` stores zones, draws radar overlays, flash/stop-flash/delete. | Implemented for RPC 108/120/121/85 with a 1024-slot recovery snapshot, shared 500 ms flash phase, and validated radar/pause-map call hooks. (`STATIC_037`, `CURRENT_REIMPL`, `TODO_VERIFY`) | Runtime path is complete; visual/color parity still needs a replacement run. | Run `/rpczones`, inspect radar and ESC map through all four phases, then archive the trace. |
| Menu pool | `net/menupool.*` handles SA-MP menu creation, show/hide, current menu, selection/quit. | Implemented: bounds-checked 128-slot pool, RPC 76/77/78 decode, 640x460-scaled two-column overlay, disabled-row keyboard navigation, and outgoing RPC 132/140. | Runtime path is complete; visual and wire parity still need an original/replacement trace pair. | Run `/rpcmenu` in the bare fixture and archive both RPC traces. |
| Checkpoints | Legacy local player code processes checkpoints and race checkpoints. | `ScrSetCheckpoint`, `ScrDisableCheckpoint`, `ScrSetRaceCheckpoint`, `ScrDisableRaceCheckpoint` are dummy. | Mission/race/guidance markers are absent. | Add normal checkpoint first, then race checkpoint arrow/ring semantics. |
| 3D labels and chat bubbles | `label.*` and RPCs create/update/draw text in world. | Create 3D label is decoded/observed only; update is dummy; `/dl` debug labels are separate ad hoc UI. | Roleplay/admin/debug labels and chat bubbles are missing. | Build a real label pool using the existing D3D overlay path. |
| Actor pool | `net/actorpool.*`, `remoteactor.*`, `game/actorped.*` manage server actors/NPC-like peds, animations, damage, visibility. | No equivalent actor pool in current runtime/header snapshot. | Actor-heavy scripts will silently lose peds. | Add actor slot model and spawn/remove first; defer animation/damage until traced. |
| Death window | `deathwindow.*` renders kill feed/connect/disconnect entries. | `ScrDeathMessage` is dummy; no death window renderer. | Kill feed and special connect/disconnect UI are absent. | Reuse D3D font overlay to render buffered death messages. |
| Player name tags | `newplayertags.*` renders name, health, armour, distance-scaled 3D tags. | Current markers/remote player display are partial; `ScrShowPlayerNameTagForPlayer` is dummy. | Remote players lack accurate legacy name-tag behavior. | Implement tag visibility flags, LOS/distance, health/armour bars. |
| Help and netstats | `helpdialog.*`, `netstats.*`, `svrnetstats.*` plus function-key toggles. | No full equivalents. | F1/F5/F10 legacy diagnostics are absent. | Add lightweight overlays fed by existing adapter state. |
| Game text | `CGame::DisplayGameText` path exists in legacy and is used by bounds/carjack/debug flows. | `ScrDisplayGameText` is dummy. | Common server HUD messages are missing. | Implement opcode-backed or overlay-backed gametext with style/time. |
| Map icons | Legacy player/color/radar helper paths and map-marker RPCs update radar blips. | `ScrSetPlayerMapIcon` dummy; remove map icon is merged with clock RPC metadata. | GPS/admin/map markers missing or inconsistent. | Confirm 0.3.7 RPC layouts and use GTA radar blip helpers. |
| Audio streams | Legacy has BASS-style audio stream flow and GTA sound helpers. | `ScrPlayAudioStream` dummy; `ScrStopAudioStream` decoded only with backend not wired. | Radio/audio-stream features do not work. | Wire BASS/Wine-safe stream open/stop behind guards. |
| Player weapons/money/stats | Legacy player/game wrappers handle money, ammo, weapon grant/reset, skills, drunk level, wanted, shop names. | Reset money/weapons and armed weapon exist; give weapon, ammo, money, skill, drunk, wanted, shop name are dummy. | Many gamemode effects are invisible or desynced locally. | Start with `GivePlayerWeapon`, `SetPlayerAmmo`, money and wanted level. |
| Player actions/animations | Legacy has special actions, fighting style, apply/clear animation, jetpack, goggles, dancing, hands-up and task helpers. | Apply animation is decoded only; clear/special/fighting are dummy. | RP/action servers will show wrong local/remote ped state. | Apply/clear animation through GTA script commands after layout confirmation. |
| Attached objects | Legacy ped/object paths handle held/attached objects. | Partial: RPC 75/113 lifecycle, guarded object creation, root attachment, RPC 116/117 edit overlay and outgoing cancel/final/update responses are implemented. Original bone-matrix attachment, anisotropic scale, material colours and 3D-gizmo parity remain open. (`STATIC_037`, `CURRENT_REIMPL`, `OPENMP_REF`, `TODO_VERIFY`) | Cosmetics and editing work at compatibility level, but bone/scale/colour visuals can differ from R5. | Reproduce the R5 `CPlayerPed` attachment wrapper/render update around `samp.dll+0xB0B10`, then trace all 18 bones. |
| Spectating/camera attach | Legacy local player has `ToggleSpectating`, `SpectatePlayer`, `SpectateVehicle`, and camera-on-actor/vehicle script paths. | Spectate RPCs and camera attach/interpolate RPCs are dummy. | Admin/spec modes and scripted cameras fail. | Implement spectate state machine using legacy script command sequence. |
| Vehicle advanced state | Legacy `vehiclepool.*` and `game/vehicle.*` include waiting list/model loading, damage model rebuild, mods, paintjob, number plate, trailer, respawn/wasted, unoccupied sync, params/interior/velocity. | Basic create/remove/health/put-driver exists; many create extras are deferred; params, component removal, link interior, remove from vehicle, velocity, number plate, trailer, set pos/z-angle are dummy. | Vehicle-heavy servers still have major visual/behavior gaps. | Next best: damage/mod/paintjob application, then params/interior/trailer/unoccupied. |
| Remote vehicle control | Legacy hooks GTA vehicle `ProcessControl` and temporarily swaps remote input/ped context for remote drivers. | Current runtime does not implement that hook/context switch. | Remote-driven vehicles may move less like legacy GTA simulation. | Instrument first; then consider guarded ProcessControl compatibility hook. |
| World edits | Legacy/game wrappers include world bounds, explosions, remove building, stunt bonus, gravity. | RemoveBuildingForPlayer RPC 43 now scans building/dummy/object pools, applies the R5 removed flag/Z lowering and persists rules for stream re-application. Other listed world edits have separate status. (`STATIC_037`, `CURRENT_REIMPL`, `TODO_VERIFY`) | Remove-building is implemented but still needs visual original/replacement confirmation. | Run the Area 51 fixture and compare pool/removal traces against R5. |
| Archive/custom assets | Legacy has `archive/*`, crypto/signing/hash helpers, memory module support. | Current docs/runtime only inspect/register pieces; no full SA-MP custom asset pipeline. | Custom objects/skins/assets remain incomplete. | Continue staged asset pipeline from `docs/re/samp_custom_asset_pipeline.md`. |
| Crash/reporting utilities | Legacy has `exceptions.*`, `runutil.*`, MD5/build helpers. | Replacement has traces/logging, but not the same rich client crash/report path. | Harder user-side crash triage and less parity with original diagnostics. | Add compact exception context only if it helps current crash work. |

## RPCs that are currently dummy or decoded-only

From the current adapter metadata, these are the clearest server-to-client gaps.
Some names come from compatibility references and still need original-DLL
layout confirmation.

Player/world basics:

* Dummy: `ScrSetPlayerName`, `ScrSetPlayerPosFindZ`, `ScrSetWorldBounds`,
  `ScrGivePlayerMoney`, `ScrGivePlayerWeapon`, `ScrSetPlayerShopName`,
  `ScrSetPlayerSkillLevel`, `ScrSetPlayerDrunkLevel`, `ScrToggleClock`,
  `ScrSetPlayerAmmo`, `ScrSetGravity`, `ScrSetPlayerSkin`,
  `ScrSetPlayerWantedLevel`.
* Decoded-only: `ScrSetPlayerTeam`, `ScrSetPlayerColor`.

Vehicles:

* Dummy: `ScrSetVehicleParamsEx`, `ScrRemoveVehicleComponent`,
  `ScrLinkVehicleToInterior`, `ScrRemovePlayerFromVehicle`,
  `ScrSetVehicleVelocity`, `ScrSetNumberPlate`,
  `ScrAttachTrailerToVehicle`, `ScrDetachTrailerFromVehicle`,
  `ScrSetVehiclePos`, `ScrSetVehicleZAngle`,
  `ScrSetVehicleParamsForPlayer`.
* Partial: world vehicle create/remove/health and driver-seat put are present,
  but create extras and advanced control are incomplete.

World UI and markers:

* Dummy: `ScrDeathMessage`, `ScrSetPlayerMapIcon`, `ScrUpdate3DTextLabel`,
  `ScrChatBubble`, `ScrDisplayGameText`, `ScrShowPlayerNameTagForPlayer`,
  `ScrInitMenu`, `ScrShowMenu`, `ScrHideMenu`, `ScrCreatePickup`,
  `ScrDestroyPickup`, `ScrSetCheckpoint`, `ScrDisableCheckpoint`,
  `ScrSetRaceCheckpoint`, `ScrDisableRaceCheckpoint`.
* Decoded-only: `ScrCreate3DTextLabel`.

Camera/spectating/actions:

* Dummy: `ScrAttachCameraToObject`, `ScrInterpolateCamera`,
  `ScrTogglePlayerSpectating`, `ScrPlayerSpectatePlayer`,
  `ScrPlayerSpectateVehicle`, `ScrClearAnimations`,
  `ScrSetPlayerSpecialAction`, `ScrSetPlayerFightingStyle`,
  `ScrSetPlayerVelocity`.
* Partial: `ScrSetPlayerAttachedObject`, `ScrAttachObjectToPlayer`, attached/object edit RPCs 116/117.
* Decoded-only: `ScrApplyAnimation`.

Audio/world effects:

* Dummy: `ScrPlayAudioStream`, `ScrCreateExplosion`,
  `ScrEnableStuntBonusForPlayer`,
  `ScrGameModeRestart`.
* Implemented pending runtime parity trace: `ScrPlayCrimeReport`, `ScrRemoveBuildingForPlayer`.
* Decoded-only: `ScrStopAudioStream`.

## Suggested implementation order

1. Vehicle advanced state: damage, params, mods, paintjob, number plate and
   trailer/interior. This is closest to the issues we already debugged and has
   good legacy/GTA-reversed address evidence.
2. GameText, checkpoints, 3D labels and death window. These are visible,
   high-signal compatibility wins and mostly isolated from core physics.
3. Pickup pool and map icons. These unlock many ordinary gamemode mechanics.
4. Spectating and camera attach/interpolate. Important, but touches camera state
   and should use Ghidra/static evidence before broad changes.
5. Player actions/animations/attached objects. High compatibility value, but
   should be implemented defensively because model/animation loads can crash.
6. Menus and gang zones are implemented; capture original/replacement golden
   traces and visual parity evidence before marking them done.
7. Full custom asset/archive pipeline. Large surface; continue staged and
   trace-driven.

## Main conclusion

The current replacement has the essential session loop now, but the legacy
client had a much broader set of persistent pools and UI renderers. The largest
"we do not have this at all" gaps are pickups, menus, gang zones, actors,
checkpoints, death window, full 3D labels/chat bubbles, spectating, audio
streams, and advanced vehicle/player state. The most valuable next compatibility
work is to turn the existing dummy/decoded RPCs into small, evidence-backed
pools and render/update paths instead of continuing to add ad hoc one-off fixes.
