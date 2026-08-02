#!/usr/bin/env python3
"""Analyze focused Original-R5 pickup probe artifacts without live access.

The analyzer deliberately distinguishes a complete ordinary-pickup observation
from still-unexercised type-14 and dropped-pickup paths.  It never reports
generic PASS: every conclusion is tagged as observed, partial, mismatched, or
still requiring an Original-R5 run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


OBSERVED = "OBSERVED"
TODO_VERIFY = "TODO_VERIFY"
MISMATCH = "MISMATCH"
OBSERVED_DIFFERENT = "OBSERVED_DIFFERENT"

ORIGINAL_R5_SHA256 = (
    "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2"
)
GTA_10_US_SHA256 = (
    "a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26"
)
PICKUP_FLAG = "samp_probe_pickup_hooks.flag"

PICKED_UP_RVA = "0x00013440"
PROCESS_RVA = "0x00013520"
PROCESS_CALLER_RVA = "0x00008ca8"

EVENT_RE = re.compile(
    r"pickup_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"tick=\d+ thread=\d+ frame=\d+ "
    r"kind=(?P<kind>picked_up|process|rpc_131|rpc_97) "
    r"caller_rva=(?P<caller>0x[0-9a-fA-F]+) "
    r"hook_rva=(?P<hook>0x[0-9a-fA-F]+) "
    r"pool=0x[0-9a-fA-F]+ raw_argument=(?P<raw>\d+) "
    r"process_ordinal=(?P<ordinal>\d+) "
    r"process_gate=(?P<gate_before>\d+),(?P<gate_after>\d+) "
    r"cadence_delta=(?P<delta_ms>\d+)_ms/(?P<delta_frames>\d+)_frames "
    r"rpc=(?P<rpc>\d+) bits=(?P<bits>\d+) "
    r"payload_valid=(?P<payload_valid>\d+) payload=(?P<payload>\d+) "
    r"priority=(?P<priority>\d+) reliability=(?P<reliability>\d+) "
    r"channel=(?P<channel>\d+) result=(?P<result>\d+)"
)

POOL_RE = re.compile(
    r"pickup_pool_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"phase=(?P<phase>pre|post|rpc) valid=(?P<valid>0x[0-9a-fA-F]+) "
    r"pool=0x[0-9a-fA-F]+ count=(?P<count>\d+) "
    r"active=(?P<active>\d+) captured=(?P<captured>\d+)"
)

SLOT_RE = re.compile(
    r"pickup_slot_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"phase=(?P<phase>pre|post|rpc) sample=(?P<sample>\d+) "
    r"valid=(?P<valid>0x[0-9a-fA-F]+) slot=(?P<slot>\d+) "
    r"handle=(?P<handle>0x[0-9a-fA-F]+) "
    r"raw_gta_index=(?P<raw>\d+) timer=(?P<timer>\d+) "
    r"dropped=(?P<dropped>\d+) from_player=(?P<from_player>\d+) "
    r"model=(?P<model>-?\d+) type=(?P<type>-?\d+) "
    r"pos_bits=[0-9a-fA-F]+,[0-9a-fA-F]+,[0-9a-fA-F]+"
)


@dataclass(frozen=True)
class PickupSlot:
    sample: int
    valid_mask: int
    slot: int
    handle: int
    raw_gta_index: int
    timer: int
    dropped: int
    from_player: int
    model: int
    pickup_type: int


@dataclass
class PoolSnapshot:
    valid_mask: int
    count: int
    active: int
    captured: int
    slots: dict[int, PickupSlot] = field(default_factory=dict)


@dataclass
class PickupEvent:
    ring_seq: int
    event_seq: int
    kind: str
    caller_rva: str
    hook_rva: str
    raw_argument: int
    process_ordinal: int
    gate_before: int
    gate_after: int
    delta_ms: int
    delta_frames: int
    rpc_id: int
    rpc_bits: int
    payload_valid: int
    payload: int
    priority: int
    reliability: int
    channel: int
    result: int
    snapshots: dict[str, PoolSnapshot] = field(default_factory=dict)


@dataclass
class ParsedTrace:
    records: list[PickupEvent]
    hook_installed: int | None
    hook_requested: int | None
    restore_restored: int | None
    restore_requested: int | None
    overflow_skipped: int
    install_failure_seen: bool
    parse_errors: list[str]
    orphan_details: int


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_probe_log(path: Path) -> Path:
    """Resolve the final focused Windows log in one artifact.

    ``latest_log_bytes`` is preferred over the duplicate ``logs`` snapshot.
    Multiple Windows run directories remain an error rather than being chosen
    by timestamp.
    """
    if path.is_file():
        return path
    if not path.is_dir():
        raise FileNotFoundError(path)

    priority_patterns = (
        "windows/*/latest_log_bytes/samp_probe.log",
        "windows/*/logs/samp_probe.log",
        "latest_log_bytes/samp_probe.log",
        "logs/samp_probe.log",
        "pilot/client/samp_probe.log",
        "observer/client/samp_probe.log",
        "client/samp_probe.log",
        "samp_probe.log",
    )
    fallback: list[Path] = []
    for pattern in priority_patterns:
        candidates = sorted(
            candidate for candidate in path.glob(pattern) if candidate.is_file()
        )
        fallback.extend(candidates)
        focused = [
            candidate
            for candidate in candidates
            if "pickup_hook:" in _read(candidate)
            or "pickup_r5:" in _read(candidate)
        ]
        if len(focused) == 1:
            return focused[0]
        if len(focused) > 1:
            raise ValueError(
                "multiple focused pickup logs; pass one samp_probe.log directly: "
                + ", ".join(str(candidate) for candidate in focused)
            )
    unique = sorted(set(fallback))
    if len(unique) == 1:
        return unique[0]
    if not unique:
        raise FileNotFoundError(f"no samp_probe.log beneath {path}")
    raise ValueError(
        "probe log selection is ambiguous; pass one samp_probe.log directly: "
        + ", ".join(str(candidate) for candidate in unique)
    )


def _artifact_root(requested: Path, log_path: Path) -> Path | None:
    candidates = [requested] if requested.is_dir() else []
    candidates.extend(log_path.parents)
    for candidate in candidates:
        if (
            (candidate / "metadata.json").is_file()
            or (candidate / "driver" / "pickup.json").is_file()
            or (candidate / "server.log").is_file()
        ):
            return candidate
    return None


def _resolve_manifest(
    requested: Path, log_path: Path, artifact_root: Path | None
) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    candidates: set[Path] = set()
    for parent in (log_path.parent, *log_path.parents[:3]):
        candidate = parent / "manifest.json"
        if candidate.is_file():
            candidates.add(candidate)
    if artifact_root is not None:
        candidates.update(
            candidate
            for candidate in artifact_root.glob("windows/*/manifest.json")
            if candidate.is_file()
        )
    if requested.is_dir():
        direct = requested / "manifest.json"
        if direct.is_file():
            candidates.add(direct)
    if not candidates:
        return None, None, None
    if len(candidates) != 1:
        return None, None, "multiple Windows manifests found"
    manifest_path = next(iter(candidates))
    try:
        value = json.loads(_read(manifest_path))
    except (OSError, json.JSONDecodeError) as error:
        return manifest_path, None, f"invalid manifest: {error}"
    if not isinstance(value, dict):
        return manifest_path, None, "manifest root is not an object"
    return manifest_path, value, None


def parse_trace(text: str) -> ParsedTrace:
    records_by_ring: dict[int, PickupEvent] = {}
    pool_details: list[tuple[int, int, str, PoolSnapshot, int]] = []
    slot_details: list[tuple[int, int, str, PickupSlot, int]] = []
    parse_errors: list[str] = []

    for line_number, line in enumerate(text.splitlines(), 1):
        match = EVENT_RE.search(line)
        if match:
            ring_seq = int(match["seq"])
            if ring_seq in records_by_ring:
                parse_errors.append(f"line {line_number}: duplicate seq={ring_seq}")
                continue
            records_by_ring[ring_seq] = PickupEvent(
                ring_seq=ring_seq,
                event_seq=int(match["event"]),
                kind=match["kind"],
                caller_rva=match["caller"].lower(),
                hook_rva=match["hook"].lower(),
                raw_argument=int(match["raw"]),
                process_ordinal=int(match["ordinal"]),
                gate_before=int(match["gate_before"]),
                gate_after=int(match["gate_after"]),
                delta_ms=int(match["delta_ms"]),
                delta_frames=int(match["delta_frames"]),
                rpc_id=int(match["rpc"]),
                rpc_bits=int(match["bits"]),
                payload_valid=int(match["payload_valid"]),
                payload=int(match["payload"]),
                priority=int(match["priority"]),
                reliability=int(match["reliability"]),
                channel=int(match["channel"]),
                result=int(match["result"]),
            )
            continue

        match = POOL_RE.search(line)
        if match:
            pool_details.append(
                (
                    int(match["seq"]),
                    int(match["event"]),
                    match["phase"],
                    PoolSnapshot(
                        valid_mask=int(match["valid"], 16),
                        count=int(match["count"]),
                        active=int(match["active"]),
                        captured=int(match["captured"]),
                    ),
                    line_number,
                )
            )
            continue

        match = SLOT_RE.search(line)
        if match:
            slot_details.append(
                (
                    int(match["seq"]),
                    int(match["event"]),
                    match["phase"],
                    PickupSlot(
                        sample=int(match["sample"]),
                        valid_mask=int(match["valid"], 16),
                        slot=int(match["slot"]),
                        handle=int(match["handle"], 16),
                        raw_gta_index=int(match["raw"]),
                        timer=int(match["timer"]),
                        dropped=int(match["dropped"]),
                        from_player=int(match["from_player"]),
                        model=int(match["model"]),
                        pickup_type=int(match["type"]),
                    ),
                    line_number,
                )
            )
            continue

        if (
            ("pickup_r5:" in line and "overflow " not in line)
            or "pickup_pool_r5:" in line
            or "pickup_slot_r5:" in line
        ):
            parse_errors.append(f"line {line_number}: malformed pickup trace line")

    orphan_details = 0
    for ring_seq, event_seq, phase, snapshot, line_number in pool_details:
        record = records_by_ring.get(ring_seq)
        if record is None:
            orphan_details += 1
            continue
        if record.event_seq != event_seq:
            parse_errors.append(
                f"line {line_number}: seq={ring_seq} event mismatch "
                f"{event_seq}!={record.event_seq}"
            )
            continue
        if phase in record.snapshots:
            parse_errors.append(
                f"line {line_number}: duplicate pool seq={ring_seq} phase={phase}"
            )
            continue
        record.snapshots[phase] = snapshot

    sample_keys: set[tuple[int, str, int]] = set()
    for ring_seq, event_seq, phase, slot, line_number in slot_details:
        record = records_by_ring.get(ring_seq)
        snapshot = record.snapshots.get(phase) if record is not None else None
        if record is None or snapshot is None:
            orphan_details += 1
            continue
        if record.event_seq != event_seq:
            parse_errors.append(
                f"line {line_number}: seq={ring_seq} slot event mismatch "
                f"{event_seq}!={record.event_seq}"
            )
            continue
        sample_key = (ring_seq, phase, slot.sample)
        if sample_key in sample_keys or slot.slot in snapshot.slots:
            parse_errors.append(
                f"line {line_number}: duplicate slot sample seq={ring_seq} "
                f"phase={phase}"
            )
            continue
        sample_keys.add(sample_key)
        snapshot.slots[slot.slot] = slot

    for record in records_by_ring.values():
        expected_phases = (
            ("rpc",)
            if record.kind in ("rpc_131", "rpc_97")
            else ("pre", "post")
        )
        unexpected = set(record.snapshots) - set(expected_phases)
        if unexpected:
            parse_errors.append(
                f"seq={record.ring_seq}: unexpected phases={sorted(unexpected)}"
            )
        for phase, snapshot in record.snapshots.items():
            if snapshot.captured != len(snapshot.slots):
                parse_errors.append(
                    f"seq={record.ring_seq} phase={phase}: captured="
                    f"{snapshot.captured} slots={len(snapshot.slots)}"
                )

    hook_matches = re.findall(
        r"pickup_hook: summary installed=(\d+) requested=(\d+)", text
    )
    restore_matches = re.findall(
        r"pickup_hook: restore restored=(\d+) requested=(\d+)", text
    )
    overflow_skipped = sum(
        int(value)
        for value in re.findall(r"pickup_r5: overflow skipped=(\d+)", text)
    )
    hook_installed, hook_requested = (
        (int(hook_matches[-1][0]), int(hook_matches[-1][1]))
        if hook_matches
        else (None, None)
    )
    restore_restored, restore_requested = (
        (int(restore_matches[-1][0]), int(restore_matches[-1][1]))
        if restore_matches
        else (None, None)
    )
    install_failure_seen = any(
        marker in text
        for marker in (
            "pickup_hook: skip unsupported_identity",
            "pickup_hook: skip preflight_mismatch",
            "pickup_hook: trampoline_allocation_failed",
            "pickup_hook: incomplete_install",
        )
    )
    event_seqs = [record.event_seq for record in records_by_ring.values()]
    if len(event_seqs) != len(set(event_seqs)):
        parse_errors.append("duplicate event sequence")

    return ParsedTrace(
        records=sorted(
            records_by_ring.values(), key=lambda record: record.ring_seq
        ),
        hook_installed=hook_installed,
        hook_requested=hook_requested,
        restore_restored=restore_restored,
        restore_requested=restore_requested,
        overflow_skipped=overflow_skipped,
        install_failure_seen=install_failure_seen,
        parse_errors=parse_errors,
        orphan_details=orphan_details,
    )


def _identity(
    manifest_path: Path | None,
    manifest: dict[str, Any] | None,
    manifest_error: str | None,
) -> dict[str, Any]:
    if manifest_error:
        return {"status": MISMATCH, "reason": manifest_error}
    if manifest is None:
        return {
            "status": TODO_VERIFY,
            "reason": "no Windows manifest; binary identity is uncorroborated",
        }
    samp_hash = manifest.get("samp_sha256")
    gta_hash = manifest.get("gta_sha256")
    flags = manifest.get("probe_flags")
    checks = {
        "original_r5_samp": samp_hash == ORIGINAL_R5_SHA256,
        "gta_10_us": gta_hash == GTA_10_US_SHA256,
        "pickup_profile_exact": flags == [PICKUP_FLAG],
    }
    return {
        "status": OBSERVED if all(checks.values()) else MISMATCH,
        "manifest": str(manifest_path) if manifest_path is not None else None,
        "samp_sha256": samp_hash,
        "gta_sha256": gta_hash,
        "samp_probe_sha256": manifest.get("samp_probe_sha256"),
        "probe_flags": flags,
        "checks": checks,
    }


def _rpc_errors(
    record: PickupEvent,
    *,
    rpc_id: int,
    bits: int,
    reliability: int,
) -> list[str]:
    expected = {
        "kind": f"rpc_{rpc_id}",
        "rpc_id": rpc_id,
        "rpc_bits": bits,
        "payload_valid": 1,
        "priority": 1,
        "reliability": reliability,
        "channel": 0,
        "hook_rva": "0x00000000",
    }
    actual = {
        "kind": record.kind,
        "rpc_id": record.rpc_id,
        "rpc_bits": record.rpc_bits,
        "payload_valid": record.payload_valid,
        "priority": record.priority,
        "reliability": record.reliability,
        "channel": record.channel,
        "hook_rva": record.hook_rva,
    }
    return [
        f"{name}={actual[name]!r}, expected={value!r}"
        for name, value in expected.items()
        if actual[name] != value
    ]


def _nested_rpcs(
    method: PickupEvent, records: list[PickupEvent], kinds: tuple[str, ...]
) -> list[PickupEvent]:
    return sorted(
        (
            record
            for record in records
            if record.kind in kinds
            and record.event_seq > method.event_seq
            and record.ring_seq < method.ring_seq
        ),
        key=lambda record: record.event_seq,
    )


def _ordinary(
    records: list[PickupEvent],
) -> tuple[dict[str, Any], set[int]]:
    observations: list[dict[str, Any]] = []
    used_rpc_ring_seqs: set[int] = set()
    for method in (record for record in records if record.kind == "picked_up"):
        errors: list[str] = []
        if method.hook_rva != PICKED_UP_RVA:
            errors.append(
                f"hook_rva={method.hook_rva}, expected={PICKED_UP_RVA}"
            )
        pre = method.snapshots.get("pre")
        post = method.snapshots.get("post")
        if pre is None or post is None:
            errors.append("missing pre/post pool snapshot")
            observations.append(
                {
                    "status": MISMATCH,
                    "event_seq": method.event_seq,
                    "errors": errors,
                }
            )
            continue

        matching = [
            slot
            for slot in pre.slots.values()
            if slot.raw_gta_index == method.raw_argument
        ]
        if len(matching) != 1:
            errors.append(
                f"raw_argument matched {len(matching)} pre slots, expected 1"
            )
            observations.append(
                {
                    "status": MISMATCH,
                    "event_seq": method.event_seq,
                    "errors": errors,
                }
            )
            continue
        before = matching[0]
        after = post.slots.get(before.slot)
        if before.valid_mask != 0x1F:
            errors.append(f"pre slot valid_mask=0x{before.valid_mask:08x}")
        if after is None:
            errors.append("focused slot missing from post snapshot")
        else:
            if after.valid_mask != 0x1F:
                errors.append(f"post slot valid_mask=0x{after.valid_mask:08x}")
            if before.handle == 0:
                errors.append("pre handle is zero")
            if before.timer != 0:
                errors.append(f"pre timer={before.timer}, expected=0")
            if before.dropped != 0:
                errors.append(f"pre dropped={before.dropped}, expected=0")
            if after.timer != 15:
                errors.append(f"post timer={after.timer}, expected=15")
            for name in (
                "handle",
                "raw_gta_index",
                "dropped",
                "from_player",
                "model",
                "pickup_type",
            ):
                if getattr(before, name) != getattr(after, name):
                    errors.append(
                        f"{name} changed {getattr(before, name)}"
                        f"->{getattr(after, name)}"
                    )

        rpc_candidates = [
            rpc
            for rpc in _nested_rpcs(method, records, ("rpc_131",))
            if rpc.payload_valid == 1 and rpc.payload == before.slot
        ]
        rpc: PickupEvent | None = None
        if len(rpc_candidates) != 1:
            errors.append(
                f"nested RPC131 candidates={len(rpc_candidates)}, expected=1"
            )
        else:
            rpc = rpc_candidates[0]
            used_rpc_ring_seqs.add(rpc.ring_seq)
            if rpc.event_seq != method.event_seq + 1:
                errors.append(
                    f"nested RPC event_seq={rpc.event_seq}, expected="
                    f"{method.event_seq + 1}"
                )
            errors.extend(
                _rpc_errors(rpc, rpc_id=131, bits=32, reliability=9)
            )
            rpc_snapshot = rpc.snapshots.get("rpc")
            if rpc_snapshot is None or before.slot not in rpc_snapshot.slots:
                errors.append("RPC131 focus slot missing from rpc snapshot")

        observation: dict[str, Any] = {
            "status": MISMATCH if errors else OBSERVED,
            "event_seq": method.event_seq,
            "slot": before.slot,
            "raw_argument": method.raw_argument,
            "model": before.model,
            "pickup_type": before.pickup_type,
            "dropped": before.dropped,
            "handle_index": before.handle & 0xFFFF,
            "handle_generation": before.handle >> 16,
            "raw_equals_handle_index": (
                method.raw_argument == (before.handle & 0xFFFF)
            ),
            "timer": {
                "pre": before.timer,
                "post": after.timer if after is not None else None,
            },
            "rpc": (
                {
                    "event_seq": rpc.event_seq,
                    "id": rpc.rpc_id,
                    "bits": rpc.rpc_bits,
                    "payload": rpc.payload,
                    "priority": rpc.priority,
                    "reliability": rpc.reliability,
                    "channel": rpc.channel,
                    "result": rpc.result,
                }
                if rpc is not None
                else None
            ),
            "rpc_failure_timer_assignment": (
                OBSERVED
                if rpc is not None
                and rpc.result == 0
                and after is not None
                and after.timer == 15
                else TODO_VERIFY
            ),
            "errors": errors,
        }
        observations.append(observation)

    if not observations:
        status = TODO_VERIFY
    elif any(item["status"] == MISMATCH for item in observations):
        status = MISMATCH
    else:
        status = OBSERVED
    return (
        {
            "status": status,
            "event_count": len(observations),
            "observations": observations,
            "static_oracle": {
                "payload": "signed int32 SA-MP pickup slot",
                "qos": "priority=1 reliability=9 channel=0",
                "timer_transition": "0->15",
                "rejects": "missing, zero-handle, nonzero-timer, dropped",
            },
        },
        used_rpc_ring_seqs,
    )


def _process(
    records: list[PickupEvent],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], set[int]]:
    process_events = [record for record in records if record.kind == "process"]
    process_errors: list[str] = []
    timer_samples: list[dict[str, int]] = []
    type14_samples: list[dict[str, Any]] = []
    dropped_samples: list[dict[str, Any]] = []
    used_rpc_ring_seqs: set[int] = set()

    for method in process_events:
        if method.hook_rva != PROCESS_RVA:
            process_errors.append(
                f"event={method.event_seq} hook_rva={method.hook_rva}, "
                f"expected={PROCESS_RVA}"
            )
        if method.caller_rva != PROCESS_CALLER_RVA:
            process_errors.append(
                f"event={method.event_seq} caller_rva={method.caller_rva}, "
                f"expected={PROCESS_CALLER_RVA}"
            )
        if (method.gate_before, method.gate_after) != (6, 6):
            process_errors.append(
                f"event={method.event_seq} process_gate="
                f"{method.gate_before},{method.gate_after}, expected=6,6"
            )
        pre = method.snapshots.get("pre")
        post = method.snapshots.get("post")
        if pre is None or post is None:
            process_errors.append(
                f"event={method.event_seq} missing pre/post pool snapshot"
            )
            continue

        for before in pre.slots.values():
            after = post.slots.get(before.slot)
            if (
                after is not None
                and before.handle != 0
                and before.dropped == 0
                and before.pickup_type != 14
            ):
                expected_timer = max(0, before.timer - 1)
                timer_samples.append(
                    {
                        "event_seq": method.event_seq,
                        "slot": before.slot,
                        "pre": before.timer,
                        "post": after.timer,
                        "expected_post": expected_timer,
                    }
                )
                if after.timer != expected_timer:
                    process_errors.append(
                        f"event={method.event_seq} slot={before.slot} "
                        f"ordinary timer {before.timer}->{after.timer}, "
                        f"expected {expected_timer}"
                    )

        nested = _nested_rpcs(method, records, ("rpc_131", "rpc_97"))
        for rpc in nested:
            used_rpc_ring_seqs.add(rpc.ring_seq)
            if rpc.kind == "rpc_131":
                errors = _rpc_errors(
                    rpc, rpc_id=131, bits=32, reliability=10
                )
                before = pre.slots.get(rpc.payload)
                if before is None:
                    errors.append("type-14 payload slot was not captured")
                    status = TODO_VERIFY if len(errors) == 1 else MISMATCH
                else:
                    if before.dropped != 0 or before.pickup_type != 14:
                        errors.append(
                            f"payload slot dropped/type="
                            f"{before.dropped}/{before.pickup_type}, "
                            "expected=0/14"
                        )
                    after = post.slots.get(before.slot)
                    if after is None or after.timer != before.timer:
                        errors.append("type-14 timer changed or post slot missing")
                    status = MISMATCH if errors else OBSERVED
                type14_samples.append(
                    {
                        "status": status,
                        "event_seq": method.event_seq,
                        "rpc_event_seq": rpc.event_seq,
                        "slot": rpc.payload,
                        "qos": {
                            "priority": rpc.priority,
                            "reliability": rpc.reliability,
                            "channel": rpc.channel,
                        },
                        "errors": errors,
                    }
                )
            else:
                errors = _rpc_errors(rpc, rpc_id=97, bits=16, reliability=10)
                matches = [
                    slot
                    for slot in pre.slots.values()
                    if slot.dropped == 1 and slot.from_player == rpc.payload
                ]
                if not matches:
                    errors.append("dropped source slot was not captured")
                    status = TODO_VERIFY if len(errors) == 1 else MISMATCH
                    slot_number = None
                else:
                    before = matches[0]
                    slot_number = before.slot
                    after = post.slots.get(before.slot)
                    if after is None or after.timer != before.timer:
                        errors.append("dropped timer changed or post slot missing")
                    status = MISMATCH if errors else OBSERVED
                dropped_samples.append(
                    {
                        "status": status,
                        "event_seq": method.event_seq,
                        "rpc_event_seq": rpc.event_seq,
                        "slot": slot_number,
                        "from_player": rpc.payload,
                        "qos": {
                            "priority": rpc.priority,
                            "reliability": rpc.reliability,
                            "channel": rpc.channel,
                        },
                        "errors": errors,
                    }
                )

    ordinals = [event.process_ordinal for event in process_events]
    ordinal_consecutive = all(
        current == previous + 1
        for previous, current in zip(ordinals, ordinals[1:])
    )
    if not ordinal_consecutive:
        process_errors.append("process ordinals are not consecutive")
    frame_deltas = [
        event.delta_frames for event in process_events if event.delta_frames > 0
    ]
    if not frame_deltas:
        cadence_status = TODO_VERIFY
    elif all(delta == 7 for delta in frame_deltas):
        cadence_status = OBSERVED
    else:
        cadence_status = OBSERVED_DIFFERENT

    process_status = (
        TODO_VERIFY
        if not process_events
        else MISMATCH
        if process_errors
        else OBSERVED
    )
    positive_timer_samples = [
        sample for sample in timer_samples if sample["pre"] > 0
    ]
    timer_status = (
        MISMATCH
        if any(sample["post"] != sample["expected_post"] for sample in timer_samples)
        else OBSERVED
        if positive_timer_samples
        else TODO_VERIFY
    )

    def path_status(samples: list[dict[str, Any]]) -> str:
        if not samples:
            return TODO_VERIFY
        if any(sample["status"] == MISMATCH for sample in samples):
            return MISMATCH
        if any(sample["status"] == TODO_VERIFY for sample in samples):
            return TODO_VERIFY
        return OBSERVED

    process_result = {
        "status": process_status,
        "event_count": len(process_events),
        "errors": process_errors,
        "caller_rva": PROCESS_CALLER_RVA,
        "gate_oracle": "6 before and after; caller resets after return",
        "ordinals_consecutive": ordinal_consecutive,
        "cadence": {
            "status": cadence_status,
            "frame_deltas": frame_deltas,
            "millisecond_deltas": [
                event.delta_ms for event in process_events if event.delta_ms > 0
            ],
            "static_prediction": (
                "one Process call per seven caller invocations; frame spacing "
                "remains runtime-dependent"
            ),
        },
        "ordinary_timer_countdown": {
            "status": timer_status,
            "samples": timer_samples,
            "positive_timer_sample_count": len(positive_timer_samples),
        },
    }
    type14_result = {
        "status": path_status(type14_samples),
        "event_count": len(type14_samples),
        "observations": type14_samples,
        "static_oracle": {
            "rpc": 131,
            "payload": "signed int32 SA-MP pickup slot",
            "qos": "priority=1 reliability=10 channel=0",
            "timer": "unchanged",
        },
    }
    dropped_result = {
        "status": path_status(dropped_samples),
        "event_count": len(dropped_samples),
        "observations": dropped_samples,
        "static_oracle": {
            "rpc": 97,
            "payload": "uint16 source player",
            "qos": "priority=1 reliability=10 channel=0",
            "timer": "unchanged",
        },
    }
    return process_result, type14_result, dropped_result, used_rpc_ring_seqs


def _driver_request(artifact_root: Path | None) -> tuple[int | None, int | None]:
    if artifact_root is None:
        return None, None
    driver_path = artifact_root / "driver" / "pickup.json"
    if not driver_path.is_file():
        return None, None
    try:
        value = json.loads(_read(driver_path))
    except (OSError, json.JSONDecodeError):
        return None, 1
    if not isinstance(value, dict):
        return None, 1
    events = value.get("events")
    request_ids = (
        {
            event.get("request_id")
            for event in events
            if isinstance(event, dict)
            and event.get("event") == "sync_pair_scenario_queued"
            and isinstance(event.get("request_id"), int)
        }
        if isinstance(events, list)
        else set()
    )
    request_id = next(iter(request_ids)) if len(request_ids) == 1 else None
    returncode = value.get("returncode")
    return request_id, returncode if isinstance(returncode, int) else None


def _request_block(text: str, request_id: int) -> str:
    selected: list[str] = []
    active = False
    for line in text.splitlines():
        accepted = re.search(r"marker=REQUEST_ACCEPTED\b.*\brequest=(\d+)\b", line)
        if accepted:
            active = int(accepted.group(1)) == request_id
        if active:
            selected.append(line)
    return "\n".join(selected)


def _fixture(artifact_root: Path | None) -> dict[str, Any]:
    request_id, returncode = _driver_request(artifact_root)
    if artifact_root is None or request_id is None:
        return {
            "status": MISMATCH if returncode is not None else TODO_VERIFY,
            "request_id": request_id,
            "reason": (
                "pickup driver receipt is invalid or has no unique request"
                if returncode is not None
                else "artifact driver request context is unavailable"
            ),
        }
    blocks = [
        _request_block(_read(path), request_id)
        for path in (
            artifact_root / "server.log",
            artifact_root / "server.console.log",
            artifact_root / "sync-pair-results.log",
        )
        if path.is_file()
    ]
    checks = {
        "driver_completed": returncode == 0,
        "request_done": any(
            re.search(
                rf"marker=REQUEST_DONE\b.*\brequest={request_id}\b.*"
                r"\bstatus=PASS\b.*\bscenario=pickup\b",
                block,
            )
            is not None
            for block in blocks
        ),
        "pickup_created": any("marker=PICKUP_CREATED" in block for block in blocks),
        "pickup_collected": any(
            "marker=PICKUP_COLLECTED" in block for block in blocks
        ),
    }
    return {
        "status": OBSERVED if all(checks.values()) else MISMATCH,
        "request_id": request_id,
        "checks": checks,
        "scope": "ordinary type-1 pickup only",
    }


def analyze_log(path: Path) -> dict[str, Any]:
    requested = path.resolve()
    log_path = resolve_probe_log(requested)
    trace = parse_trace(_read(log_path))
    artifact_root = _artifact_root(requested, log_path)
    manifest_path, manifest, manifest_error = _resolve_manifest(
        requested, log_path, artifact_root
    )
    identity = _identity(manifest_path, manifest, manifest_error)

    hook_status = (
        MISMATCH
        if trace.install_failure_seen
        else TODO_VERIFY
        if trace.hook_installed is None
        else OBSERVED
        if trace.hook_installed == trace.hook_requested == 2
        else MISMATCH
    )
    restore_status = (
        TODO_VERIFY
        if trace.restore_restored is None
        else OBSERVED
        if trace.restore_restored == trace.restore_requested == 2
        else MISMATCH
    )
    integrity_status = (
        MISMATCH
        if (
            hook_status == MISMATCH
            or restore_status == MISMATCH
            or trace.overflow_skipped
            or trace.parse_errors
            or trace.orphan_details
        )
        else TODO_VERIFY
        if hook_status == TODO_VERIFY
        else OBSERVED
    )

    ordinary, ordinary_rpc = _ordinary(trace.records)
    process, type14, dropped, process_rpc = _process(trace.records)
    used_rpc = ordinary_rpc | process_rpc
    all_rpc = {
        record.ring_seq
        for record in trace.records
        if record.kind in ("rpc_131", "rpc_97")
    }
    unpaired_rpc = sorted(all_rpc - used_rpc)
    rpc_pairing_status = OBSERVED if not unpaired_rpc else MISMATCH
    fixture = _fixture(artifact_root)

    mismatch_statuses = (
        integrity_status,
        identity["status"],
        fixture["status"],
        ordinary["status"],
        process["status"],
        type14["status"],
        dropped["status"],
        rpc_pairing_status,
    )
    if MISMATCH in mismatch_statuses:
        assessment = MISMATCH
    elif (
        identity["status"] == OBSERVED
        and integrity_status == OBSERVED
        and fixture["status"] == OBSERVED
        and ordinary["status"] == OBSERVED
        and process["status"] == OBSERVED
    ):
        if (
            type14["status"] == OBSERVED
            and dropped["status"] == OBSERVED
            and process["ordinary_timer_countdown"]["status"] == OBSERVED
        ):
            assessment = "OBSERVED_COMPLETE"
        else:
            assessment = "OBSERVED_ORDINARY"
    elif any(
        status == OBSERVED
        for status in (
            ordinary["status"],
            process["status"],
            type14["status"],
            dropped["status"],
        )
    ):
        assessment = "OBSERVED_PARTIAL"
    else:
        assessment = TODO_VERIFY

    return {
        "schema": 1,
        "source_log": str(log_path),
        "source_sha256": _sha256(log_path),
        "assessment": assessment,
        "evidence": ["STATIC_037", "PROBE_TRACE", "TODO_VERIFY"],
        "identity": identity,
        "identity_policy": {
            "pointers": "excluded_from_output_and_pairing",
            "ticks_and_absolute_frames": "excluded_from_output_and_pairing",
            "event_pairing": (
                "event_seq establishes nesting; ring_seq establishes "
                "publication order"
            ),
        },
        "integrity": {
            "status": integrity_status,
            "hook_install": {
                "status": hook_status,
                "installed": trace.hook_installed,
                "requested": trace.hook_requested,
            },
            "overflow": {
                "status": OBSERVED if trace.overflow_skipped == 0 else MISMATCH,
                "skipped": trace.overflow_skipped,
            },
            "hook_restore": {
                "status": restore_status,
                "restored": trace.restore_restored,
                "requested": trace.restore_requested,
                "required_for_observation": False,
            },
            "parse_errors": trace.parse_errors,
            "orphan_details": trace.orphan_details,
            "rpc_pairing": {
                "status": rpc_pairing_status,
                "unpaired_ring_sequences": unpaired_rpc,
            },
        },
        "fixture": fixture,
        "record_counts": {
            kind: sum(record.kind == kind for record in trace.records)
            for kind in ("picked_up", "process", "rpc_131", "rpc_97")
        },
        "ordinary_picked_up": ordinary,
        "process": process,
        "type14_process": type14,
        "dropped_process": dropped,
        "coverage_boundary": {
            "ordinary_fixture": (
                "the current sync_pair pickup scenario creates type 1 and "
                "destroys it after the server callback"
            ),
            "not_claimed_from_ordinary_fixture": [
                "15-tick repeated-notification cadence",
                "type-14 RPC131 path",
                "dropped RPC97 path",
                "pause/unpause behavior",
                "destroy/recreate handle generations",
                "visual disappearance independent of the SA-MP slot",
            ],
        },
    }


def _render(result: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_or_log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze_log(args.artifact_or_log)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    _render(result, args.output)
    return 1 if result["assessment"] == MISMATCH else 0


if __name__ == "__main__":
    raise SystemExit(main())
