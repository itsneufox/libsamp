# AFK, pause, and focus-input parity (2026-07-27)

## Scope and reference

This pass covers remote player-status rendering, `/nametagstatus`, GTA window
focus loss, and the boundary between the GTA pause menu and SA-MP processing.

Reference binary:

- SA-MP 0.3.7-R5 `samp.dll`
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- prefix:
  `/home/chairman/Games/san-andreas-multiplayer-legacy-legacy`

All original-DLL claims below are `STATIC_037` unless another tag is stated.
No Proton or Windows runtime comparison was run for this pass.

## `/nametagstatus` and the remote status glyph

The previous replacement behavior was wrong: it used `/nametagstatus` to hide
remote health and armour bars.

The R5 command handler at `samp.dll+0x68720` dispatches to
`samp.dll+0x8E90`. That function toggles `CNetGame+0x234`, prints
`NameTag Player Status: ON/OFF`, and persists the inverse setting as
`nonametagstatus`. It does not toggle normal name, health, or armour drawing.

The remote name-tag loop supplies two independent arguments:

- `samp.dll+0x75560` calls the remote-state getter at `+0x16330`;
- `samp.dll+0x7556D` reads the player-status display flag from
  `CNetGame+0x234`;
- both values reach the name-tag renderer at `samp.dll+0x6CDA0`.

The gated block at `samp.dll+0x6CF6B..+0x6D086` does the following:

- lazily creates two `SAMPAUX3` D3DX fonts through `samp.dll+0x69BB0`;
- the exact heights are 20 and 22, weight 400, one mip level,
  `SYMBOL_CHARSET`;
- measures and draws glyph `C` with the 22-pixel font in black;
- overlays glyph `E` with the 20-pixel font in `0xFFE3E1E3`;
- draws this composite only when the remote state argument is `2`.

The replacement now keeps health and armour visible independently of
`/nametagstatus`, uses the same two fonts/glyphs/colors, and releases them with
the rest of the D3DX resources on device reset and shutdown.

The final mapping of the original `+17/-22` glyph anchor onto the
replacement's projected tag origin remains `INFERRED` and `TODO_VERIFY`.
Reading and writing the original `nonametagstatus` config key is also still
open; the replacement toggle currently lasts for the running process only.

## Remote inactivity state and cadence

The original remote-player state field is at `CRemotePlayer+0x1C5`:

- constructor `samp.dll+0x15FE8` initializes it to `2`;
- getter `samp.dll+0x16330` returns it while the remote ped is valid;
- `CRemotePlayer::Process` computes elapsed time from the last sync tick at
  `samp.dll+0x166DA..+0x166F0`;
- on-foot transition at `+0x16DA0` uses 3000 ms when all three movement
  components are zero and 1500 ms otherwise;
- driver transition at `+0x16FE2` uses the same 3000/1500 ms split;
- passenger transition at `+0x1704E` uses 3000 ms;
- `+0x170D6` returns state `2` to `0` when the elapsed time is below 1500 ms.

The replacement does not expose an ABI-identical `+0x1C5` state machine.
It therefore derives state `2` from each slot's decoded `last_sync_tick`,
movement vector, and seat:

- moving on-foot/driver: 1500 ms;
- stationary on-foot/driver: 3000 ms;
- passenger: 3000 ms;
- no sync observed yet: state `2`.

Those thresholds and original transitions are `STATIC_037`. The replacement
field mapping is `INFERRED` and `TODO_VERIFY`, especially under packet loss,
passenger sync, and vehicle interpolation.

## `WM_KILLFOCUS`

The R5 WndProc is at `samp.dll+0x61650`. Its `WM_KILLFOCUS` branch at
`samp.dll+0x61B75..+0x61BCC` performs this order:

1. if the scoreboard is visible, `+0x6E9E0(1)` closes it and restores cursor
   mode;
2. if chat input is active, `+0x69580` closes it;
3. if the class-selection GUI is visible, `+0xA06F0(0, 1)` releases its
   cursor/input mode;
4. `+0xA05D0` advances the delayed GTA-input restore;
5. processing chains to the saved GTA WndProc.

There is no explicit dialog close or TextDraw-selection cancel in this branch.

The replacement now follows that ownership boundary:

- restores scoreboard HUD/mouse state immediately;
- closes chat input;
- releases class-selection mouse ownership;
- preserves dialog and TextDraw state;
- clears only a transient dialog-button press so focus return cannot submit a
  stale click;
- chains the focus-loss message to GTA.

A scoreboard release latch also prevents a physically held TAB key from
immediately reopening the polling-based replacement scoreboard after focus
returns. A fresh TAB release/key press is required.

Class-selection cursor ownership is now limited to the foreground GTA window
and a closed GTA frontend menu. The class selection itself remains active.

## Pause and anti-pause boundary

`CGame::IsMenuActive` is `samp.dll+0xA0920`. R5 uses it broadly in the WndProc
and render paths. For example, the render entry at `samp.dll+0x75730` tests it
at `+0x7576D` and skips the SA-MP overlay draw block while GTA's frontend menu
is open.

This is evidence that pause-menu UI/input rendering is gated. It is not
evidence that RakNet pumping or every outbound sync class stops. A comparable
two-client runtime trace is still required before changing network cadence.

The replacement's seven-byte NOP at GTA VA `0x561AF0`
(`gta_sa.exe+0x161AF0`) is supported by the 0.2x legacy patch source. The
original GTA instruction is:

```text
C6 05 49 CB B7 00 01    mov byte ptr [0xB7CB49], 1
```

No direct R5 reference to address `0x561AF0` was found in the static DLL scan,
so the claim that R5 applies this exact patch remains `ALT_02X_CODE`,
`GTA_REVERSED_REF`, and `TODO_VERIFY`, not `STATIC_037`.

## Checks

- Win32 replacement build:
  `reimpl/scripts/build_in_devbuild_toolbox.sh`
- result: pass
- candidate SHA256:
  `72becff0243dc3a4319001896952623438a7f6cb1bc947b0028105f232dd077a`
- strict PE identity report still shows the repository's known structural
  replacement/original differences; no new compiler or linker failure.

## Runtime scenarios still required

1. Original and replacement observer: stationary, moving on-foot, driver, and
   passenger status appearance at 1500/3000 ms.
2. `/nametagstatus` off/on: glyph changes while health/armour remain visible.
3. Focus loss with chat input, plain TAB, right-click scoreboard mode, and
   class selection; verify dialogs and TextDraw selection survive.
4. Hold TAB across focus loss and return; verify no sticky reopen before
   release.
5. GTA pause menu with a second observer: compare on-foot, aim, driver,
   passenger, and keepalive packet cadence separately.
