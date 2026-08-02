#!/usr/bin/env python3
"""Summarize artifact-only R5 death_cleanup_* cleanup evidence."""

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
UINT32_MAX = 0xFFFFFFFF

TARGET_KINDS = ("gmx_reset", "connection_lost", "quit_destructor")

EVENT_RE = re.compile(
    r"death_cleanup_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"tick=\d+ thread=\d+ frame=\d+ kind=(?P<kind>[a-z_]+) "
    r"caller_rva=(?P<caller>0x[0-9a-fA-F]+) "
    r"hook_rva=(?P<hook>0x[0-9a-fA-F]+) "
    r"object=0x[0-9a-fA-F]+ argument=0x[0-9a-fA-F]+ "
    r"result=(?P<result>0x[0-9a-fA-F]+) "
    r"cleanup=(?P<cleanup>\d+)"
)

UI_RE = re.compile(
    r"death_cleanup_ui_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"phase=(?P<phase>pre|post) "
    r"scoreboard=0x[0-9a-fA-F]+ visible=(?P<scoreboard>\d+) "
    r"dialog=0x[0-9a-fA-F]+ active=(?P<dialog>\d+) "
    r"selector=0x[0-9a-fA-F]+ active=(?P<selector>\d+) "
    r"chat=0x[0-9a-fA-F]+ active=(?P<chat>\d+) "
    r"class_gui=0x[0-9a-fA-F]+ visible=(?P<class_gui>\d+) "
    r"game=0x[0-9a-fA-F]+ "
    r"input_depth=(?P<input_a>\d+),(?P<input_b>\d+) "
    r"camera=(?P<camera_a>\d+),(?P<camera_b>\d+) "
    r"frontend=(?P<frontend_a>\d+),(?P<frontend_b>\d+),"
    r"(?P<frontend_c>\d+)"
)

POOLS_RE = re.compile(
    r"death_cleanup_pools_r5: seq=(?P<seq>\d+) event=(?P<event>\d+) "
    r"phase=(?P<phase>pre|post) "
    r"valid=0x[0-9a-fA-F]+ netgame=0x[0-9a-fA-F]+ "
    r"pools=0x[0-9a-fA-F]+ pool_ptrs=\S+ "
    r"vehicle=(?P<vehicle_listed>\d+)/(?P<vehicle_wrappers>\d+) "
    r"remote=(?P<remote_aux>\d+)/(?P<remote_wrappers>\d+) "
    r"pickup_raw=(?P<pickup_handles>\d+)/(?P<pickup_server_ids>\d+)/"
    r"(?P<pickup_timers>\d+) "
    r"object=(?P<object_listed>\d+)/(?P<object_wrappers>\d+) "
    r"actor=(?P<actor_listed>\d+)/(?P<actor_wrappers>\d+) "
    r"gangzone=(?P<gangzone_listed>\d+) "
    r"textdraw=(?P<textdraw_listed>\d+) "
    r"label=(?P<label_listed>\d+) menu=(?P<menu_listed>\d+) "
    r"current=(?P<menu_current>\d+) "
    r"remove_building_count=(?P<remove_building_count>\d+)"
)

POOL_FIELDS = (
    "vehicle_listed",
    "vehicle_wrappers",
    "remote_aux",
    "remote_wrappers",
    "pickup_handles",
    "pickup_server_ids",
    "pickup_timers",
    "object_listed",
    "object_wrappers",
    "actor_listed",
    "actor_wrappers",
    "gangzone_listed",
    "textdraw_listed",
    "label_listed",
    "menu_listed",
    "menu_current",
)


@dataclass
class CleanupEvent:
    ring_seq: int
    event_seq: int
    kind: str
    caller_rva: str
    hook_rva: str
    result: str
    cleanup_valid: bool
    ui: dict[str, dict[str, Any]] = field(default_factory=dict)
    pools: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class ParsedTrace:
    records: list[CleanupEvent]
    hook_installed: int | None
    hook_requested: int | None
    overflow_skipped: int
    restore_restored: int | None
    restore_requested: int | None
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
    """Resolve one focused probe log without selecting by timestamp or pointer."""
    if path.is_file():
        return path
    if not path.is_dir():
        raise FileNotFoundError(path)

    candidates: set[Path] = set()
    for pattern in (
        "client/samp_probe.log",
        "logs/samp_probe.log",
        "pilot/client/samp_probe.log",
        "observer/client/samp_probe.log",
        "windows/*/logs/samp_probe.log",
    ):
        candidates.update(candidate for candidate in path.glob(pattern) if candidate.is_file())

    focused = [
        candidate
        for candidate in sorted(candidates)
        if "death_cleanup_" in _read(candidate)
    ]
    if len(focused) == 1:
        return focused[0]
    if not focused and len(candidates) == 1:
        return next(iter(candidates))
    if not candidates:
        raise FileNotFoundError(f"no samp_probe.log beneath {path}")
    raise ValueError(
        "probe log selection is ambiguous; pass one samp_probe.log directly: "
        + ", ".join(str(candidate) for candidate in focused or sorted(candidates))
    )


def _ui_snapshot(match: re.Match[str]) -> dict[str, Any]:
    return {
        "scoreboard_visible": int(match["scoreboard"]),
        "dialog_active": int(match["dialog"]),
        "textdraw_selector_active": int(match["selector"]),
        "chat_active": int(match["chat"]),
        "class_gui_visible": int(match["class_gui"]),
        "input_depth": [int(match["input_a"]), int(match["input_b"])],
        "camera": [int(match["camera_a"]), int(match["camera_b"])],
        "frontend": [
            int(match["frontend_a"]),
            int(match["frontend_b"]),
            int(match["frontend_c"]),
        ],
    }


def _pool_snapshot(match: re.Match[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    unreadable: list[str] = []
    for name in POOL_FIELDS:
        value = int(match[name])
        if value == UINT32_MAX:
            snapshot[name] = None
            unreadable.append(name)
        else:
            snapshot[name] = value
    snapshot["remove_building_count"] = int(match["remove_building_count"])
    snapshot["unreadable"] = unreadable
    return snapshot


def parse_trace(text: str) -> ParsedTrace:
    records_by_seq: dict[int, CleanupEvent] = {}
    details: list[tuple[str, int, int, str, dict[str, Any], int]] = []
    parse_errors: list[str] = []

    for line_number, line in enumerate(text.splitlines(), 1):
        event_match = EVENT_RE.search(line)
        if event_match:
            ring_seq = int(event_match["seq"])
            if ring_seq in records_by_seq:
                parse_errors.append(f"line {line_number}: duplicate seq={ring_seq}")
                continue
            records_by_seq[ring_seq] = CleanupEvent(
                ring_seq=ring_seq,
                event_seq=int(event_match["event"]),
                kind=event_match["kind"],
                caller_rva=event_match["caller"].lower(),
                hook_rva=event_match["hook"].lower(),
                result=event_match["result"].lower(),
                cleanup_valid=event_match["cleanup"] == "1",
            )
            continue

        ui_match = UI_RE.search(line)
        if ui_match:
            details.append(
                (
                    "ui",
                    int(ui_match["seq"]),
                    int(ui_match["event"]),
                    ui_match["phase"],
                    _ui_snapshot(ui_match),
                    line_number,
                )
            )
            continue

        pool_match = POOLS_RE.search(line)
        if pool_match:
            details.append(
                (
                    "pools",
                    int(pool_match["seq"]),
                    int(pool_match["event"]),
                    pool_match["phase"],
                    _pool_snapshot(pool_match),
                    line_number,
                )
            )

    orphan_details = 0
    for detail_kind, ring_seq, event_seq, phase, snapshot, line_number in details:
        record = records_by_seq.get(ring_seq)
        if record is None:
            orphan_details += 1
            continue
        if record.event_seq != event_seq:
            parse_errors.append(
                f"line {line_number}: seq={ring_seq} event mismatch "
                f"{event_seq}!={record.event_seq}"
            )
            continue
        target = record.ui if detail_kind == "ui" else record.pools
        if phase in target:
            parse_errors.append(
                f"line {line_number}: duplicate {detail_kind} seq={ring_seq} phase={phase}"
            )
            continue
        target[phase] = snapshot

    hook_matches = re.findall(
        r"death_cleanup_hook: summary installed=(\d+) requested=(\d+)", text
    )
    restore_matches = re.findall(
        r"death_cleanup_hook: restore restored=(\d+) requested=(\d+)", text
    )
    overflow_skipped = sum(
        int(value)
        for value in re.findall(r"death_cleanup_r5: overflow skipped=(\d+)", text)
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

    return ParsedTrace(
        records=sorted(records_by_seq.values(), key=lambda record: record.ring_seq),
        hook_installed=hook_installed,
        hook_requested=hook_requested,
        overflow_skipped=overflow_skipped,
        restore_restored=restore_restored,
        restore_requested=restore_requested,
        parse_errors=parse_errors,
        orphan_details=orphan_details,
    )


def _delta(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, int | None]:
    return {
        name: (
            post[name] - pre[name]
            if isinstance(pre.get(name), int) and isinstance(post.get(name), int)
            else None
        )
        for name in POOL_FIELDS
    }


def _changes(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {"pre": pre[name], "post": post[name]}
        for name in pre.keys() & post.keys()
        if pre[name] != post[name]
    }


def _observation(record: CleanupEvent) -> dict[str, Any]:
    missing = [
        f"{kind}.{phase}"
        for kind, snapshots in (("ui", record.ui), ("pools", record.pools))
        for phase in ("pre", "post")
        if phase not in snapshots
    ]
    observation: dict[str, Any] = {
        "status": OBSERVED if not missing and record.cleanup_valid else TODO_VERIFY,
        "ring_seq": record.ring_seq,
        "event_seq": record.event_seq,
        "caller_rva": record.caller_rva,
        "hook_rva": record.hook_rva,
        "result": record.result,
        "cleanup_valid": record.cleanup_valid,
        "missing": missing,
    }
    if "pre" in record.ui and "post" in record.ui:
        observation["ui"] = {
            "pre": record.ui["pre"],
            "post": record.ui["post"],
            "changes": _changes(record.ui["pre"], record.ui["post"]),
        }
    if "pre" in record.pools and "post" in record.pools:
        pre = record.pools["pre"]
        post = record.pools["post"]
        remove_pre = pre["remove_building_count"]
        remove_post = post["remove_building_count"]
        observation["pools"] = {
            "pre": {name: pre[name] for name in POOL_FIELDS},
            "post": {name: post[name] for name in POOL_FIELDS},
            "delta": _delta(pre, post),
            "unreadable": {
                "pre": pre["unreadable"],
                "post": post["unreadable"],
            },
        }
        observation["remove_building"] = {
            "pre": remove_pre,
            "post": remove_post,
            "delta": remove_post - remove_pre,
            "assessment": "PERSISTED" if remove_pre == remove_post else "CHANGED",
        }
    return observation


def _scenario(records: list[CleanupEvent], kind: str) -> dict[str, Any]:
    matching = [record for record in records if record.kind == kind]
    observations = [_observation(record) for record in matching]
    return {
        "status": (
            TODO_VERIFY
            if not observations or any(item["status"] != OBSERVED for item in observations)
            else OBSERVED
        ),
        "event_count": len(observations),
        "observations": observations,
    }


def _nested_connection_gmx(records: list[CleanupEvent]) -> dict[str, Any]:
    connections = [record for record in records if record.kind == "connection_lost"]
    gmx_events = [record for record in records if record.kind == "gmx_reset"]
    if not connections or not gmx_events:
        return {
            "status": TODO_VERIFY,
            "reason": "connection_lost or gmx_reset event missing",
            "pairs": [],
        }

    pairs: list[dict[str, int]] = []
    unpaired: list[int] = []
    used_gmx_ring_seqs: set[int] = set()
    for connection in connections:
        candidates = [
            gmx
            for gmx in gmx_events
            if gmx.ring_seq not in used_gmx_ring_seqs
            if gmx.event_seq > connection.event_seq
            and gmx.ring_seq < connection.ring_seq
        ]
        if not candidates:
            unpaired.append(connection.event_seq)
            continue
        nested = min(candidates, key=lambda item: item.event_seq)
        used_gmx_ring_seqs.add(nested.ring_seq)
        pairs.append(
            {
                "connection_event_seq": connection.event_seq,
                "connection_ring_seq": connection.ring_seq,
                "gmx_event_seq": nested.event_seq,
                "gmx_ring_seq": nested.ring_seq,
                "event_seq_delta": nested.event_seq - connection.event_seq,
                "publish_seq_delta": connection.ring_seq - nested.ring_seq,
            }
        )

    return {
        "status": OBSERVED if len(pairs) == len(connections) else MISMATCH,
        "reason": (
            "connection begins first by event_seq; nested GMX publishes first by ring_seq"
            if len(pairs) == len(connections)
            else "both event kinds exist but nested publish ordering was not observed"
        ),
        "pairs": pairs,
        "unpaired_connection_events": unpaired,
    }


def analyze_log(path: Path) -> dict[str, Any]:
    log_path = resolve_probe_log(path)
    trace = parse_trace(_read(log_path))
    scenarios = {
        kind: _scenario(trace.records, kind)
        for kind in TARGET_KINDS
    }
    nested = _nested_connection_gmx(trace.records)

    hook_status = (
        TODO_VERIFY
        if trace.hook_installed is None
        else (
            OBSERVED
            if trace.hook_installed == trace.hook_requested == 6
            else MISMATCH
        )
    )
    restore_status = (
        TODO_VERIFY
        if trace.restore_restored is None
        else (
            OBSERVED
            if trace.restore_restored == trace.restore_requested == 6
            else MISMATCH
        )
    )
    integrity_status = (
        MISMATCH
        if trace.parse_errors
        or trace.overflow_skipped
        or hook_status == MISMATCH
        or restore_status == MISMATCH
        else TODO_VERIFY
        if hook_status == TODO_VERIFY
        else OBSERVED
    )

    target_statuses = [scenario["status"] for scenario in scenarios.values()]
    if integrity_status == MISMATCH or nested["status"] == MISMATCH:
        assessment = MISMATCH
    elif all(status == TODO_VERIFY for status in target_statuses):
        assessment = TODO_VERIFY
    elif (
        all(status == OBSERVED for status in target_statuses)
        and nested["status"] == OBSERVED
        and integrity_status == OBSERVED
    ):
        assessment = "OBSERVED_COMPLETE"
    else:
        assessment = "OBSERVED_PARTIAL"

    return {
        "schema": 1,
        "source_log": str(log_path),
        "source_sha256": _sha256(log_path),
        "assessment": assessment,
        "evidence": ["PROBE_TRACE", "STATIC_037", "TODO_VERIFY"],
        "identity_policy": {
            "pointers": "excluded_from_output_and_event_pairing",
            "ticks": "excluded_from_output_and_event_pairing",
            "pairing": "kind+event_seq+ring_seq",
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
            },
            "parse_errors": trace.parse_errors,
            "orphan_details": trace.orphan_details,
        },
        "record_counts": {
            kind: sum(record.kind == kind for record in trace.records)
            for kind in sorted({record.kind for record in trace.records})
        },
        "scenarios": scenarios,
        "connection_lost_to_gmx_ordering": nested,
    }


def _render(result: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output is not None:
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
