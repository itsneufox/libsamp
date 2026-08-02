# Local-ped clothes visibility parity (2026-07-27)

## Scope

- Original SA-MP 0.3.7-R5 DLL SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- GTA executable SHA256:
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`
- Replacement prefix:
  `/home/chairman/Games/san-andreas-multiplayer-legacy-libsamp`
- Scenario: local skin 0, automatic spawn, labels fixture

## Observed failure

`PROBE_TRACE`:

- The local `CPlayerPed` existed and continued to synchronize.
- The weapon rendered at the correct local-ped transform, but the body did not.
- Both GTA render gates were already open:
  - `CPed+0x474 bit 1` (`bDontRender`) was `0`;
  - `CEntity+0x1C bit 7` (`m_bIsVisible`) was `1`.
- The model-0 RenderWare clump was valid and had a render-enabled atomic, but
  its only geometry contained just 2 triangles and 6 vertices. This is GTA's
  undressed `MODEL_PLAYER` placeholder, not the constructed CJ body.

Evidence:

- Trace artifact:
  `artifacts/runs/20260727-175501-replacement-labels-744129`
- Visual artifact:
  `artifacts/runs/20260727-174914-replacement-labels-736458/screenshots/manual-ped-invisible.png`

The old 0.2x `CPlayerPed::SetVisible` implementation calls `CPed+0x474 bit 3`
a visibility flag. GTA 1.0 US static analysis shows that bit is not a render
gate; forcing it is therefore not part of this fix.

## Original lifecycle evidence

`STATIC_037`:

- `CLocalPlayer::HandleClassSelection` at `samp.dll+0x4080` calls the
  `CPlayerPed::SetInitialState` wrapper at `+0x4098`.
- The wrapper at `samp.dll+0xABBD0` calls GTA
  `CPlayerPed::SetInitialState` at `0x60CD20` with player number 0.
- `CLocalPlayer::Spawn` at `samp.dll+0x3C20` calls the same wrapper on
  non-first spawns, refreshes streaming, calls `RestartIfWastedAt`, then calls
  `CPlayerPed::SetModelIndex` at `+0x3D32`.
- `CPlayerPed::SetModelIndex` at `samp.dll+0xAFF82..+0xAFF9A` patches GTA
  `CClothes::RebuildPlayer` at `0x5A82C0` from `0x56` to `0xC3` immediately
  before the first SA-MP model change.
- R5 does not arm that guard during startup.
- The bundled `main.scm` contains opcode `070D BUILD_PLAYER_MODEL`, whose GTA
  handler needs `CClothes::RebuildPlayer` to construct the initial CJ clump.

## Root cause and fix

The replacement armed the `0x5A82C0 -> RET` guard in its early entry-gate-7
patch batch. `BUILD_PLAYER_MODEL` therefore became a no-op and left the local
ped with the 2-triangle placeholder.

The replacement now:

1. leaves `CClothes::RebuildPlayer` intact during GTA startup;
2. mirrors the R5 `SetInitialState` class-selection transition once per spawn
   info sequence;
3. arms the byte-validated `0x56 -> 0xC3` clothes guard lazily inside the
   direct R5 `SetModelIndex` path;
4. keeps the guard idempotent when the byte is already `0xC3`;
5. rejects an unexpected third-party byte instead of overwriting it blindly;
6. records clump/atomic/geometry diagnostics for future model regressions.

## Validation

`PROBE_TRACE`:

- Visually captured fixed build SHA256:
  `ce3520985a567d3668202237cd3ea6e08f78601d3a0317ccb093ea4fb248e87d`
- Fixed artifact:
  `artifacts/runs/20260727-175757-replacement-labels-748814`
- Lazy guard marker:
  `0x5A82C0 0x56 -> 0xC3`
- Fixed clump:
  1 render atomic, 3184 triangles, 2202 vertices
- Server fixture:
  2 passes, 0 failures, 2 visual observations
- No `exception_filter` marker
- Visual capture:
  `artifacts/runs/20260727-175757-replacement-labels-748814/screenshots/manual-ped-visible.png`

`PROBE_TRACE` visual result: the full CJ body, clothes, and attached weapon
render together after spawn.

The final terminology-only rebuild SHA256 is
`6e26be521f6e3f2a9b464fe6af5d713106628d26db8d932cc026c50ca336a915`.
The full regression artifact
`artifacts/runs/20260727-180200-replacement-all-754589` completed 11 passes,
0 failures, and 11 visual observations. Its trace retained the 3184-triangle
CJ clump, changed skin `0 -> 287 -> 0` through RPC 153, and rebuilt the full
model-0 clump on the return transition without an exception marker.

## Remaining checks

`TODO_VERIFY`:

- Repeat the lifecycle through death/respawn and F4 class selection.
- Include the lazy clothes guard in a GMX/reconnect stress pass.
- Compare a non-model-0 skin and a subsequent RPC 153 skin transition against
  an original R5 trace.
