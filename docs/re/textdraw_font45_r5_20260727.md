# SA-MP 0.3.7-R5 TextDraw Font 4/5

Date: 2026-07-27

## Reference builds

- `samp.dll` 0.3.7-R5:
  SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- GTA San Andreas 1.0 US:
  SHA256 `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`

All offsets below are RVAs relative to the R5 `samp.dll` unless an absolute
GTA-SA 1.0 US address is explicitly named.

## Layout

`STATIC_037`:

- The packed TextDraw transmit payload is `0x3f` bytes.
- The R5 `CTextDraw` object is `0x9d6` bytes.
- Relevant object offsets:
  - style `+0x987`
  - x/y `+0x98b` / `+0x98f`
  - shared cache index `+0x9a3`
  - selectable `+0x9a7`
  - preview model `+0x9a8`
  - preview rotations `+0x9aa`, `+0x9ae`, `+0x9b2`
  - preview zoom `+0x9b6`
  - preview colours `+0x9ba`, `+0x9bc`
  - rendered-bounds valid `+0x9bf`
  - rendered bounds `+0x9c1`, `+0x9c5`, `+0x9c9`, `+0x9cd`
  - hover flag/colour `+0x9d1` / `+0x9d2`

## Font 4: sprite TextDraws

`STATIC_037` helper map:

- shared 200-entry cache init: `+0x000b2af0`
- allocate/free cache index: `+0x000b2b20` / `+0x000b2b50`
- ensure/load TXD: `+0x000b2b90`
- read texture: `+0x000b2c60`
- sprite draw wrapper: `+0x000b2ca0`
- parse/load `library:texture`: `+0x000b2cd0`
- edit text: `+0x000b2f60`
- cached quad and rendered-bounds latch: `+0x000b3090`
- cached/non-cached dispatch: `+0x000b3480`

The parser requires a colon, rejects total strings with length `>= 64`, and
rejects both path separators. Its library matches are case-sensitive:

- `hud:texture` uses GTA's existing `hud` TXD slot.
- `samaps:texture` ensures `SAMP\samaps.txd`.
- `vehicleprev:texture` ensures slot `vehicleprev` from
  `SAMP\vehicles128.txd`.
- `mdl<decimal>:texture` resolves through R5's custom-model download manager
  and its uppercase hexadecimal hash slot.
- Other libraries use the first ten library bytes as the TXD slot name and
  load `models\txd\<full-library>.txd`.

The draw wrapper sets RenderWare state 9 to 2 and invokes GTA
`CSprite2d::Draw` at `0x728350`. The quad is exactly
`x, y, x + lineWidth, y + lineHeight`, scaled through GTA's 640x448 HUD
factors; centre/right alignment flags do not move it. Missing textures draw
nothing, but the rendered bounds are still latched.

The replacement now follows that native CTxdStore/RwTexture/CSprite2d route,
keeps the resources across D3D reset like R5, and releases them on TextDraw
replacement/hide, session reset and module shutdown. `mdl` lookup remains
`TODO_VERIFY` because the replacement does not yet expose the R5
download-manager hash contract.

## Font 5: model previews

`STATIC_037`:

- preparation/dispatch starts at `+0x000b34a0`;
- CPedModelInfo (`0x85bdc0`) dispatches to `+0x0006c140`;
- vehicle IDs 400..611 dispatch to `+0x0006c3c0`;
- other supported model-info types dispatch to `+0x0006c9b0`;
- every preview is first rendered into a 256x256 cache and later drawn by the
  same cached-quad path as Font 4.

Recovered special cases now mirrored by the replacement:

- ped model 162 uses Z 50.15; other ped previews use Z 50.05;
- vehicle 570 maps to 538 and 569 maps to 537;
- GTA `CTrain` (`0x8721a0`, R5 wrapper type 4) uses
  `Y = -5.5 - 2.5 * collisionRadius` and ignores transmitted zoom;
- generic models 1373, 3118, 3552 and 3553 map to model 18631;
- generic model 18631 ignores transmitted rotations and receives a fixed
  180-degree Z rotation;
- cached Font 5 composition now uses the TextDraw letter colour or active
  selection colour instead of unconditional white.

The current replacement still renders a raw ped clump instead of constructing
R5's temporary `CPlayerPed` wrapper, and its cached texture composition is a
state-preserving D3D9 quad rather than the exact R5 wrapper. Those are
`TODO_VERIFY` parity gaps.

## Selection and bounds

`STATIC_037`:

- A selectable TextDraw is not hit-testable until its first rendered-bounds
  latch.
- R5 scans all active IDs in ascending order for hover state, so every
  overlapping selectable TextDraw receives the selection colour.
- The highest overlapping ID is the click RPC winner.

The replacement now stores rendered bounds per slot, requires that latch for
clicks, applies hover colour to every overlap (including Font 4/5), and retains
the highest-ID click winner.

## Deliberate safety differences and open checks

- R5 has a cache-full path which can index the shared array with `-1`. The
  replacement deliberately does not reproduce that unsafe write.
- The replacement currently owns resources per TextDraw slot rather than
  enforcing R5's global 200-entry Font 4/5 cache limit.
- Invalid/non-resident generic models outside the four observed remaps do not
  yet reproduce every R5 fallback path.
- `OBSERVED_037`/`PROBE_TRACE` runtime comparison is still required for the
  newly implemented native Font 4 path, hover overlap, train preview and
  special generic fallback. This change is statically evidenced but has not
  yet been visually validated.
