# Shared movement-ring capacity audit (2026-07-27)

## Scope

The replacement drains up to 1024 RakNet packets in one runtime pump, then
copies a 128-entry shared movement history into the runtime snapshot. The
history orders packets 207/200/209/210/211 across RakNet channels.

Without an intermediate snapshot, a burst of more than 128 movement packets
could overwrite the oldest entries before the runtime consumes them. This is
an implementation-level risk, not behavior observed in the original R5 DLL.

## Windows trailer run

`PROBE_TRACE`:

- run:
  `artifacts/runs/20260727-204023-windows-sync-edge-trailer-945513`
- replacement DLL SHA256:
  `658fb5ec95a3737bf4dbfadb1e81e33b39ccd1f7c8932c023d84adcd599eccbf`
- topology: local original R5 pilot plus native-Windows replacement observer
- server stop marker reported `trailer_updates=505`, and the observer decoded
  505 Packet 210 states; it also decoded 505 Packet 200 states
- the shared movement sequence ended at 1026 after 16 setup movements
- sampled Trailer mappings were exact throughout the run:
  `movement_seq = 16 + (2 * trailer_seq)`, including sequence pairs
  `18/1`, `144/64`, `272/128`, `400/192`, `528/256`, `656/320`,
  `784/384`, `912/448`, and `1026/505`
- no `network_prepare: pump saturated` marker occurred
- the sampled RakNet update telemetry reported at most three messages in one
  network update cycle

Conclusion: this run gives no evidence that the 128-entry ring dropped or
reordered trailer/driver packets. The visibly poor trailer playback must be
explained elsewhere. The capacity mismatch nevertheless remains reachable
under an artificial backlog, long frame stall, or high-player burst.

## Guard

`INFERRED`:

The RakNet adapter now yields a production drain once it has decoded 128
movement packets during that drain. The runtime snapshots immediately after
the drain, so each batch fits the existing history without changing the public
snapshot layout or expanding all other 128-entry remote-sync arrays.
Non-movement-only drains retain the caller's full packet budget.

The guard includes sequence-wrap handling and emits
`packet-state movement_drain_yield` when exercised.

## Deferred runtime head

`PROBE_TRACE + INFERRED`:

The runtime can still retain the oldest movement across multiple frames while
a streamed GTA vehicle is pending. That is outside the per-drain guard above.
The shared cursor now retries such a head without advancing either the shared
or packet-specific cursor, but only for 2000 ms. This bound is below the
approximately 2.1-second overwrite window of 128 combined Packet 200/210
events at 60 events/s. A ring gap is logged and processing resumes from the
oldest available event; an expired dependency is consumed as a drop rather
than globally deadlocking remote movement.

This protects the focused one-pilot/one-observer trailer topology. Multiple
simultaneous remote drivers can exceed the shared history sooner, so a
runtime-owned deferred queue or larger movement-only snapshot remains a
separate scalability improvement.

## Remaining verification

- `TODO_VERIFY`: drive a deterministic synthetic RakNet backlog through the
  real `Receive()` loop and confirm two or more lossless snapshot batches.
- `TODO_VERIFY`: introduce a deliberate observer frame stall during a
  distributed run and verify the new yield marker plus contiguous consumed
  movement sequences.
- This guard does not address vehicle/trailer interpolation, ProcessControl
  choreography, transform authority, or trailer physics.
