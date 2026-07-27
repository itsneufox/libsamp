# Class selection and password-dialog parity (2026-07-27)

## Scope and binary identity

This note records the Windows pixel-pair and input-path checks for the
class-selection controls, native `CreateMenu`, and dialog style 3
(`DIALOG_STYLE_PASSWORD`).

- Original SA-MP 0.3.7-R5 `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- Replacement used for the integrated Windows observations:
  `c80b515100a66dafbaef6a0632383f5104a16697cea6c27ecc16ebf27adc8ac8`.
- Final locally built replacement after the password-panel reconstruction:
  `acb5edd84e5c634309d50cb68213dffd9d575ccb59fae454c66242df4977168b`.
- Integrated replacement run:
  `20260727_124112_integrated_ui_parity_47f5b927`.

The final hash was built but could not be deployed for a new Windows capture
because the remote execution approval was rejected. Claims about that last
visual patch are therefore explicitly marked `TODO_VERIFY`.

## Class-selection controls

`STATIC_037`:

- R5 constructs a 310x40 dialog at
  `samp.dll+0xC58B9..+0xC58EF`;
- it is horizontally centered and positioned 50 pixels above the bottom;
- the three controls are 90x30 at relative X positions 10, 110, and 210,
  all at relative Y 5;
- labels use bold Arial at nominal height 20;
- the controls use the `sampgui.png` atlas, including the source rectangle
  `[0,0,136,54]`.

The reconstruction is implemented without embedding the original asset. It
loads the already-installed `sampgui.png` from the GTA root and retains a
safe rectangular fallback if that external asset is missing or cannot be
created as a D3D texture.

`OBSERVED_037 + PROBE_TRACE`:

- original reference:
  `artifacts/runs/windows-altenter-original/20260727_122006_altenter_original_r5_30444d85`;
- replacement burst:
  `20260727_124140_685_class-selection-integrated` in the integrated run.

At 800x600, the reconstructed backing strip, rounded left/right/Spawn
controls, positions, sizing, and labels visually match the original capture.
The earlier plain outlined-button presentation gap is therefore closed for
the default 800x600 class-selection state. Hover/pressed frames and
non-800x600 scaling remain separate runtime checks.

## Native menu input and harness correction

The integrated run also confirmed the native GTA panel path. The first
synthetic arrow attempts selected row 0 because the lab helper did not emit
extended-key scan codes. The helper now uses held `keybd_event` input and the
correct extended scan codes for the arrow keys.

`PROBE_TRACE`:

- pressing `S`, then `Space`, selected row 1;
- pressing extended `Down`, then `Space`, selected row 1 again;
- the open.mp log recorded
  `OnPlayerSelectedMenuRow ... row=1 ... item=Test2` for both attempts.

This closes the apparent Windows RPC 132 regression: it was a test-harness
false negative, not a replacement menu-latch defect. RPC 140 `MenuQuit`,
two-column navigation, and disabled rows remain `TODO_VERIFY`.

## Password masking and response bytes

The same fixture displayed dialog ID 31903 with style 3.

`OBSERVED_037 + PROBE_TRACE`:

- original reference:
  `artifacts/runs/windows-password-original/20260727_122833_password_original_r5_73c57432`;
- replacement burst:
  `20260727_125045_614_password-replacement-masked` in the integrated run;
- both clients displayed eight mask glyphs for the eight-byte input
  `p4rity42`;
- the replacement rendered an insertion caret and never displayed the clear
  password in the screenshot;
- Enter produced a normal dialog response with
  `dialog=31903 response=1 listitem=-1 input_len=8`;
- the server received the exact clear payload `p4rity42`.

The mask display and RPC 62 payload path are therefore functionally covered.
The clear value appears only in the deliberately instrumented local server
log used by this fixture. The replacement runtime trace now records only the
password length and `masked=1`, never the clear dialog input.

## Password-dialog pixel gap and reconstruction

The integrated replacement hash still used the old generic dialog panel. The
pixel pair showed concrete differences:

- the replacement body was wider than the roughly 230x130 original;
- its edit control had a square border;
- its buttons were flat/generic instead of using the rounded `sampgui.png`
  skin;
- caption/body spacing differed.

The final local source now reconstructs the observed 230-pixel minimum input
layout, 40-pixel edit control, 96x26 buttons, dark uniform panel, Arial body
font, bold 20-pixel input/button font, circular mask glyphs, two-pixel caret,
and external `sampgui.png` edit/button skins. D3D resources are released with
the existing dialog/chat reset path. Server-sized text is bounded to the
current viewport, button activation requires press and release on the same
control, and `WM_KILLFOCUS` clears a pending dialog press without closing the
dialog.

Evidence for those constants is `OBSERVED_037`; the implementation mapping is
`INFERRED + TODO_VERIFY` until a Windows capture using final DLL
`acb5edd84e5c634309d50cb68213dffd9d575ccb59fae454c66242df4977168b`
is compared against the original golden.

## Checks

- Final Win32 build: pass.
- Host C/C++ tests: 12/12 pass.
- Lifecycle Python tests: 4/4 pass.
- `git diff --check`: pass.
- Strict PE shape still has the known replacement/original section, import,
  TLS, and entry-point differences; this work does not claim binary-shape
  identity.
