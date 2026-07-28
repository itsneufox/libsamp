# RemoveBuildingForPlayer lifecycle in SA-MP 0.3.7 R5

Date: 2026-07-27

Reference binary:

- SA-MP 0.3.7 R5 `samp.dll`
- SHA256: `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`
- Preferred image base: `0x10000000`; every address below is recorded as an
  RVA from `samp.dll`.

## Evidence scope

This document began as a static lifecycle/xref audit of the R5 binary. A
populated original-client GMX trace captured on 2026-07-28 now corroborates
the process-lifetime and duplicate-rule behavior:

- artifact:
  `artifacts/runs/20260728-144428-distributed-sync-gmx-1646159`;
- original probe log:
  `windows/20260728_144443_dist_sync_gmx_pilot_ee1502b0/latest_log_bytes/samp_probe.log`;
- probe-log SHA256:
  `7474fe5d3e5f0b0c1a7ea4d8332daeb446dbbdf119d02e320a8673fc953d3b8f`.

- `STATIC_037`: instruction flow, global references, and the absence of a
  clear/reset reference in the audited R5 paths.
- `INFERRED`: lifecycle behavior derived only from static evidence.
- `OBSERVED_037` / `PROBE_TRACE`: the rule count remained 15 across the
  synchronous original-R5 GMX reset; the fixture's repeated rules occupied
  separate entries.
- `TODO_VERIFY`: claims that still need a watched original-client run.

## R5 findings

| Location | Evidence | Finding |
| --- | --- | --- |
| `samp.dll+0x1D530` | `STATIC_037` | RPC 43 reads the model, position, and radius and enters the remove-building path. |
| `samp.dll+0x9D180`, `+0x9D020`, `+0x9CFF0` | `STATIC_037` | The immediate path scans the relevant GTA pools and marks matching entities removed; the existing focused analysis also identifies the R5 Z displacement used for current entities. |
| `samp.dll+0x9D3D0` | `STATIC_037` | A remove-building rule is appended to the process-global rule store. No equality/deduplication test was found on this append path. |
| `samp.dll+0x14AF68` | `STATIC_037` | Base of the process-global rule storage. A rule occupies 20 bytes: model ID, three position floats, and radius. |
| `samp.dll+0x14FD88` | `STATIC_037` | Global rule count. The 20,000-byte interval from the store base to this count is consistent with storage for about 1,000 rules. This layout-derived capacity is not proof of a checked upper bound. |
| `samp.dll+0xA4A70` | `STATIC_037` | The later IPL/stream-in path checks retained rules and substitutes model 19300 (`blankmodel`) for matching definitions. |
| `samp.dll+0xA540` | `STATIC_037` | The audited GMX handling path contains no remove-building store clear. |

No count/store reset xref was found in the audited GMX, disconnect, or session
teardown paths. The static result therefore supports the following lifecycle:

- `INFERRED`: remove-building rules live for the lifetime of the `samp.dll`
  process, not only for one network session.
- `INFERRED`: GMX, disconnect, and reconnect do not restore already removed
  entities and do not discard the rules used for later IPL stream-ins.
- `INFERRED`: the same retained rule can continue suppressing matching
  buildings after a reconnect in the same process.

The GMX portion is now `OBSERVED_037 + PROBE_TRACE`: the count remained
`15 -> 15` inside `samp.dll+0xA540`. Disconnect/reconnect persistence and the
affected entity state after later IPL streaming remain `TODO_VERIFY`.

## Replacement correction

The former replacement reset cleared its retained rules at a session boundary
without restoring the GTA entities already altered by those rules. That
created a hybrid state: current entities remained removed, while future
stream-ins were no longer covered.

The compatibility reset now preserves the rule count and records for the
process lifetime. On GMX/connect/disconnect it resets only:

- the adapter-consumer event sequence, so a new adapter snapshot can be
  consumed correctly; and
- the periodic scan tick, so the retained rules are reconsidered promptly.

Fresh-process initialization still zeroes the store normally. The GMX
persistence behavior is now backed by `OBSERVED_037 + PROBE_TRACE`; other
session boundaries remain inferred from `STATIC_037`.

The replacement also no longer deduplicates equal rules. Each received rule is
appended in arrival order, matching both the absence of an equality branch at
`samp.dll+0x9D3D0` and the original fixture count of 15. Before this correction,
the same fixture collapsed those entries to 9 in:
`artifacts/runs/20260728-145211-distributed-sync-gmx-1657080`.

`PROBE_TRACE`: the corrected replacement was rebuilt as SHA256
`693a78e7f40e5d579997f9a126bd0082ddf2495c56d78bce8b657421b259e712`
and rerun in:
`artifacts/runs/20260728-145828-distributed-sync-gmx-1669162`.
The GMX reset now reports `records_persisted=15`, and the full
`InitGame -> GameModeRestart -> InitGame` cycle, Windows rejoin, and post-GMX
spawn completed without a crash. Duplicate-count parity is therefore closed
for this fixture.

## Remaining differences

| Replacement behavior | R5 evidence | Status |
| --- | --- | --- |
| Stores at most 256 compatibility rules. | The R5 global layout is consistent with about 1,000 20-byte records. | `STATIC_037`; capacity parity remains open. |
| Reapplies rules by scanning pools every 750 ms. | R5 handles later IPL definitions in the stream-in hook at `+0xA4A70` and substitutes model 19300 before normal creation. | `STATIC_037`; timing and implementation are not exact. |
| Uses conservative bounds and overflow handling. | No equivalent checked upper-bound path was established in the focused R5 append analysis. | `TODO_VERIFY`; unsafe unchecked behavior should not be copied speculatively. |

The periodic rescan is currently the safer compatibility fallback, but it can
leave a short visible window and cannot exactly reproduce the original IPL
creation-time substitution.

## Runtime verification still required

GMX persistence and duplicate append behavior are now closed for the exercised
fixture. Remaining verification should use the same original R5 process for:

1. joining a fixture that sends one distinctive `RemoveBuildingForPlayer`
   rule;
2. watching `samp.dll+0x14FD88` and the first record at
   `samp.dll+0x14AF68`.
3. triggering disconnect/reconnect and a later IPL stream-in near the rule;
4. confirming that the count and record survive those remaining session
   transitions and that the matching building remains absent;
5. exercising enough unique rules to determine the practical limit around the
   layout-derived 1,000-record boundary without allowing an uncontrolled
   overwrite.

Expected evidence tags for those runs are `OBSERVED_037 + PROBE_TRACE`. Exact
capacity, overflow behavior, disconnect/reconnect persistence, and stream-in
timing remain `TODO_VERIFY`.
