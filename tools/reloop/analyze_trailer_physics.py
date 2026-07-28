#!/usr/bin/env python3
"""Summarize and compare focused trailer-physics ASI probe traces.

The probe emits one ``trailer_physics`` record followed by pre/post
``trailer_physics_state`` and ``trailer_physics_detail`` records.  Raw GTA
addresses are deliberately not compared: object relationships are reduced to
``trailer.tow == tractor`` and ``tractor.reverse == trailer`` first.

This analyzer reports measurements only.  It has no tolerance-based parity
verdict because acceptable residuals still need original 0.3.7 golden runs.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence


FRAME_LIMIT = 64
EVIDENCE = "PROBE_TRACE"
TOKEN_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_]*)="
    r"(?P<value>\([^)]*\)|[^\s]+)"
)
INTEGER_RE = re.compile(r"^[+-]?\d+$")
HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")


class TrailerPhysicsAnalysisError(RuntimeError):
    """An input cannot be used as a trailer-physics trace."""


@dataclasses.dataclass
class PhysicsRecord:
    line_number: int
    seq: int
    event: int
    generation: int
    frame: int
    kind: str
    values: dict[str, Any]
    states: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    details: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class PhysicsTrace:
    source: str
    records: list[PhysicsRecord] = dataclasses.field(default_factory=list)
    malformed_lines: list[int] = dataclasses.field(default_factory=list)
    orphan_auxiliary_lines: list[int] = dataclasses.field(default_factory=list)
    duplicate_auxiliary_lines: list[int] = dataclasses.field(default_factory=list)
    overflow_skipped: int = 0


def _parse_value(raw: str) -> Any:
    if raw.startswith("(") and raw.endswith(")"):
        values = raw[1:-1].split(",") if len(raw) > 2 else []
        parsed: list[Any] = []
        for value in values:
            parsed.append(_parse_value(value))
        return tuple(parsed)
    if HEX_RE.fullmatch(raw):
        return int(raw, 16)
    if INTEGER_RE.fullmatch(raw):
        return int(raw, 10)
    try:
        value = float(raw)
    except ValueError:
        return raw
    return value


def _tokens(text: str) -> dict[str, Any]:
    return {
        match.group("key"): _parse_value(match.group("value"))
        for match in TOKEN_RE.finditer(text)
    }


def _required_int(values: dict[str, Any], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} is not an integer")
    return value


def _record_identity(values: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        _required_int(values, "seq"),
        _required_int(values, "event"),
        _required_int(values, "generation"),
        _required_int(values, "frame"),
    )


def _find_record(
    records: Sequence[PhysicsRecord],
    identity: tuple[int, int, int, int],
) -> PhysicsRecord | None:
    for record in reversed(records):
        if (record.seq, record.event, record.generation, record.frame) == identity:
            return record
    return None


def _parse_state_payload(payload: str) -> tuple[dict[str, Any], str]:
    trailer_at = payload.find("trailer=")
    if trailer_at < 0:
        raise ValueError("missing trailer state")
    tractor_at = payload.find(" tractor=", trailer_at)
    if tractor_at < 0:
        raise ValueError("missing tractor state")

    prefix = _tokens(payload[:trailer_at])
    trailer = _tokens(payload[trailer_at:tractor_at])
    tractor = _tokens(payload[tractor_at + 1 :])
    phase = prefix.get("phase")
    if phase not in {"pre", "post"}:
        raise ValueError("invalid phase")
    trailer["object"] = trailer.pop("trailer")
    tractor["object"] = tractor.pop("tractor")
    return {
        "trailer": trailer,
        "tractor": tractor,
    }, phase


def parse_trace(text: str, source: str = "<memory>") -> PhysicsTrace:
    """Parse complete or partial probe output without assuming a log prefix."""
    trace = PhysicsTrace(source=source)

    for line_number, line in enumerate(text.splitlines(), start=1):
        if "trailer_physics: overflow " in line:
            values = _tokens(line.split("trailer_physics: overflow ", 1)[1])
            skipped = values.get("skipped")
            if isinstance(skipped, int) and skipped > 0:
                trace.overflow_skipped += skipped
            else:
                trace.malformed_lines.append(line_number)
            continue

        marker = "trailer_physics: "
        if marker in line:
            payload = line.split(marker, 1)[1]
            values = _tokens(payload)
            try:
                seq, event, generation, frame = _record_identity(values)
                kind = values["kind"]
                if kind not in {"set_tow_link", "process_control"}:
                    raise ValueError("invalid kind")
            except (KeyError, ValueError):
                trace.malformed_lines.append(line_number)
                continue
            trace.records.append(
                PhysicsRecord(
                    line_number=line_number,
                    seq=seq,
                    event=event,
                    generation=generation,
                    frame=frame,
                    kind=kind,
                    values=values,
                )
            )
            continue

        marker = "trailer_physics_state: "
        if marker in line:
            payload = line.split(marker, 1)[1]
            try:
                values = _tokens(payload)
                identity = _record_identity(values)
                state, phase = _parse_state_payload(payload)
            except (KeyError, ValueError):
                trace.malformed_lines.append(line_number)
                continue
            record = _find_record(trace.records, identity)
            if record is None:
                trace.orphan_auxiliary_lines.append(line_number)
            elif phase in record.states:
                trace.duplicate_auxiliary_lines.append(line_number)
            else:
                record.states[phase] = state
            continue

        marker = "trailer_physics_detail: "
        if marker in line:
            payload = line.split(marker, 1)[1]
            values = _tokens(payload)
            try:
                identity = _record_identity(values)
                phase = values["phase"]
                if phase not in {"pre", "post"}:
                    raise ValueError("invalid phase")
            except (KeyError, ValueError):
                trace.malformed_lines.append(line_number)
                continue
            record = _find_record(trace.records, identity)
            if record is None:
                trace.orphan_auxiliary_lines.append(line_number)
            elif phase in record.details:
                trace.duplicate_auxiliary_lines.append(line_number)
            else:
                record.details[phase] = values

    return trace


def load_trace(path: Path) -> PhysicsTrace:
    resolved = resolve_log_path(path)
    return parse_trace(
        resolved.read_text(encoding="utf-8", errors="replace"),
        source=str(resolved),
    )


def resolve_log_path(path: Path) -> Path:
    """Resolve a direct log or an artifact without selecting ``*.root.log``.

    Native-Windows collection stores the active Documents/SA-MP Logs file at
    ``windows/<run>/latest_log_bytes/samp_probe.log``.  The adjacent
    ``samp_probe.root.log`` can legitimately be empty, so it is never a
    candidate.
    """
    resolved = path.resolve()
    if resolved.is_file():
        return resolved
    if not resolved.is_dir():
        raise TrailerPhysicsAnalysisError(f"not a file or directory: {resolved}")

    patterns = (
        "windows/*/latest_log_bytes/samp_probe.log",
        "windows/*/logs/samp_probe.log",
        "latest_log_bytes/samp_probe.log",
        "logs/samp_probe.log",
        "client/samp_probe.log",
        "pilot/client/samp_probe.log",
        "observer/client/samp_probe.log",
    )
    for pattern in patterns:
        candidates = sorted(
            candidate
            for candidate in resolved.glob(pattern)
            if candidate.is_file() and candidate.stat().st_size > 0
        )
        if len(candidates) == 1:
            return candidates[0].resolve()
        if len(candidates) > 1:
            rendered = ", ".join(str(candidate) for candidate in candidates)
            raise TrailerPhysicsAnalysisError(
                f"ambiguous samp_probe.log beneath {resolved}: {rendered}"
            )
    raise TrailerPhysicsAnalysisError(
        f"no non-empty non-root samp_probe.log beneath {resolved}"
    )


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _vector(value: Any, length: int | None = None) -> tuple[float, ...] | None:
    if not isinstance(value, tuple):
        return None
    converted = tuple(_finite_float(component) for component in value)
    if any(component is None for component in converted):
        return None
    result = tuple(component for component in converted if component is not None)
    if length is not None and len(result) != length:
        return None
    return result


def _norm(value: Sequence[float]) -> float:
    return math.sqrt(sum(component * component for component in value))


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions differ")
    return _norm(tuple(a - b for a, b in zip(left, right)))


def _vector_distance(left: Any, right: Any, length: int | None = None) -> float | None:
    left_vector = _vector(left, length)
    right_vector = _vector(right, length)
    if left_vector is None or right_vector is None:
        return None
    return _distance(left_vector, right_vector)


def _stats(values: Iterable[float | None]) -> dict[str, Any]:
    finite = [
        number
        for value in values
        if value is not None and (number := _finite_float(value)) is not None
    ]
    if not finite:
        return {"count": 0}
    ordered = sorted(finite)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": statistics.fmean(ordered),
        "rms": math.sqrt(statistics.fmean(value * value for value in ordered)),
        "p95": ordered[p95_index],
        "max": ordered[-1],
    }


def _value_norm(value: Any, length: int | None = None) -> float | None:
    vector = _vector(value, length)
    return _norm(vector) if vector is not None else None


def _state_vehicle(
    record: PhysicsRecord, phase: str, vehicle: str
) -> dict[str, Any] | None:
    state = record.states.get(phase)
    if state is None:
        return None
    result = state.get(vehicle)
    return result if isinstance(result, dict) else None


def _link_state(record: PhysicsRecord, phase: str) -> dict[str, bool] | None:
    trailer = _state_vehicle(record, phase, "trailer")
    tractor = _state_vehicle(record, phase, "tractor")
    if trailer is None or tractor is None:
        return None
    trailer_object = trailer.get("object")
    tractor_object = tractor.get("object")
    trailer_tow = trailer.get("tow")
    tractor_reverse = tractor.get("reverse")
    if not all(
        isinstance(value, int)
        for value in (
            trailer_object,
            tractor_object,
            trailer_tow,
            tractor_reverse,
        )
    ):
        return None
    tow_matches = tractor_object != 0 and trailer_tow == tractor_object
    reverse_matches = trailer_object != 0 and tractor_reverse == trailer_object
    return {
        "trailer_tow_matches_tractor": tow_matches,
        "tractor_reverse_matches_trailer": reverse_matches,
        "bidirectional": tow_matches and reverse_matches,
    }


def _record_snapshot(record: PhysicsRecord) -> dict[str, Any]:
    result: dict[str, Any] = {
        "frame": record.frame,
        "trailer_dpos": record.values.get("trailer_dpos"),
        "tractor_dpos": record.values.get("tractor_dpos"),
    }
    for phase in ("pre", "post"):
        phase_result: dict[str, Any] = {}
        for vehicle_name in ("trailer", "tractor"):
            vehicle = _state_vehicle(record, phase, vehicle_name)
            if vehicle is None:
                continue
            phase_result[vehicle_name] = {
                key: vehicle.get(key)
                for key in (
                    "valid",
                    "basis_r",
                    "basis_f",
                    "basis_u",
                    "pos",
                    "move",
                    "turn",
                    "flags",
                    "status",
                    "fake",
                )
            }
        link = _link_state(record, phase)
        if link is not None:
            phase_result["link"] = link
        detail = record.details.get(phase)
        if detail is not None:
            phase_result["trailer_detail"] = {
                key: detail.get(key)
                for key in (
                    "trailer_valid",
                    "support",
                    "wheel",
                    "wheel_prev",
                    "spring",
                    "line",
                    "ride",
                )
            }
        result[phase] = phase_result
    return result


def _unique_frames(records: Iterable[PhysicsRecord]) -> tuple[dict[int, PhysicsRecord], list[int]]:
    by_frame: dict[int, PhysicsRecord] = {}
    counts: Counter[int] = Counter()
    for record in records:
        if record.kind != "process_control" or not 0 <= record.frame < FRAME_LIMIT:
            continue
        counts[record.frame] += 1
        by_frame.setdefault(record.frame, record)
    duplicates = sorted(frame for frame, count in counts.items() if count > 1)
    return by_frame, duplicates


def _generation_order(trace: PhysicsTrace) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for record in trace.records:
        if record.generation <= 0 or record.generation in seen:
            continue
        seen.add(record.generation)
        ordered.append(record.generation)
    return ordered


def _elapsed_u32(current: Any, first: Any) -> int | None:
    if not isinstance(current, int) or not isinstance(first, int):
        return None
    return (current - first) & 0xFFFFFFFF


def _generation_summary(
    trace: PhysicsTrace, generation: int, ordinal: int
) -> dict[str, Any]:
    records = [record for record in trace.records if record.generation == generation]
    attach = [record for record in records if record.kind == "set_tow_link"]
    frame_map, duplicate_frames = _unique_frames(records)
    frames = [frame_map[index] for index in sorted(frame_map)]
    expected = set(range(FRAME_LIMIT))
    observed = set(frame_map)
    contiguous = 0
    while contiguous in observed:
        contiguous += 1

    first_game_ms = frames[0].values.get("pre_game_ms") if frames else None
    link_pre = [_link_state(frame, "pre") for frame in frames]
    link_post = [_link_state(frame, "post") for frame in frames]
    link_loss_frames: list[int] = []
    link_recovery_frames: list[int] = []
    previous_linked = (
        _linked(attach[0], "post") if attach else None
    )
    sequence_status_changes: list[dict[str, int]] = []
    previous_status: int | None = None
    if attach:
        attach_post = _state_vehicle(attach[0], "post", "trailer")
        if attach_post is not None and isinstance(attach_post.get("status"), int):
            previous_status = attach_post["status"]
    for frame in frames:
        pre_linked = _linked(frame, "pre")
        if previous_linked is True and pre_linked is False:
            link_loss_frames.append(frame.frame)
        elif previous_linked is False and pre_linked is True:
            link_recovery_frames.append(frame.frame)
        if pre_linked is not None:
            previous_linked = pre_linked

        trailer_pre = _state_vehicle(frame, "pre", "trailer")
        trailer_post = _state_vehicle(frame, "post", "trailer")
        pre_status = trailer_pre.get("status") if trailer_pre is not None else None
        post_status = trailer_post.get("status") if trailer_post is not None else None
        if (
            isinstance(previous_status, int)
            and isinstance(pre_status, int)
            and previous_status != pre_status
        ):
            sequence_status_changes.append(
                {
                    "frame": frame.frame,
                    "from": previous_status,
                    "to": pre_status,
                }
            )
        if isinstance(post_status, int):
            previous_status = post_status
        elif isinstance(pre_status, int):
            previous_status = pre_status
    complete_aux = sum(
        set(record.states) == {"pre", "post"}
        and set(record.details) == {"pre", "post"}
        for record in records
    )

    return {
        "ordinal": ordinal,
        "generation": generation,
        "set_tow_link_events": len(attach),
        "set_tow_link": (
            {
                "result": attach[0].values.get("result"),
                "set_my_pos_raw": attach[0].values.get("set_my_pos_raw"),
                "trailer_jump_m": _value_norm(
                    attach[0].values.get("trailer_dpos"), 3
                ),
                "tractor_jump_m": _value_norm(
                    attach[0].values.get("tractor_dpos"), 3
                ),
                "link_pre": _link_state(attach[0], "pre"),
                "link_post": _link_state(attach[0], "post"),
                "state": _record_snapshot(attach[0]),
            }
            if attach
            else None
        ),
        "process_control": {
            "frames_observed": len(frames),
            "frame_indices": sorted(observed),
            "contiguous_prefix_frames": contiguous,
            "missing_first_64": sorted(expected - observed),
            "duplicate_frames": duplicate_frames,
            "trailer_step_m": _stats(
                _value_norm(record.values.get("trailer_dpos"), 3)
                for record in frames
            ),
            "tractor_step_m": _stats(
                _value_norm(record.values.get("tractor_dpos"), 3)
                for record in frames
            ),
            "pre_timestep": _stats(
                _finite_float(record.values.get("pre_timestep"))
                for record in frames
            ),
            "elapsed_game_ms": _stats(
                _elapsed_u32(record.values.get("pre_game_ms"), first_game_ms)
                for record in frames
            ),
            "pre_linked_frames": sum(
                bool(link and link["bidirectional"]) for link in link_pre
            ),
            "post_linked_frames": sum(
                bool(link and link["bidirectional"]) for link in link_post
            ),
            "link_loss_frames": link_loss_frames,
            "link_recovery_frames": link_recovery_frames,
            "trailer_status_changes_between_frames": sequence_status_changes,
            "trailer_move_speed_effect": _stats(
                _value_norm(_state_effect(record, "trailer", "move", 3), 3)
                for record in frames
            ),
            "trailer_turn_speed_effect": _stats(
                _value_norm(_state_effect(record, "trailer", "turn", 3), 3)
                for record in frames
            ),
            "tractor_move_speed_effect": _stats(
                _value_norm(_state_effect(record, "tractor", "move", 3), 3)
                for record in frames
            ),
            "tractor_turn_speed_effect": _stats(
                _value_norm(_state_effect(record, "tractor", "turn", 3), 3)
                for record in frames
            ),
            "support_effect": _stats(
                _value_norm(_detail_effect(record, "support", 5), 5)
                for record in frames
            ),
            "wheel_compression_effect": _stats(
                _value_norm(_detail_effect(record, "wheel", 4), 4)
                for record in frames
            ),
            "complete_pre_post_state_and_detail_records": complete_aux,
            "first_frame": _record_snapshot(frames[0]) if frames else None,
            "last_frame": _record_snapshot(frames[-1]) if frames else None,
        },
    }


def summarize_trace(trace: PhysicsTrace) -> dict[str, Any]:
    set_tow_link = [
        record for record in trace.records if record.kind == "set_tow_link"
    ]
    process_control = [
        record for record in trace.records if record.kind == "process_control"
    ]
    generations = _generation_order(trace)
    attach_intervals = [
        _elapsed_u32(
            set_tow_link[index].values.get("pre_game_ms"),
            set_tow_link[index - 1].values.get("pre_game_ms"),
        )
        for index in range(1, len(set_tow_link))
    ]
    return {
        "schema_version": 1,
        "source": trace.source,
        "evidence": EVIDENCE,
        "assessment": "MEASURED_NO_PARITY_THRESHOLD",
        "parse": {
            "physics_records": len(trace.records),
            "set_tow_link_records": len(set_tow_link),
            "process_control_records": len(process_control),
            "malformed_lines": trace.malformed_lines,
            "orphan_auxiliary_lines": trace.orphan_auxiliary_lines,
            "duplicate_auxiliary_lines": trace.duplicate_auxiliary_lines,
            "overflow_skipped": trace.overflow_skipped,
            "untracked_generation_zero_records": sum(
                record.generation == 0 for record in trace.records
            ),
        },
        "set_tow_link": {
            "events": len(set_tow_link),
            "successful_results": sum(
                record.values.get("result") == 1 for record in set_tow_link
            ),
            "trailer_jump_m": _stats(
                _value_norm(record.values.get("trailer_dpos"), 3)
                for record in set_tow_link
            ),
            "tractor_jump_m": _stats(
                _value_norm(record.values.get("tractor_dpos"), 3)
                for record in set_tow_link
            ),
            "inter_event_game_ms": _stats(attach_intervals),
            "intervals_le_100ms": sum(
                interval is not None and interval <= 100
                for interval in attach_intervals
            ),
            "intervals_le_250ms": sum(
                interval is not None and interval <= 250
                for interval in attach_intervals
            ),
            "bidirectional_link_pre": sum(
                bool(link and link["bidirectional"])
                for record in set_tow_link
                if (link := _link_state(record, "pre")) is not None
            ),
            "bidirectional_link_post": sum(
                bool(link and link["bidirectional"])
                for record in set_tow_link
                if (link := _link_state(record, "post")) is not None
            ),
        },
        "generations": [
            _generation_summary(trace, generation, ordinal)
            for ordinal, generation in enumerate(generations)
        ],
    }


def _metric(
    records: Iterable[tuple[PhysicsRecord, PhysicsRecord]],
    getter,
) -> dict[str, Any]:
    return _stats(getter(original, replacement) for original, replacement in records)


def _vehicle_vector_metric(
    original: PhysicsRecord,
    replacement: PhysicsRecord,
    phase: str,
    vehicle: str,
    key: str,
    length: int | None = None,
) -> float | None:
    original_vehicle = _state_vehicle(original, phase, vehicle)
    replacement_vehicle = _state_vehicle(replacement, phase, vehicle)
    if original_vehicle is None or replacement_vehicle is None:
        return None
    return _vector_distance(
        original_vehicle.get(key), replacement_vehicle.get(key), length
    )


def _state_vector(
    record: PhysicsRecord,
    phase: str,
    vehicle: str,
    key: str,
    length: int | None = None,
) -> tuple[float, ...] | None:
    state = _state_vehicle(record, phase, vehicle)
    if state is None:
        return None
    return _vector(state.get(key), length)


def _detail_vector(
    record: PhysicsRecord,
    phase: str,
    key: str,
    length: int | None = None,
) -> tuple[float, ...] | None:
    detail = record.details.get(phase)
    if detail is None:
        return None
    return _vector(detail.get(key), length)


def _vector_effect(
    before: Sequence[float] | None,
    after: Sequence[float] | None,
) -> tuple[float, ...] | None:
    if before is None or after is None or len(before) != len(after):
        return None
    return tuple(right - left for left, right in zip(before, after))


def _state_effect(
    record: PhysicsRecord,
    vehicle: str,
    key: str,
    length: int | None = None,
) -> tuple[float, ...] | None:
    return _vector_effect(
        _state_vector(record, "pre", vehicle, key, length),
        _state_vector(record, "post", vehicle, key, length),
    )


def _detail_effect(
    record: PhysicsRecord,
    key: str,
    length: int | None = None,
) -> tuple[float, ...] | None:
    return _vector_effect(
        _detail_vector(record, "pre", key, length),
        _detail_vector(record, "post", key, length),
    )


def _effect_delta(
    original_effect: Sequence[float] | None,
    replacement_effect: Sequence[float] | None,
) -> float | None:
    if original_effect is None or replacement_effect is None:
        return None
    return _distance(original_effect, replacement_effect)


def _detail_vector_metric(
    original: PhysicsRecord,
    replacement: PhysicsRecord,
    phase: str,
    key: str,
    length: int | None = None,
) -> float | None:
    original_detail = original.details.get(phase)
    replacement_detail = replacement.details.get(phase)
    if original_detail is None or replacement_detail is None:
        return None
    return _vector_distance(
        original_detail.get(key), replacement_detail.get(key), length
    )


def _bool_mismatch(left: Any, right: Any) -> bool | None:
    if left is None or right is None:
        return None
    return left != right


def _vehicle_scalar(
    record: PhysicsRecord, phase: str, vehicle: str, key: str
) -> Any:
    state = _state_vehicle(record, phase, vehicle)
    return state.get(key) if state is not None else None


def _integer_xor(left: Any, right: Any) -> int | None:
    if not isinstance(left, int) or not isinstance(right, int):
        return None
    return left ^ right


def _linked(record: PhysicsRecord, phase: str) -> bool | None:
    link = _link_state(record, phase)
    return link["bidirectional"] if link is not None else None


def _generation_diff(
    original_trace: PhysicsTrace,
    replacement_trace: PhysicsTrace,
    original_generation: int,
    replacement_generation: int,
    ordinal: int,
) -> dict[str, Any]:
    original_records = [
        record
        for record in original_trace.records
        if record.generation == original_generation
    ]
    replacement_records = [
        record
        for record in replacement_trace.records
        if record.generation == replacement_generation
    ]
    original_frames, original_duplicates = _unique_frames(original_records)
    replacement_frames, replacement_duplicates = _unique_frames(replacement_records)
    common_indices = sorted(set(original_frames) & set(replacement_frames))
    pairs = [
        (original_frames[index], replacement_frames[index])
        for index in common_indices
    ]

    original_attach = next(
        (record for record in original_records if record.kind == "set_tow_link"),
        None,
    )
    replacement_attach = next(
        (record for record in replacement_records if record.kind == "set_tow_link"),
        None,
    )
    attach_delta = None
    if original_attach is not None and replacement_attach is not None:
        attach_delta = {
            "trailer_jump_vector_delta_m": _vector_distance(
                original_attach.values.get("trailer_dpos"),
                replacement_attach.values.get("trailer_dpos"),
                3,
            ),
            "tractor_jump_vector_delta_m": _vector_distance(
                original_attach.values.get("tractor_dpos"),
                replacement_attach.values.get("tractor_dpos"),
                3,
            ),
            "pre_link_mismatch": _bool_mismatch(
                _linked(original_attach, "pre"),
                _linked(replacement_attach, "pre"),
            ),
            "post_link_mismatch": _bool_mismatch(
                _linked(original_attach, "post"),
                _linked(replacement_attach, "post"),
            ),
            "trailer_pre_position_residual_m": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "trailer",
                "pos",
                3,
            ),
            "trailer_post_position_residual_m": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "post",
                "trailer",
                "pos",
                3,
            ),
            "tractor_pre_position_residual_m": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "tractor",
                "pos",
                3,
            ),
            "trailer_pre_move_speed_delta": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "trailer",
                "move",
                3,
            ),
            "tractor_pre_move_speed_delta": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "tractor",
                "move",
                3,
            ),
            "trailer_pre_turn_speed_delta": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "trailer",
                "turn",
                3,
            ),
            "tractor_pre_turn_speed_delta": _vehicle_vector_metric(
                original_attach,
                replacement_attach,
                "pre",
                "tractor",
                "turn",
                3,
            ),
            "trailer_pre_flags_xor": _integer_xor(
                _vehicle_scalar(original_attach, "pre", "trailer", "flags"),
                _vehicle_scalar(
                    replacement_attach, "pre", "trailer", "flags"
                ),
            ),
            "tractor_pre_flags_xor": _integer_xor(
                _vehicle_scalar(original_attach, "pre", "tractor", "flags"),
                _vehicle_scalar(
                    replacement_attach, "pre", "tractor", "flags"
                ),
            ),
            "trailer_pre_status_mismatch": _bool_mismatch(
                _vehicle_scalar(original_attach, "pre", "trailer", "status"),
                _vehicle_scalar(
                    replacement_attach, "pre", "trailer", "status"
                ),
            ),
            "tractor_pre_status_mismatch": _bool_mismatch(
                _vehicle_scalar(original_attach, "pre", "tractor", "status"),
                _vehicle_scalar(
                    replacement_attach, "pre", "tractor", "status"
                ),
            ),
        }

    original_first_ms = (
        original_frames[common_indices[0]].values.get("pre_game_ms")
        if common_indices
        else None
    )
    replacement_first_ms = (
        replacement_frames[common_indices[0]].values.get("pre_game_ms")
        if common_indices
        else None
    )

    def elapsed_delta(
        original: PhysicsRecord, replacement: PhysicsRecord
    ) -> float | None:
        original_elapsed = _elapsed_u32(
            original.values.get("pre_game_ms"), original_first_ms
        )
        replacement_elapsed = _elapsed_u32(
            replacement.values.get("pre_game_ms"), replacement_first_ms
        )
        if original_elapsed is None or replacement_elapsed is None:
            return None
        return abs(float(original_elapsed - replacement_elapsed))

    pre_link_mismatches = [
        _bool_mismatch(_linked(original, "pre"), _linked(replacement, "pre"))
        for original, replacement in pairs
    ]
    post_link_mismatches = [
        _bool_mismatch(_linked(original, "post"), _linked(replacement, "post"))
        for original, replacement in pairs
    ]

    return {
        "ordinal": ordinal,
        "original_generation": original_generation,
        "replacement_generation": replacement_generation,
        "attach": attach_delta,
        "frames": {
            "original_observed": len(original_frames),
            "replacement_observed": len(replacement_frames),
            "common": len(common_indices),
            "common_indices": common_indices,
            "missing_in_replacement": sorted(
                set(original_frames) - set(replacement_frames)
            ),
            "extra_in_replacement": sorted(
                set(replacement_frames) - set(original_frames)
            ),
            "original_duplicate_frames": original_duplicates,
            "replacement_duplicate_frames": replacement_duplicates,
        },
        "metrics": {
            "trailer_step_vector_delta_m": _metric(
                pairs,
                lambda original, replacement: _vector_distance(
                    original.values.get("trailer_dpos"),
                    replacement.values.get("trailer_dpos"),
                    3,
                ),
            ),
            "tractor_step_vector_delta_m": _metric(
                pairs,
                lambda original, replacement: _vector_distance(
                    original.values.get("tractor_dpos"),
                    replacement.values.get("tractor_dpos"),
                    3,
                ),
            ),
            "trailer_pre_position_residual_m": _metric(
                pairs,
                lambda original, replacement: _vehicle_vector_metric(
                    original, replacement, "pre", "trailer", "pos", 3
                ),
            ),
            "trailer_post_position_residual_m": _metric(
                pairs,
                lambda original, replacement: _vehicle_vector_metric(
                    original, replacement, "post", "trailer", "pos", 3
                ),
            ),
            "tractor_pre_position_residual_m": _metric(
                pairs,
                lambda original, replacement: _vehicle_vector_metric(
                    original, replacement, "pre", "tractor", "pos", 3
                ),
            ),
            "trailer_pre_move_speed_delta": _metric(
                pairs,
                lambda original, replacement: _vehicle_vector_metric(
                    original, replacement, "pre", "trailer", "move", 3
                ),
            ),
            "trailer_pre_turn_speed_delta": _metric(
                pairs,
                lambda original, replacement: _vehicle_vector_metric(
                    original, replacement, "pre", "trailer", "turn", 3
                ),
            ),
            "trailer_move_speed_effect_delta": _metric(
                pairs,
                lambda original, replacement: _effect_delta(
                    _state_effect(original, "trailer", "move", 3),
                    _state_effect(replacement, "trailer", "move", 3),
                ),
            ),
            "trailer_turn_speed_effect_delta": _metric(
                pairs,
                lambda original, replacement: _effect_delta(
                    _state_effect(original, "trailer", "turn", 3),
                    _state_effect(replacement, "trailer", "turn", 3),
                ),
            ),
            "tractor_move_speed_effect_delta": _metric(
                pairs,
                lambda original, replacement: _effect_delta(
                    _state_effect(original, "tractor", "move", 3),
                    _state_effect(replacement, "tractor", "move", 3),
                ),
            ),
            "support_pre_delta": _metric(
                pairs,
                lambda original, replacement: _detail_vector_metric(
                    original, replacement, "pre", "support", 5
                ),
            ),
            "support_effect_delta": _metric(
                pairs,
                lambda original, replacement: _effect_delta(
                    _detail_effect(original, "support", 5),
                    _detail_effect(replacement, "support", 5),
                ),
            ),
            "wheel_compression_pre_delta": _metric(
                pairs,
                lambda original, replacement: _detail_vector_metric(
                    original, replacement, "pre", "wheel", 4
                ),
            ),
            "wheel_compression_effect_delta": _metric(
                pairs,
                lambda original, replacement: _effect_delta(
                    _detail_effect(original, "wheel", 4),
                    _detail_effect(replacement, "wheel", 4),
                ),
            ),
            "pre_timestep_abs_delta": _metric(
                pairs,
                lambda original, replacement: (
                    abs(original_value - replacement_value)
                    if (
                        original_value := _finite_float(
                            original.values.get("pre_timestep")
                        )
                    )
                    is not None
                    and (
                        replacement_value := _finite_float(
                            replacement.values.get("pre_timestep")
                        )
                    )
                    is not None
                    else None
                ),
            ),
            "relative_game_time_abs_delta_ms": _metric(pairs, elapsed_delta),
        },
        "state_mismatches": {
            "pre_link": sum(value is True for value in pre_link_mismatches),
            "post_link": sum(value is True for value in post_link_mismatches),
            "pre_link_comparable": sum(value is not None for value in pre_link_mismatches),
            "post_link_comparable": sum(
                value is not None for value in post_link_mismatches
            ),
        },
    }


def compare_traces(
    original_trace: PhysicsTrace, replacement_trace: PhysicsTrace
) -> dict[str, Any]:
    """Diff generations by attach encounter order, never by raw pointer."""
    original_generations = _generation_order(original_trace)
    replacement_generations = _generation_order(replacement_trace)
    original_attach_count = sum(
        record.kind == "set_tow_link" for record in original_trace.records
    )
    replacement_attach_count = sum(
        record.kind == "set_tow_link" for record in replacement_trace.records
    )
    paired = min(len(original_generations), len(replacement_generations))
    return {
        "schema_version": 1,
        "comparison": "original_vs_replacement",
        "evidence": EVIDENCE,
        "assessment": "MEASURED_NO_PARITY_THRESHOLD",
        "pointer_policy": "raw_addresses_ignored_relationships_compared",
        "generation_pairing_policy": "successful_attach_encounter_order",
        "set_tow_link_comparison": {
            "original_events": original_attach_count,
            "replacement_events": replacement_attach_count,
            "replacement_minus_original": (
                replacement_attach_count - original_attach_count
            ),
        },
        "original": summarize_trace(original_trace),
        "replacement": summarize_trace(replacement_trace),
        "generation_pairs": [
            _generation_diff(
                original_trace,
                replacement_trace,
                original_generations[index],
                replacement_generations[index],
                index,
            )
            for index in range(paired)
        ],
        "unpaired_generations": {
            "original": original_generations[paired:],
            "replacement": replacement_generations[paired:],
        },
    }


def _render(result: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser(
        "summary", help="summarize one samp_probe.log"
    )
    summary_parser.add_argument("log", type=Path)
    summary_parser.add_argument("--output", type=Path)

    diff_parser = subparsers.add_parser(
        "diff", help="compare original and replacement samp_probe.log files"
    )
    diff_parser.add_argument("original", type=Path)
    diff_parser.add_argument("replacement", type=Path)
    diff_parser.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            trace = load_trace(args.log)
            result = summarize_trace(trace)
            _render(result, args.output)
            return 0 if trace.records else 1

        original = load_trace(args.original)
        replacement = load_trace(args.replacement)
        result = compare_traces(original, replacement)
        _render(result, args.output)
        return 0 if original.records and replacement.records else 1
    except (OSError, TrailerPhysicsAnalysisError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
