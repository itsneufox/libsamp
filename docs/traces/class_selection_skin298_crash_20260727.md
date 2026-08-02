# Class-selection skin 298 crash (2026-07-27)

## Scenario

- Replacement prefix:
  `/home/chairman/Games/san-andreas-multiplayer-legacy-libsamp`
- Server: local UFW, `127.0.0.1:7777`, 49 classes
- Original R5 DLL SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- Reproduction sequence: skin `45 -> 44 -> 45 -> 298`

## Failure evidence

`PROBE_TRACE`: the old replacement completed skin 45/44 changes, then stopped
after receiving skin 298. Instrumented reproduction narrowed the stop to:

1. opcode `0247` / `RequestModel(298)` returned;
2. opcode `038B` / global `LoadAllRequestedModels` never returned;
3. GTA consumed a CPU core until the process died.

The 290-299 special-character streaming slots have no normal DFF mapping in
this replacement run (`load_state=0`, `cd_size=0`). Calling the global blocking
loader after requesting one of those slots was therefore unsafe.

## Original R5 evidence

`STATIC_037`: R5 `CPlayerPed::SetModelIndex` at `samp.dll+0x9EF50` checks model
availability/RW state, requests an unavailable target and bounds its final
availability loop to 200 one-millisecond waits. Its caller at
`samp.dll+0xAFF82..+0xAFF9A` also patches GTA
`CClothes::RebuildPlayer` at `0x5A82C0` from `0x56` to `0xC3` immediately
before changing the local ped model. It does not apply that guard during GTA
startup.

## Replacement change

- Apply the observed GTA `0x5A82C0` guard lazily at the first SA-MP model
  change, after GTA has built the initial player clothes clump.
- Request only the selected target and let normal GTA streaming ticks finish
  it; never enter the unbounded global `038B` path from the graphics callback.
- Keep the R5 200 ms failure budget and leave an unavailable special slot
  unapplied instead of blocking/crashing.
- Keep the replacement square class-selection controls as the default.
  External R5 `sampgui.png` controls are opt-in through
  `SAMPDLL_CLASS_SELECTION_R5_TEXTURE=1`.

## Verification

- Candidate/install SHA256:
  `3746b0920ee3302b690d6d5cb323c536d981ae42b9488730bf4208ef6a9bb73b`
- `PROBE_TRACE`: the same UFW run reached skin 298 repeatedly, continued
  through skins 297, 296 and 295, and stayed responsive for the 120-second
  observation window without `exception_filter`.
- Normal skins 45 and 44 followed
  `requested -> loaded -> complete (applied=1)`.
- UI trace reported `class_selection ... texture=0`, confirming the square
  default.
- Host tests: 12/12 passed.

## Open parity point

The crash is closed, but visual parity for GTA special-character slots 290-299
is still open. They currently retain the last valid visible ped instead of
loading the original named special character. Reproduce R5's special-character
slot population before applying those models.
