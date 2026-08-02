# TAB, chat, TextDraw cursor, and focus latch audit (2026-07-27)

## Scope and evidence

This pass audits the replacement's Win32 input ownership around TAB,
chat input, selectable TextDraws, focus loss, and the GTA frontend menu.

Reference binary:

- SA-MP 0.3.7-R5 `samp.dll`
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`

All original-DLL claims below are `STATIC_037` unless explicitly tagged
otherwise. No original or replacement runtime was started for this pass.

## SelectTextDraw state machine

The incoming RPC 83 registration is at `samp.dll+0x1E6BF` and points to the
handler at `samp.dll+0x1D650`. The selector object has the following relevant
methods:

- `samp.dll+0x71440` enables selection, stores the hover color, and initializes
  the hovered TextDraw ID to `65535`;
- `samp.dll+0x71480` sends the currently hovered ID through RPC 83 and does not
  clear selection;
- `samp.dll+0x71520` first clears selection/cursor ownership, sets the hovered
  ID to `65535`, and then sends that cancel sentinel;
- `samp.dll+0x71570` handles `WM_LBUTTONUP`; it sends only when the hover ID is
  not `65535`, but consumes the release while selection is active.

The WndProc at `samp.dll+0x61650` implements Escape as a two-message sequence:

1. active selection consumes `WM_KEYDOWN/VK_ESCAPE` at
   `samp.dll+0x61A7C`;
2. `WM_KEYUP/VK_ESCAPE` calls the cancel method at
   `samp.dll+0x6198B..+0x619A8` and is also consumed.

The previous replacement cleared selection after every successful TextDraw
click and chained Escape key-down to GTA. That could end a multi-click
selection prematurely and could open GTA's pause menu while cancelling.

The replacement now:

- keeps selection and cursor ownership after ordinary TextDraw clicks;
- consumes `WM_LBUTTONUP` and submits a valid hovered ID without requiring a
  preceding delivered button-down, matching `samp.dll+0x71570`;
- consumes both Escape phases;
- sends ID `65535` and clears selection on Escape key-up;
- clears the adapter's selection snapshot for a cancel even if the network
  send fails, matching the original clear-before-send order.

The server-driven cancel path is also connected: incoming RPC 83 with
`active=0` clears the adapter state, and
`textdraw_compat_update_from_snapshot()` then clears the runtime selector and
cursor on the next snapshot.

## TAB scoreboard

`PROBE_TRACE` in `docs/re/ui_interaction_loop_20260718.md` established that
plain TAB in R5 leaves GTA's input call intact and allows movement. The
replacement's display-only TAB path follows that observation. Right mouse
button remains the explicit cursor/input mode trigger used by the existing
interaction fixture.

On `WM_KILLFOCUS`, R5 closes an open scoreboard at
`samp.dll+0x61B75..+0x61B87`. The replacement additionally latches a physical
TAB held across focus return until it is released. That latch is `INFERRED`:
the original owns an explicit scoreboard-visible state, while the replacement
derives visibility by polling TAB. It prevents an immediate replacement-only
reopen, but still needs a focus-loss runtime pair.

## Chat

The R5 chat input object is referenced through `samp.dll+0x1026EB84`; its
active field is at object offset `+0x14E0`. Open and close are
`samp.dll+0x69480` and `samp.dll+0x69580`.

The character-message helper at `samp.dll+0x61590` opens inactive chat for
`T`, `t`, or the backtick character. The key helper at `samp.dll+0x61360`
maps F6 to the same open/close toggle. Thus the replacement's `WM_CHAR`
opening and F6 key-up toggle are structurally consistent with R5; a
replacement-only chat latch defect was not established statically.

R5 forwards each window message to the chat object handler at
`samp.dll+0x697D0` before its outer WndProc dispatch. When chat is active, the
WndProc also routes messages through its GUI dialog at
`samp.dll+0x616E5..+0x6171A`. The static input helper at
`samp.dll+0x8C840` explicitly handles `WM_INPUTLANGCHANGE`,
`WM_IME_STARTCOMPOSITION`, and `WM_IME_COMPOSITION`.

The replacement currently implements only a bounded printable-ASCII editor
plus history. It consumes Left, Right, Home, and End without moving a caret and
does not implement IME composition. Those are concrete editor-parity gaps;
the exact R5 clipboard shortcuts, selection rules, and held-key repeat behavior
remain `TODO_VERIFY`.

## Focus and GTA pause menu

The R5 `WM_KILLFOCUS` branch at `samp.dll+0x61B75..+0x61BCC` closes the
scoreboard, closes active chat, releases class-selection mouse ownership, and
chains to GTA. It does not close a dialog or cancel SelectTextDraw. The
replacement now preserves those two states on focus loss.

R5 uses `CGame::IsMenuActive` (`samp.dll+0xA0920`) to gate UI handlers and
skips its overlay render block when the frontend menu is active
(`samp.dll+0x7576D`). A static call scan found no menu-active path to the
TextDraw cancel method at `samp.dll+0x71520`.

The replacement still closes chat and cancels TextDraw selection whenever its
WndProc observes the GTA menu active. That behavior is `INFERRED` and is the
highest-risk unresolved ownership difference in this audit. It should not be
removed without an original/replacement controller-pause and external-menu
runtime pair, because keyboard Escape is normally consumed before the menu can
open while either UI owns input.

## Remaining runtime matrix

1. SelectTextDraw: click two selectable items without a new SelectTextDraw RPC;
   require two RPC 83 responses while the cursor remains visible.
2. SelectTextDraw: Escape down must not open pause; Escape up must emit exactly
   one ID `65535` and hide the cursor.
3. Server cancel: send SelectTextDraw false without client input; require
   selector/cursor teardown.
4. Focus: hold TAB, lose focus, regain focus while TAB is still down, then
   release and press TAB again.
5. Focus: repeat with chat, dialog, TextDraw selection, and class selection;
   require the R5 ownership outcomes above.
6. Pause: compare keyboard Escape, controller Start, and an externally opened
   frontend menu while chat or TextDraw selection is active.
7. Mouse edge case: runtime-confirm that `WM_LBUTTONUP` over a selectable
   TextDraw without a preceding delivered down emits the hovered RPC 83. The
   replacement now mirrors R5's statically recovered no-latch path; a paired
   runtime trace remains `TODO_VERIFY`.
8. Chat: compare held T, F6, key repeat, Home/End/Left/Right, clipboard,
   non-ASCII input, and focus loss.
