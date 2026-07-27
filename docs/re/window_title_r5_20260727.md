# R5 game-window title parity (2026-07-27)

## Runtime observation

`OBSERVED_037 + PROBE_TRACE` from the native-Windows Alt+Enter pair:

- original:
  `artifacts/runs/windows-altenter-original/20260727_122006_altenter_original_r5_30444d85`;
- replacement:
  `artifacts/runs/windows-altenter/20260727_121645_altenter_no_windowedmode_12fff7fa`.

After fullscreen-to-windowed mode, the original process reports and visibly
draws the title `GTA:SA:MP`. The replacement reports GTA's stock
`GTA: San Andreas`. Both `processes.json` and `last_collection.json` preserve
the same difference.

Original reference:

- SA-MP 0.3.7-R5 `samp.dll`;
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.

## Static R5 path

`STATIC_037`:

- `SetWindowTextA` is imported through IAT RVA `samp.dll+0xE53BC`;
- the exact zero-terminated title starts at `samp.dll+0xE98E4`;
- the R5 game-window setup helper starts at `samp.dll+0x61EF0`;
- it reads GTA's HWND from VA `0xC97C1C`, enables class-style bit `0x8`,
  installs the R5 WndProc through the helper at `samp.dll+0x61EC0`, and then
  calls `SetWindowTextA(hwnd, "GTA:SA:MP")` at
  `samp.dll+0x61F3F..+0x61F4B`;
- the one-time startup routine at `samp.dll+0xC4790` calls this helper at
  `samp.dll+0xC482C`, after its preceding runtime initialization and before
  construction of the main client objects beginning at `samp.dll+0xC4831`.

The other direct `SetWindowTextA` call at `samp.dll+0x934B7` receives a
dynamically produced string and belongs to the bundled window/dialog utility.
It is not the fixed SA-MP game-title path. The import thunk at
`samp.dll+0xC5DE8` likewise adds no separate title behavior.

R5 writes the title once during startup; the Alt+Enter runtime pair shows that
GTA's video-mode transition retains it.

## Replacement behavior

The replacement now applies the exact title when its existing window setup
first observes a valid GTA HWND. Application is:

- restricted to online/SA-MP startup;
- checked for Win32 failure;
- latched once per HWND, rather than rewritten every frame;
- traced with the static RVAs above.

This placement is the replacement equivalent of the R5 startup window helper
and remains independent of the optional WindowedMode ASI.

## Checks and remaining runtime proof

- Original import, string, direct Xrefs, helper call order, and binary hash
  were checked statically.
- `git diff --check` is required after integration.
- No build or runtime was started for this focused patch.
- The next native-Windows Alt+Enter replacement run must require
  `main_window_title == "GTA:SA:MP"` before and after both video-mode
  transitions.
