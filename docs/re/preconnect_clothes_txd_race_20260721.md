# Pre-connect clothes/TXD race (2026-07-21)

## Scope

- Replacement prefix: `/home/chairman/Games/san-andreas-multiplayer-legacy-libsamp`
- GTA executable SHA256: `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`
- Fixed replacement DLL SHA256: `01190be87e2a92e52aa1ef069ba54e6b47d7eed719b0aa512afbe86374f5aa24`
- Scenario: ReLoop replacement startup against the local open.mp fixture

## Failure

`PROBE_TRACE + STATIC_037 + GTA_REVERSED_REF`:

- Runs `20260721-190123-replacement-all-171870` and
  `20260721-190135-replacement-all-171870` faulted at `gta_sa.exe+0x003F39FB`
  (`0x007F39FB`) while reading address `0x00000008`.
- Both register captures had `EAX=0x00000008` and `ESI=0x00000000`.
- The return address `0x005A6116` identifies the first
  `RwTexDictionaryFindNamedTexture` call inside
  `CClothesBuilder::ConstructTextures` (`0x005A6040`). GTA had obtained a null
  source clothes TXD from the TXD pool and passed it to the RenderWare lookup.
- No RakNet connection had started. This was GTA startup/streaming state, not a
  server packet or the separately observed IPL fault at `0x00405E15`.

Reference mappings:

- `RwTexDictionaryFindNamedTexture`: gta-reversed `rwcore.cpp`, address
  `0x007F39F0`.
- `CClothesBuilder::ConstructTextures`: gta-reversed `ClothesBuilder.cpp`,
  address `0x005A6040`.

## Rejected mitigation

`PROBE_TRACE`:

A 500 ms delay before the forced `entry=9` transition did not solve the
problem. Runs `20260721-191052`, `20260721-191110`, and `20260721-191128`
still terminated during pre-connect; `20260721-191110` exposed an additional
GTA cleanup fault at `gta_sa.exe+0x001380AF`. A pre-transition sleep only moved
the race and was not retained as the fix.

The first game-thread handoff change removed concurrent GTA-mutating
`apply_preconnect_frontend_compat()` calls from the monitor thread. That change
is retained because GTA streaming and script commands must remain on the game
thread, but run `20260721-192025-replacement-pvars-183473` reproduced the
original `0x007F39FB` fault and proved that handoff alone was insufficient.

## Fix

`PROBE_TRACE + GTA_REVERSED_REF + INFERRED`:

1. Once the graphics callback is active, the monitor thread no longer calls
   the GTA-mutating pre-connect path. It remains only a pre-hook fallback.
2. After `entry 8->9` / `game_started 1->0`, the replacement gives GTA 1000 ms
   of normal game-thread frames before issuing its own Santa Maria
   `CStreaming::LoadScene` and script-camera operations. This avoids competing
   with the local player's clothes/TXD construction window.
3. The post-transition interval is configurable through
   `SAMPDLL_PRECONNECT_LOADED_SETTLE_MS` (0..10000 ms); the compatibility
   default is 1000 ms.

The gate logs:

```text
preconnect_bridge: settling loaded GTA before scene load elapsed_ms=0/1000 ...
preconnect_bridge: monitor handed GTA mutations to graphics callback ...
```

## Validation

`PROBE_TRACE`:

Seven fresh starts passed consecutively with no `exception_filter` or probe
`exception:` marker:

- PVars (`3 passes, 0 failures` each): `20260721-192718`, `192828`, `192910`,
  `192952`, `193034`, and `193117`.
- Full `all` scenario: `20260721-193213-replacement-all-188928`,
  `11 passes, 0 failures`, with 9 expected visual-review observations.

The built and installed DLL hashes matched after deployment.

## Remaining risk

`TODO_VERIFY`:

The exact original 0.3.7 readiness condition for clothes/TXD completion is not
yet statically identified. The 1000 ms post-transition gate is backed by the
failure window and repeated runtime validation, but it remains a conservative
timing gate rather than an original-DLL semantic marker.
