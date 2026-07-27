# Death/F4 class-selection and weapon-skill HUD parity (2026-07-27)

## Scope and binary identity

This trace covers local death/recovery, the F4 "return after next death"
latch, RPC 34 local-player routing, and the unwanted GTA single-player
weapon-skill update display.

- Original SA-MP 0.3.7-R5 `samp.dll`:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- GTA SA 1.0 US executable used for address validation:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`
- Replacement DLL used by the final F4/death runtime check:
  `1971f78e90f37b0b53a841452e3b8576bafa19ba653b60d8298585300de67088`

## Original F4/death control flow

`STATIC_037`:

- `CLocalPlayer::Process` is at `samp.dll+0x74C0`.
- At `+0x7CF1`, R5 first checks that its wants-another-class latch is clear,
  then polls `GetAsyncKeyState(VK_F4)` at `+0x7CF9`.
- The key sets `CLocalPlayer+0x2FA` and prints
  `Returning to class selection after next death` at `+0x7D06..+0x7D21`.
  This polling is not gated by chat, dialog, or textdraw visibility.
- Recovery begins at `+0x7D24`. The latch remains pending while the GTA ped
  action is 54 (`DEATH`) or 55 (`WASTED`) at `+0x7D3B..+0x7D50`.
- Normal recovery calls `Spawn` through `+0x7DC3`.
- With the F4 latch set, the branch at `+0x7DD4` clears the wasted state,
  calls `HandleClassSelection` (`+0x4080`), clears the latch, and bypasses
  normal `Spawn`.

This agrees with the 0.2x `CLocalPlayer::Process` source and supersedes the
replacement's earlier UI-gated/early-consumed approximation.

## Original player-skill path and GTA HUD behavior

`STATIC_037`:

- RPC 34 is handled at `samp.dll+0xF5E0`.
- At `+0xF65F..+0xF69E`, R5 compares the RPC player ID with the local SA-MP
  ID stored by `CPlayerPool`, not with RakNet's connection transport index.
- Dispatch at `+0xAE450` selects the local path at `+0x9CA40`.
- The local path validates `skill < 11`, converts the `uint16` level to
  `float`, and writes GTA's stat float directly at
  `0xB79380 + 0x114 + skill*4` (stats 69 through 79). It does not execute
  SCM opcode `062A`.
- R5's general patch routine is at `samp.dll+0xAAEB0`. It patches the first
  byte of GTA `CHud::SetHelpMessage` at `0x588BE0` to `RET`, but does not
  patch GTA `CHud::SetHelpMessageStatUpdate` at `0x588D40` or the global
  `bShowUpdateStats` byte at `0x8CDE56`.

`PROBE_TRACE`:

- Original run:
  `artifacts/runs/20260727-105049-original-player-399207`
- Original probe log:
  `artifacts/runs/20260727-105049-original-player-399207/client/skill_stat_probe.log`
  (`SHA256=853a2969ca3efe006c902c04e1e9cc198c4be7a3b98008e25dfc3bb0a850150b`)
- Replacement comparison log:
  `artifacts/runs/20260727-105523-replacement-player-408965/client/skill_stat_probe.log`
  (`SHA256=1b811e3760be974671422b51f8c7c75b1344e94f025fb76479e33f9cdbe86cc4`)
- Probe ASI:
  `SHA256=8b7a4dfd8bf92b749a47520f9e834b7d389d6875e339c028792ea03f76aa4731`
- After original SA-MP initialization, the sampled bytes were
  `0x8CDE56=1`, `0x588BE0=0xC3`, and `0x588D40=0xA0`.

Therefore globally disabling GTA stat updates would diverge from R5. The
replacement instead follows the original direct CStats write, avoiding the
script-stat notification path that can leave the single-player weapon-skill
bar visible.

## Local-player ID regression and correction

`PROBE_TRACE`:

- Before correction:
  `artifacts/runs/20260727-105951-replacement-player-416842`
  (`built_sha256=b5502d6262751f415fd0a8bbd2ec3a7d1f22ad0c02d4f0030377d67cbc3ac094`)
- In that two-client run, connection acceptance supplied RakNet
  `player_index=1`, while RPC 139/InitGame assigned SA-MP `local_player=0`.
  RPC 34 targeted player 0, but the replacement logged
  `apply_player_skill ... applied=0`.
- After making the InitGame/CPlayerPool ID authoritative:
  `artifacts/runs/20260727-110332-replacement-player-424606`
  (`built_sha256=99911325cbbbc4fef438e329f30bd4af7239c91d104ce96208d82543a41a44bc`)
- The corrected run logs the same `player_index=1`, `local_player=0`, and
  RPC 34 target 0, followed by
  `apply_player_skill ... applied=1 path=direct_cstats`. RPC 89 fighting
  style also changes from `applied=0` to `applied=1`.

The same precedence rule is now used for runtime target dispatch,
scoreboard-local selection, skin routing, and adapter-side player lookup.

## Final F4-after-death runtime trace

`PROBE_TRACE` on the replacement prefix, with the already-running open.mp
test server reused:

- `samp_runtime.log`, process block beginning at overall line 534579:
  - block offset 802: `f4_after_death_latched`
  - block offset 940: local death, health 0, action 54, outgoing death report
  - block offset 1081: `f4_after_death_consumed`, health 100, action 1,
    `normal_respawn_suppressed=1`
- `samp_net_trace.log`, window beginning at overall line 511650:
  - offset 45: outgoing RPC 53 Death, reason 255, responsible 65535
  - offsets 238-240: F4 recovery schedules and sends RPC 128 RequestClass
  - offsets 262-263: successful RPC 128 response
  - no outgoing RPC 52 exists in this process window
- State capture after eight seconds:
  `SHA256=9ccfc78ec413ecb5a4c5a2ed918d46f1e22fcea68fd370630d8f57b29542fa3b`
  reports position `(258.489288, -41.400799, 1002.023438)`, HUD disabled,
  radar blank, and camera mode 15: the class-selection scene.

Result: F4 latches before death, remains pending throughout GTA's death
actions, then enters class selection without leaking the normal RPC 52
respawn path.

## Class-selection visual follow-up

The corrected Windows harness produced a same-machine class-selection pair
while both clients were connected to the same fixture:

- original R5:
  `artifacts/runs/windows-altenter-original/20260727_122006_altenter_original_r5_30444d85`;
- replacement:
  integrated run `20260727_124112_integrated_ui_parity_47f5b927`, burst
  `20260727_124140_685_class-selection-integrated`.

`STATIC_037` reconstructed R5's 310x40 bottom-centered dialog, three 90x30
controls, bold 20-pixel Arial labels, and `sampgui.png` atlas source rectangle.
`OBSERVED_037 + PROBE_TRACE`: the integrated 800x600 replacement capture now
visually matches the original dark backing strip and rounded arrow/Spawn
controls. Default-state class-selection presentation is closed; hover/pressed
frames and other resolutions remain `TODO_VERIFY`.

## Checks and remaining work

- `reimpl/scripts/build_in_devbuild_toolbox.sh`: passed for the tested source.
- Built and deployed DLL hashes matched at final F4/death test time:
  `1971f78e90f37b0b53a841452e3b8576bafa19ba653b60d8298585300de67088`.
- `git diff --check` passed for the two touched implementation files.
- Strict PE parity still reports the repository's known baseline differences
  (entry point, sections/imports/TLS); this change adds no ABI or layout change.
- `TODO_VERIFY`: capture a controlled visual/pixel pair after an RPC 34 skill
  change to close the final visible weapon-skill-bar question.
- `TODO_VERIFY`: remote-player skill storage remains pending until the
  replacement has the corresponding `CPlayerPed` replicas.
- `TODO_VERIFY`: capture class-selection hover/pressed frames and scaling at
  resolutions other than 800x600.
- The final small skin/scoreboard local-ID precedence follow-up compiled, but
  was not followed by another full player run in this scoped test.
