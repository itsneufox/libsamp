# Direct scene-streaming hang fix (2026-07-27)

## Binary evidence

- Original SA-MP 0.3.7-R5 `samp.dll` SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
- GTA SA 1.0 US routines:
  - `CStreaming::LoadAllRequestedModels`: `0x40EA10`;
  - `CStreaming::LoadScene`: `0x40EB70`;
  - `CStreaming::LoadSceneCollision`: `0x40ED80`.

`STATIC_037`: an instruction scan of the complete original DLL finds no
reference to `0x40EB70` or `0x40ED80`. The only `0x40EA10` reference is the
`mov edx, 0x40EA10` at `samp.dll+0xA0A6A`, in a dedicated model-request/load
helper.

## Runtime evidence

`PROBE_TRACE`:

- `20260727-165414-replacement-ui-680318` stopped after
  `reason=preconnect step=LoadScene phase=begin`.
- `20260727-165627-replacement-ui-680318` and
  `20260727-170425-replacement-labels-688825` stopped after
  `reason=preconnect step=LoadSceneCollision phase=begin`.
- `20260727-170626-replacement-labels-688825` completed ClientJoin and
  ScrInitGame, then stopped after `reason=spawn step=LoadScene phase=begin`.
- No run emitted `exception_filter`; the probe heartbeat continued while the
  GTA/render thread remained blocked.
- Successful controls with the same semantic readiness snapshot prove that the
  existing settle/gate cannot predict whether the synchronous call will
  return.

## Replacement behavior

The replacement no longer calls `LoadSceneCollision` or `LoadScene` from:

- pre-connect scene setup;
- class-selection and spawn scene setup;
- live `SetPlayerPos` scene setup;
- periodic movement-based streaming refresh.

GTA's normal streamer remains authoritative. The existing script opcode
`04E4`/RefreshStreamingAt path remains, as do the specifically scoped
model-request/load helpers.

## Open verification

- Run at least ten cold connect/spawn cycles and require zero open
  `scene_prepare_step` records and zero exceptions.
- Repeat class-selection skin cycling and live SetPlayerPos teleports.
- Compare initial world-pop-in timing against original R5; removing an
  unreferenced blocking call fixes the hang but does not itself prove
  frame-exact streaming timing.
