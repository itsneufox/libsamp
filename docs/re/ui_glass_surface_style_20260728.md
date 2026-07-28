# Glass UI, cursor and modal-input parity (2026-07-28)

## Scope

This note records the replacement-client UI pass for dialogs, the scoreboard,
class-selection arrows, the visible cursor and modal dialog input ownership.

Reference binaries:

- SA-MP 0.3.7-R5 `samp.dll`
  SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- GTA:SA USA 1.0 `gta_sa.exe`
  SHA256 `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`
- Live-validated replacement build before restore-path hardening
  SHA256 `148d595cd5df69f2d5edb1d4fbf48e3c5259d08b260bf2920814a2f1c0fde6a3`
- Current compiled restore-path hardening build, not yet live-validated
  SHA256 `554ff496585e4736518c12a548b67d19bf859e8740a6fdaa6f85d5ad271711a8`

## Glass surface style

`USER_REQUESTED + MTA_REF`:

- Dialog, scoreboard and class-selection fallback controls now share one dark,
  semitransparent surface palette.
- Panels use a dark fill, a slightly brighter header/highlight and an explicit
  border. Normal, hovered and pressed controls remain distinguishable.
- The square replacement class-selection arrows remain the default fallback.
- This is an intentional modern compatibility style, not an assertion that
  R5 used the same pixels.

MTA was used only as a low-priority conceptual reference for layered alpha
surfaces and state-specific GUI imagery:

- `Client/gui/CGUIWindow_Impl.cpp`, commit
  `a750e5824f3a873a5110548678a67ca52e1bf739`
- `Client/core/Graphics/CGraphics.cpp`, same commit
- `Shared/data/MTA San Andreas/skins/Default 2023/CGUI.lnf.xml`, same commit

## Cursor

`OBSERVED_037 + STATIC_037 + PROBE_TRACE + USER_REQUESTED`:

- The original installation supplies a 32x32 `mouse.png`.
- A D3D hardware cursor can be accepted by Wine/Proton without being composed
  into the visible frame.
- The replacement therefore loads the installation's existing `mouse.png` and
  draws one textured backbuffer quad after the active UI branch. It does not
  commit or redistribute the proprietary asset.
- The old hand-built raster cursor was removed.
- The cursor is emitted once in the exclusive scoreboard branch and once in
  the normal overlay branch, never once per child overlay.
- Win32 `IDC_ARROW` is retained only as an explicit fallback when loading
  `mouse.png` fails.
- The user visually confirmed the result with: `cursor ist super`.

Run evidence:

- `artifacts/runs/20260728-165524-replacement-ui-1832907`
- `samp_runtime.log` records
  `ui_cursor: backbuffer texture initialized asset=mouse.png size=32x32
  render_sources=1`.

## Modal dialog input ownership

### Static R5 behavior

`STATIC_037 + GTA_REVERSED_REF`:

R5 cursor mode 2 does more than suppress keyboard mapping:

1. `samp.dll+0xA06FF..+0xA071A` patches GTA VA `0x541DF5`
   (`gta_sa.exe+0x141DF5`) from `E8 46 F3 FE FF` to five NOPs.
2. `samp.dll+0xA0580` patches GTA VA `0x53F417`
   (`gta_sa.exe+0x13F417`) from `E8 B4 7A 20 00` to five NOPs.
3. The same helper changes `0x53F41F..0x53F422` from
   `85 C0 0F 8C` to `33 C0 0F 84`.
4. Mode 2 zeros `0xB73424` and `0xB73428`, calls
   `CPad::ClearMouseHistory` at `0x541BD0`, then calls
   `CPad::UpdatePads` at `0x541DD0`.
5. It changes the first byte of `RsMouseSetPos` at `0x6194A0` from `E9`
   to `C3`.

The first patch suppresses only
`CControllerConfigManager::AffectPadFromKeyBoard`. Without steps 2-4,
`CPad::UpdateMouse` can still receive DirectInput mouse deltas and buttons
behind a modal Win32 overlay.

R5 close mode 0 with argument 0 arms a ten-tick countdown at
`samp.dll+0xA0861..+0xA0873`. At expiry, `samp.dll+0xA05D0` restores keyboard
and mouse bytes, performs:

```text
zero movement -> ClearMouseHistory -> UpdatePads
zero movement -> ClearMouseHistory
```

and only then restores `RsMouseSetPos` to `E9` and hides the D3D cursor.

### Replacement behavior

`STATIC_037 + PROBE_TRACE`:

- Both DirectInput patch sites are exact-byte validated before mutation.
- Saved bytes and ownership are tracked; changed third-party bytes are never
  overwritten during restore.
- Network dialogs and the local F1 help dialog acquire the same mode-2 gate.
- Active dialogs clear/update GTA mouse state on the game/render thread.
- Dialog close uses the R5 ten-tick delayed restore and the two-stage mouse
  history clear.
- The bullet-sync callback exits while the dialog gate owns mouse input, so a
  stale close-edge shot cannot produce `OnPlayerWeaponShot`.
- Chat mode 1 remains separate; it does not acquire the mode-2 DirectInput
  patch. Scoreboard mode 3 is also kept outside this dialog-specific change.

## Runtime validation

`PROBE_TRACE + OBSERVED_REPLACEMENT`:

Scenario:

1. Start the replacement at `127.0.0.1:7798`.
2. Spawn and open `/tpassword`.
3. Record transform and aim.
4. Hold `W`, inject four DirectInput mouse deltas of `(320, 120)`, hold/release
   RMB and LMB.
5. Record transform and aim while the dialog remains active.
6. Close with Escape, wait past the ten-tick restore, then repeat movement and
   mouse input.

Observed while open:

- GTA input call: `9090909090`
- position delta: `0.000000`
- ped-forward delta: `0.000000`
- aim-vector delta: `0.003751` after a total injected delta of `(1280, 480)`;
  this is ordinary sampled camera jitter, not the large rotation reproduced
  before the DirectInput patch
- no new server `OnPlayerWeaponShot`
- no new replacement `bullet_impact_hook: send`

Observed after Escape:

- GTA input call restored to `e846f3feff`
- subsequent `W` input moved the player `1.794591` units
- subsequent mouse delta changed the aim vector by `1.638225`
- runtime trace recorded `poll=1 result=1 flush=1`

Automated checks:

- `python3 -m unittest
  tools.reloop.test_dialog_cursor_input_lock_source_contract
  tools.reloop.test_ui_surface_style_source_contract -v`
- 24 focused cursor/dialog and UI-surface tests passed.
- Win32 DLL build completed successfully.
- The strict whole-PE identity checker still reports the longstanding
  section/import/entry-point structural differences; this UI change does not
  claim byte-identical PE layout.

## Open points

- Capture an original/replacement screenshot pair on native Windows if exact
  cursor hotspot or pixel filtering becomes relevant.
- R5 scoreboard cursor mode 3 also uses the DirectInput mouse gate while
  leaving keyboard movement enabled. That is a separate parity item and was
  intentionally not folded into the modal-dialog fix.
- One first-start attempt in the UI runner disconnected during preconnect; the
  automatic retry completed the full UI scenario. The disconnect occurred
  before the dialog patch path and was not reproduced by the final attempt.
