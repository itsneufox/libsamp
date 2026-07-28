# ReLoop streaming-hang taxonomy (2026-07-27)

## Scope

This note records the evidence used only to classify ReLoop timeouts. It does
not change client runtime behavior.

## Evidence

`PROBE_TRACE` from replacement runs:

- `artifacts/runs/20260727-165414-replacement-ui-680318`: no `RUN_START`, no
  exception, and the last scene marker is
  `reason=preconnect step=LoadScene phase=begin`.
- `artifacts/runs/20260727-165627-replacement-ui-680318`: no `RUN_START`, no
  exception, and the last scene marker is
  `reason=preconnect step=LoadSceneCollision phase=begin`.
- `artifacts/runs/20260727-170425-replacement-labels-688825`: the same open
  pre-connect `LoadSceneCollision` marker and no RakNet Join/NetGame evidence.
- `artifacts/runs/20260727-170626-replacement-labels-688825`: `ClientJoin` and
  `ScrInitGame` are present, followed by an open
  `reason=spawn step=LoadScene phase=begin` marker. There is no exception.
- `artifacts/runs/20260727-165838-replacement-ui-680318` and
  `artifacts/runs/20260727-170837-replacement-labels-688825` provide successful
  controls: their scene `begin` markers have matching `end` markers and the
  runs reach `RUN_START`/`RUN_DONE`.

The runner stops a timed-out Wine process before verdict construction. That
cleanup can yield client return code 0, which previously caused these timeouts
to be labelled `PRECONNECT_CRASH` despite the absence of a crash trace.

## Conservative classifier

`HANG_PRECONNECT_STREAMING` requires all of:

1. the run timed out before `RUN_START`;
2. neither `exception_filter` nor Wine's unhandled-page-fault marker exists;
3. the last parsed `scene_prepare_step` is `phase=begin` with
   `reason=preconnect`;
4. no `ClientJoin`/`ScrInitGame`/InitGame state marker exists.

`HANG_SPAWN_STREAMING` applies the same timeout and exception guards, but
requires Join/NetGame evidence and an open scene call whose reason is `spawn`,
`server_player_pos`, or `class_select_player_pos`.

A closed scene call, an unknown reason, an explicit crash, `RUN_ABORT`, or a
timeout after `RUN_START` retains the previous verdict path. Both new verdicts
remain in the existing three-attempt retry set.
