# Pickup, death/respawn, jetpack, and UI parity battery — 2026-07-26

## Scope and builds

- Original/reference: SA-MP 0.3.7-R5 `samp.dll`
  SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- Replacement build after this battery:
  SHA256 `915cf97bd4dc1f5287997fe845fd0fa5fe6590febfd6d4e0f912cf011fbb9a9c`.
- Server: local open.mp test server on port 7798 with
  `omp-server-bare/filterscripts/sync_pair.pwn`.
- Replacement Windows run proving the final death lifecycle:
  `20260726_225052_fresh-jetpack-then-respawn_7652d385`.

The original and replacement cases used the same health-zero, pickup-at-player,
and `SetPlayerSpecialAction` fixture paths.

## Pickup

### Original

`OBSERVED_037`: a normal pickup created at the local player caused
`OnPlayerPickUpPickup(player=0, pickup=0)`. Before the fixture destroyed the
pickup, the original client repeated the notification at roughly 1.5-second
intervals while the player remained in it.

### Replacement before fix

`PROBE_TRACE`: run `20260726_222630_sync-pilot-retry_d9b118e9` rendered the
pickup and placed the player inside it, but emitted no pickup RPC and caused no
server callback.

### Replacement after fix

`PROBE_TRACE`: run `20260726_223645_sync-pilot-pickup-hook_d0ce75c7` installed
the validated GTA pickup hook at `gta_sa.exe+0x579C6`, observed stock bytes
`8A 46 1C 3C 06`, mapped the GTA pool entry to SA-MP pickup 0, and sent RPC 131.
The server observed exactly one callback and destroyed the fixture pickup:

```text
PICKUP_CREATED pickup=0 player=0
PICKUP_COLLECTED player=0 pickup=0 scenario=5
```

## Death and respawn

### Original

`OBSERVED_037`: health zero produced:

```text
state 1 -> 7
PLAYER_DEATH killer=65535 reason=255
about four seconds later: state 7 -> 8 -> 1
```

### Replacement gaps and fixes

The initial replacement packet used an 8-bit responsible-player field and
`RELIABLE_SEQUENCED`. open.mp ignored that two-byte RPC. `ALT_02X_CODE` and the
original callback establish the layout as byte reason plus 16-bit `PLAYERID`;
world death uses 65535. RPC 53 now uses that layout and
`RELIABLE_ORDERED`.

After fixing RPC 53, on-foot sync resumed while the server was still in wasted
state. Sync is now suppressed during the death latch. When GTA recovers health,
the client sends a fresh, unguarded empty RPC 52 before resuming sync.

`PROBE_TRACE`: final replacement run:

```text
22:51:42 state 1 -> 7
22:51:42 PLAYER_DEATH killer=65535 reason=255
22:51:46 state 7 -> 8
22:51:46 ROLE_SPAWNED
22:51:46 state 8 -> 1
```

This matches the observed R5 state order and approximately four-second timing
for the tested world-death case. Weapon/killer attribution remains
`TODO_VERIFY`.

## Jetpack

`STATIC_037`: R5 uses:

- `samp.dll+0xACD10` for `CPlayerPed::StartJetpack`;
- `samp.dll+0xACD60` for `StopJetpack`;
- `samp.dll+0xACDC0` for `IsInJetpackMode`;
- GTA `CCheat::JetpackCheat` at `0x439600`;
- jetpack-task vtable `0x8705C4`.

`OBSERVED_037 + PROBE_TRACE`: an original pilot sends on-foot
`special_action=2`, and a replacement observer instantiates and visibly renders
the remote jetpack.

`PROBE_TRACE + TODO_VERIFY`: a replacement local player receiving RPC 88 with
action 2 still logs `special_action=jetpack start_failed=1`, remains visually
without a jetpack, and sends `special_action=0`. This also reproduces on a fresh
spawn, so it is not solely a stale post-death task. The static wrapper and task
layout are recorded, but local GTA task creation still needs a focused runtime
probe before claiming parity.

## Scoreboard and chat status

`OBSERVED_037 + PROBE_TRACE`: original R5 keeps the GTA input call active while
TAB is held; W+TAB moved the local player by about 3.08 units in three
comparable runs. The replacement previously applied the chat-input NOP patch,
froze movement, and enabled the cursor for plain TAB. The implementation now
keeps plain TAB display-only; only RMB scoreboard interaction enables the
cursor/input patch. This code change still needs a fresh automated Windows TAB
run because the remote input allow-list does not currently expose TAB.

Basic chat activation/send is covered: T/F6 activation, text submission, and
restoration of GTA input have matched in prior comparable runs. Full parity is
not yet claimed for history scrolling, long-line wrapping/truncation, codepage
edge cases, duplicate colors, or chat-page sizing.

## Additional parity queue

- killer/weapon attribution and damage-before-death ordering;
- dropped/weapon pickup type 14 behavior and pickup respawn timing;
- passenger, trailer, train, surfing, and enter/exit-vehicle notifications;
- spectating and virtual-world/interior stream transitions;
- pause/AFK send-rate behavior and packet-loss interpolation;
- chat history/codepage limits and interactive scoreboard row selection;
- jetpack local task creation, flight controls, vertical velocity, landing, and
  observer interpolation.
