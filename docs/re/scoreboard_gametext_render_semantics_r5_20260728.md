# Original-R5 scoreboard and GameText render semantics

Date: 2026-07-28

Status: `STATIC_037 + PROBE_TRACE`. The Original-R5 claims below remain based
on static control flow; the final section separately records replacement and
transport probes without promoting them to direct Original-R5 memory
observations.

## Binary identity

Analyzed original SA-MP 0.3.7-R5 binary:

- file: `artifacts/binaries/samp_installer.dll`;
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- preferred base: `0x10000000`.

All addresses below are module-relative RVAs.

## Scoreboard is an exclusive render branch

`STATIC_037`:

The main R5 render routine starts at `samp.dll+0x75730`. Its scoreboard branch
is controlled by the raw scoreboard-visible DWORD:

1. `samp.dll+0x7593A` loads the scoreboard object pointer.
2. `samp.dll+0x7593F` compares the DWORD at `CScoreboard+0x0` with zero.
3. When it is nonzero, `samp.dll+0x75944..+0x7594C` calls
   `CGame::DisplayHud(0)` at `samp.dll+0xA1DB0`.
4. `samp.dll+0x75951..+0x75957` calls `CScoreboard::Draw` at
   `samp.dll+0x6F0B0`.
5. `samp.dll+0x7595C` unconditionally jumps to the shared tail at
   `samp.dll+0x75C65`.

That jump bypasses the normal overlay block. In particular, it skips:

- `Chat::Draw` at the call site `samp.dll+0x75A81`, targeting
  `samp.dll+0x67E00`;
- `ChatInput::Draw` at the call site `samp.dll+0x75A90`, targeting
  `samp.dll+0x696F0`.

The compatibility consequence is exact: while the raw scoreboard-visible
latch is nonzero, R5 hides the GTA HUD and renders the scoreboard instead of
the chat text and chat-input overlay. The chat and chat-input draw calls are
not merely placed behind the scoreboard; they are not executed for that
frame.

The scoreboard branch contains no chat-buffer clear or chat-input state
transition. Static control flow therefore proves render suppression, not chat
state destruction. Whether any separate path mutates chat state during the
same frame remains `TODO_VERIFY`; the replacement must not infer such a clear
from this render branch.

## Every accepted GameText globally clears the preceding text

`STATIC_037`:

`CGame::DisplayGameText` starts at `samp.dll+0xA0CE0`. For calls that pass its
initial upper-bound guard, the function performs the following sequence:

1. `samp.dll+0xA0CEC` pushes the script-command descriptor at
   `samp.dll+0xEC724` and calls the script-command bridge at
   `samp.dll+0xB2310`.
2. The descriptor begins with bytes `BE 00`, the little-endian GTA script
   opcode `0x00BE`, `text_clear_all`.
3. Only after that global clear does the function copy and sanitize the new
   text.
4. The new GameText dispatch begins at `samp.dll+0xA0D3E`; the actual call at
   `samp.dll+0xA0D4F` targets GTA address `0x0069F2B0` with text, duration,
   and style/size arguments.

RPC 73 enters this same path:

- the RPC 73 handler starts at `samp.dll+0x198F0`;
- after decoding and validating its payload, its call site at
  `samp.dll+0x199C8` invokes `CGame::DisplayGameText` at
  `samp.dll+0xA0CE0`.

Consequently, a newly accepted RPC 73 GameText replaces all currently active
GTA game text, including text in a different style slot. R5 does not maintain
independently overlapping GameText entries for successive RPC 73 messages:
the `text_clear_all` command runs before every accepted new message is
installed.

This evidence does not yet establish the exact runtime result for rejected
payloads, empty strings, zero durations, or extension-specific hide
semantics. Those cases remain `TODO_VERIFY` and must not be generalized from
the proven accepted-message path.

## Replacement verification

### Exclusive scoreboard overlay

`PROBE_TRACE`:

- replacement build SHA256:
  `5f57901401f6d3c337f5c241ea33c1b66842497f449011c7f703f0d74e0d7dfe`;
- run:
  `artifacts/runs/20260728-154547-replacement-ui-1741171`;
- the latched scoreboard kept `HUD=0` and `radar_blank=1` while the interaction
  driver retained normal GTA movement/input;
- runtime line 899 recorded ten buffered chat lines together with
  `normal_overlay_draws=0` in the exclusive scoreboard branch.

The chat state was therefore retained but not rendered. The focused
interaction analyzer passed every scoreboard state check except the optional
server-side RPC 23 click observation.

### Global GameText replacement

The closed fixture in `tools/openmp_rpc73_gametext_fixture/` bypasses
open.mp's GameText-to-TextDraw compatibility conversion and sends two fixed
raw RPC 73 payloads. Fixture SHA256:
`494b1cd647654cd13b2451f80a6e31a13b4c26304bcb2c89fa09980f8243ab51`.

`PROBE_TRACE` run:
`artifacts/runs/20260728-155306-replacement-pvars-1747209`.

The observed sequence was:

1. server lines 180/182 sent style 5 and style 3 with `sent=1`;
2. network lines 495/496 decoded the first raw RPC 73 and lines 518/519 the
   second;
3. runtime line 825 installed style 5;
4. runtime line 830 cleared one active GameText before the replacement;
5. runtime line 831 installed style 3.

`tools/reloop/analyze_gametext_r5.py` evaluates this fixed golden run as
`PASS` with all 13 checks true and no `exception_filter`.

For transport comparability, Original-R5 run
`artifacts/runs/20260728-155657-original-pvars-1750341` used the original DLL
hash above and received the same two fixed raw payloads from the server. Its
hash-guarded screenshot request was observed, but no image file was produced;
pixel evidence therefore remains `TODO_VERIFY`. The global replacement claim
itself is already fixed by the Original-R5 `text_clear_all` control flow
documented above.
