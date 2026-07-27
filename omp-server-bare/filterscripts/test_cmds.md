# Automated `test_cmds` compatibility run

This test-only filter script is adapted from the SA-MP 0.3.7
`filterscripts/test_cmds.pwn` fixture. It is loaded by
`omp-server-bare/config.json` and runs a deterministic sequence for the player
that starts it. No input is required after the initial command. The local
`tools/reloop/reloop` runner can also queue, spawn, start and evaluate a run
without any player input.

Do not load this filter script on a public server.

## Commands

| Command | Action |
| --- | --- |
| `/tbatch` | Run all test groups with the default 1200 ms step delay. |
| `/tvehicle` | Run vehicle creation, mods, enter, eject, respawn and destroy. |
| `/tplayer` | Change/verify world and skin; trace RPC 19/opcode 0173; restore state. |
| `/tpvars` | Set, verify, modify, verify and delete integer/string/float PVars. |
| `/tui` | Cycle GameText, dialogs and TextDraw show/hide without input. |
| `/tpassword` | Show a password dialog for a visual masking and RPC response probe. |
| `/tlabels` | Create, attach, update and delete global/player 3D labels. |
| `/testcmds batch [group] [delay_ms]` | Run `all` or one named group with a custom delay. |
| `/testcmds run <group> [delay_ms]` | Run one named group. |
| `/testcmds status` | Show the current case, step and counters. |
| `/testcmds stop` | Stop timers and remove temporary vehicles, labels, dialogs and TextDraws. |

Valid groups are `all`, `vehicle`, `player`, `pvars`, `ui` and `labels`.
Delays outside 250-10000 ms fall back to 1200 ms.

Examples:

```text
/tbatch
/testcmds batch all 2000
/testcmds run vehicle 750
```

## Host-driven unattended run

`tools/reloop/reloop` writes a one-shot request to
`scriptfiles/test_cmds_request.txt` before launching the configured client:

```text
<request_id> <all|vehicle|player|pvars|ui|labels> <delay_ms> <autospawn 0|1> <player_name|*>
```

The filterscript polls this file every 500 ms, validates and removes it, then
claims only the matching player. With `autospawn=1`, the test fixture applies
the bare gamemode's deterministic Area 51 spawn and calls `SpawnPlayer`. The
ordinary test sequence begins 1000 ms after `OnPlayerSpawn`.
Batch groups are separated by a logged `case_settle` timer. The vehicle group
gets an extra 500 ms because RPC 71/vehicle respawn and their client sync are
asynchronous; this prevents the next case from measuring leftover transition
state without changing the RPC or GTA-opcode path under test.

Every host-driven line includes `request=<request_id>`. Machine-readable
milestones are `REQUEST_ACCEPTED`, `AUTO_SPAWN`, `RUN_START`, `RUN_DONE` and
`RUN_ABORT`. Manual commands use `request=0`.

## Result records

Every step is written in the same verbose, grep-friendly format to:

- the open.mp server log/console;
- `omp-server-bare/scriptfiles/test_cmds_results.log` (append-only);
- the initiating player's chat.

Example record:

```text
[test_cmds] request=123 run=1 player=0 name=ReLoop case=vehicle step=3 status=ACTION event=vehicle_respawn detail=SetVehicleToRespawn vehicle=25 returned=1
```

The status values are:

- `PASS`: the result was verified server-side;
- `FAIL`: an API call or its subsequent state verification failed;
- `ACTION`: a test transition or non-final API result;
- `OBSERVE`: the server sent the operation, but correct client rendering or a
  delayed client-owned state transition still needs trace/screenshot review.

Each complete run ends with `event=run_summary` and `marker=RUN_DONE`. A
disconnect, explicit stop, or filter-script shutdown emits `marker=RUN_ABORT`,
invalidates pending timer tokens and cleans up all temporary state.

## Vehicle sequence

The vehicle group deliberately exercises the lifecycle without operator input:

1. Create a Sultan near the player, apply wheels/nitro/paintjob, damage its
   health and repair it.
2. Put the player in the driver seat and verify vehicle ID/player state.
3. Eject the player and verify that the player is no longer in a vehicle.
4. Respawn the vehicle and verify `OnVehicleSpawn`, model and spawn position.
5. Reapply components in `OnVehicleSpawn`, then destroy the temporary vehicle.

## Evidence and scope

- `OPENMP_REF`: API signatures and callback behavior follow the official
  open.mp documentation, including `DIALOG_STYLE_PASSWORD` and the unmasked
  `inputtext` delivered to `OnDialogResponse`.
- `INFERRED`: timer spacing is a test-fixture choice, not claimed original
  SA-MP timing.
- `INFERRED`: host-driven auto-spawn exists only to remove class-selection
  input from compatibility runs; it is not an assertion about original client
  spawn timing.
- `OBSERVED_037 + PROBE_TRACE`: RPC 71/`RemovePlayerFromVehicle` may leave the
  last vehicle ID in open.mp's server-side player state until the subsequent
  transition. The fixture records this as `OBSERVE`; it is neither a failure
  nor a fabricated pass.
- `OBSERVED_037 + PROBE_TRACE`: delayed `GetPlayerFacingAngle` is not a stable
  client-application assertion because OnFootSync overwrites it on original R5
  as well. `player_facing_opcode` records expected/actual values and requires
  RPC 19/GTA opcode `0173` trace evidence; world and skin remain hard checks.
- Source provenance is recorded at the top of `test_cmds.pwn`, including the
  SHA-256 of the legacy fixture used for the adaptation.

The original commands that require another selected player, a pre-existing
trailer, or human dialog/scoreboard interaction remain covered by their
dedicated bare-gamemode fixtures instead of being faked as server-side passes.
