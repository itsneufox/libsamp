# Windows CreateMenu and chat pixel pair (2026-07-27)

## Scope

This note records a native-Windows 800x600 comparison of the same
`/menutest` fixture with original SA-MP 0.3.7-R5 and the replacement.

- Original R5 `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- Replacement used for the first pixel pair:
  `341956316018663d5f6a15850fefb28197469a3e509f6677c684b5390d378a2a`.
- Original artifact:
  `artifacts/runs/windows-menu-original/20260727_110452_menu_original_pixel_145c2e61/`.
- Replacement artifact:
  `artifacts/runs/windows-menu-replacement-final/20260727_115222_menu_replacement_pixel_53ae1513/`.

The server, resolution, spawn location, menu contents, and GTA SA 1.0 US
executable were shared between both runs.

## CreateMenu result

`OBSERVED_037 + PROBE_TRACE`:

- panel origin, size, alpha, title position, row positions, selected-row
  styling, GTA texture, and six-row geometry match visually;
- this corroborates the `STATIC_037` result that R5 `CMenu::Show` at
  `samp.dll+0xA7740` delegates presentation to GTA's stock panel opcodes;
- the replacement therefore keeps the native GTA panel as the normal path.

The first Windows `SPACE` injection closed the replacement panel but produced
no server-side `OnPlayerSelectedMenuRow` record. Earlier Proton runs did send
RPC 132 correctly. The Windows harness used a momentary `WScript.SendKeys`
pulse, which can be consumed by GTA's panel between two replacement process
callbacks. The harness now holds virtual-key SPACE for 100 ms. Treat the first
Windows result as an input-sampling gap until the held-key rerun is complete,
not as proof that RPC 132 is generally absent.

### Held-key rerun

`PROBE_TRACE` in integrated Windows run
`20260727_124112_integrated_ui_parity_47f5b927`:

- held `S`, then held `Space`, selected row 1 (`Test2`);
- after adding the required extended-key flag and scan code to the lab helper,
  held `Down`, then held `Space`, also selected row 1;
- the server recorded RPC 132 through
  `OnPlayerSelectedMenuRow ... row=1 ... item=Test2` for both attempts.

The earlier row-0 result was therefore a harness false negative. The native
panel selection latch and outgoing RPC 132 are covered on Windows.

## Chat gap and static reconstruction

The pixel pair exposed a separate replacement-only geometry error: chat began
around X=30/Y=145 with an 18-pixel row step and overlaid the menu title. R5
began at the top-left chat page and left the menu unobstructed.

`STATIC_037` at `samp.dll+0x67940`:

- initial chat RECT top is `10`;
- initial left is `45`;
- right is `550`;
- initial bottom is `110`;
- object offset `+0x63E2` stores the D3DX-measured height of `"Y"`;
- each subsequent row advances by that measured height plus one pixel;
- the renderer iterates the complete configured page, so leading empty slots
  consume rows and visible messages remain bottom-anchored.

`OBSERVED_037` in the 800x600 original capture corroborates the default
15-pixel row step. The replacement now uses X=45/Y=10, a default 15-pixel
step, full-page empty-slot accounting, and positions chat input beneath the
complete page rather than beneath only the non-empty messages.

The pair also showed one missing replacement startup line:
`Connected to open.mp server`. Legacy 0.2x InitGame code formats
`Connected to %.64s` from the RPC 139 hostname, and the R5 capture shows it
immediately after `Connected. Joining the game...`. The replacement now emits
that hostname line in the same order.

The corrected integrated run also confirms the reconstructed R5 chat origin,
15-pixel row step, full-page bottom anchoring, and startup hostname line in
the same 800x600 view as the native menu. The panel is no longer obscured by
the replacement chat.

## Remaining checks

- Exercise ButtonTriangle/default Enter or F and require RPC 140
  `MenuQuit`.
- Compare two-column menus and disabled-row navigation.
- Keep the D3DX fallback marked `TODO_VERIFY`; native GTA panels are the
  parity path.
