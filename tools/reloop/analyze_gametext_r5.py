#!/usr/bin/env python3
"""Validate the focused raw-RPC73 GameText replacement sequence.

This analyzer is intentionally strict and artifact-only.  It proves that the
closed server fixture sent both raw RPC 73 payloads, that the replacement
decoded the expected styles/texts, and that its runtime globally cleared the
style-5 GameText before installing style 3.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence


FIRST_TEXT = "RPC73_STYLE5_FIRST"
REPLACEMENT_TEXT = "RPC73_STYLE3_SECOND"
FIRST_PAYLOAD = (
    "05 00 00 00 88 13 00 00 12 00 00 00 "
    "52 50 43 37 33 5f 53 54 59 4c 45 35 5f 46 49 52 53 54"
)
REPLACEMENT_PAYLOAD = (
    "03 00 00 00 88 13 00 00 13 00 00 00 "
    "52 50 43 37 33 5f 53 54 59 4c 45 33 5f 53 45 43 4f 4e 44"
)

TOKEN_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_]*)="
    r"(?P<value>'[^']*'|[^\s]+)"
)
INTEGER_RE = re.compile(r"^[+-]?\d+$")
BYTE_SEQUENCE_RE = re.compile(r"^[0-9a-fA-F]{2}(?:\s+[0-9a-fA-F]{2})*$")

FIRST_FIXTURE = {
    "phase": "first",
    "rpc": 73,
    "style": 5,
    "time_ms": 5000,
    "text_len": 18,
    "payload_bits": 240,
    "payload": FIRST_PAYLOAD.replace(" ", ""),
    "text": FIRST_TEXT,
    "dispatchEvents": 0,
    "channel": 2,
    "sent": 1,
}
REPLACEMENT_FIXTURE = {
    "phase": "replacement",
    "rpc": 73,
    "style": 3,
    "time_ms": 5000,
    "text_len": 19,
    "payload_bits": 248,
    "payload": REPLACEMENT_PAYLOAD.replace(" ", ""),
    "text": REPLACEMENT_TEXT,
    "dispatchEvents": 0,
    "channel": 2,
    "sent": 1,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_value(raw: str) -> str | int:
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1]
    if INTEGER_RE.fullmatch(raw):
        return int(raw)
    return raw


def _tokens(line: str) -> dict[str, str | int]:
    return {
        match.group("key"): _parse_value(match.group("value"))
        for match in TOKEN_RE.finditer(line)
    }


def _records(text: str, marker: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if marker not in line:
            continue
        record: dict[str, Any] = {"line": line_number}
        record.update(_tokens(line))
        records.append(record)
    return records


def _exact_record(
    records: list[dict[str, Any]], expected: dict[str, str | int]
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if all(record.get(key) == value for key, value in expected.items())
    ]


def _resolve_one(root: Path, candidates: Sequence[str], label: str) -> Path:
    for relative in candidates:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"missing {label}; tried: "
        + ", ".join(str(root / relative) for relative in candidates)
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _raw_rpc73_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    marker = "rpc-in id=73 name=ScrDisplayGameText "
    for line_number, line in enumerate(text.splitlines(), 1):
        if marker not in line or " first=" not in line:
            continue
        prefix, raw_payload = line.split(" first=", 1)
        payload = " ".join(raw_payload.strip().split()).lower()
        record: dict[str, Any] = {
            "line": line_number,
            "payload": payload if BYTE_SEQUENCE_RE.fullmatch(payload) else None,
        }
        record.update(_tokens(prefix))
        records.append(record)
    return records


def _runtime_lifecycle(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if "game_text: show " in line:
            kind = "show"
        elif "game_text: clear_all " in line:
            kind = "clear_all"
        else:
            continue
        record: dict[str, Any] = {"line": line_number, "kind": kind}
        record.update(_tokens(line))
        records.append(record)
    return records


def _exception_filter_occurrences(root: Path) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.log")):
        if not path.is_file():
            continue
        for line_number, line in enumerate(_read(path).splitlines(), 1):
            if "exception_filter" in line.lower():
                occurrences.append(
                    {
                        "file": _relative(path, root),
                        "line": line_number,
                    }
                )
    return occurrences


def analyze(run: Path) -> dict[str, Any]:
    root = run.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)

    server_path = _resolve_one(
        root, ("server.console.log", "server.log"), "server log"
    )
    net_path = _resolve_one(
        root,
        (
            "client/samp_net_trace.log",
            "pilot/client/samp_net_trace.log",
            "observer/client/samp_net_trace.log",
        ),
        "client samp_net_trace.log",
    )
    runtime_path = _resolve_one(
        root,
        (
            "client/samp_runtime.log",
            "pilot/client/samp_runtime.log",
            "observer/client/samp_runtime.log",
        ),
        "client samp_runtime.log",
    )

    server = _read(server_path)
    net = _read(net_path)
    runtime = _read(runtime_path)

    fixture_records = _records(server, "[rpc73_gametext_fixture] phase=")
    fixture_first = _exact_record(fixture_records, FIRST_FIXTURE)
    fixture_replacement = _exact_record(
        fixture_records, REPLACEMENT_FIXTURE
    )

    raw_records = _raw_rpc73_records(net)
    raw_first = [
        record
        for record in raw_records
        if record.get("count") == 2
        and record.get("bits") == 240
        and record.get("bytes") == 30
        and record.get("payload") == FIRST_PAYLOAD
    ]
    raw_replacement = [
        record
        for record in raw_records
        if record.get("count") == 3
        and record.get("bits") == 248
        and record.get("bytes") == 31
        and record.get("payload") == REPLACEMENT_PAYLOAD
    ]

    state_records = _records(net, "rpc-state id=73 game_text_seq=")
    state_first = _exact_record(
        state_records,
        {
            "id": 73,
            "game_text_seq": 2,
            "action": "show",
            "style": 5,
            "time": 5000,
            "text": FIRST_TEXT,
        },
    )
    state_replacement = _exact_record(
        state_records,
        {
            "id": 73,
            "game_text_seq": 3,
            "action": "show",
            "style": 3,
            "time": 5000,
            "text": REPLACEMENT_TEXT,
        },
    )

    lifecycle = _runtime_lifecycle(runtime)
    runtime_first = _exact_record(
        lifecycle,
        {
            "kind": "show",
            "seq": 2,
            "style": 5,
            "time": 5000,
            "text": FIRST_TEXT,
        },
    )
    runtime_clear = _exact_record(
        lifecycle,
        {
            "kind": "clear_all",
            "seq": 3,
            "cleared": 1,
            "reason": "replace_before_show",
        },
    )
    runtime_replacement = _exact_record(
        lifecycle,
        {
            "kind": "show",
            "seq": 3,
            "style": 3,
            "time": 5000,
            "text": REPLACEMENT_TEXT,
        },
    )

    fixture_order = (
        len(fixture_first) == 1
        and len(fixture_replacement) == 1
        and fixture_first[0]["line"] < fixture_replacement[0]["line"]
    )
    net_order = (
        len(raw_first) == 1
        and len(state_first) == 1
        and len(raw_replacement) == 1
        and len(state_replacement) == 1
        and raw_first[0]["line"]
        < state_first[0]["line"]
        < raw_replacement[0]["line"]
        < state_replacement[0]["line"]
    )
    runtime_order = (
        len(runtime_first) == 1
        and len(runtime_clear) == 1
        and len(runtime_replacement) == 1
        and runtime_first[0]["line"]
        < runtime_clear[0]["line"]
        < runtime_replacement[0]["line"]
    )

    exception_filter = _exception_filter_occurrences(root)
    checks = {
        "fixture_first_sent": len(fixture_first) == 1,
        "fixture_replacement_sent": len(fixture_replacement) == 1,
        "fixture_first_before_replacement": fixture_order,
        "net_raw_rpc73_first": len(raw_first) == 1,
        "net_rpc73_first_style_text": len(state_first) == 1,
        "net_raw_rpc73_replacement": len(raw_replacement) == 1,
        "net_rpc73_replacement_style_text": len(state_replacement) == 1,
        "net_rpc73_sequence": net_order,
        "runtime_show_seq2_style5": len(runtime_first) == 1,
        "runtime_clear_seq3_cleared1": len(runtime_clear) == 1,
        "runtime_show_seq3_style3": len(runtime_replacement) == 1,
        "runtime_replacement_sequence": runtime_order,
        "no_exception_filter": not exception_filter,
    }
    verdict = "PASS" if all(checks.values()) else "MISMATCH"

    def lines(records: list[dict[str, Any]]) -> list[int]:
        return [int(record["line"]) for record in records]

    return {
        "schema": 1,
        "run": str(root),
        "verdict": verdict,
        "evidence": ["STATIC_037", "PROBE_TRACE"],
        "checks": checks,
        "sources": {
            "server": {
                "path": _relative(server_path, root),
                "sha256": _sha256(server_path),
            },
            "net": {
                "path": _relative(net_path, root),
                "sha256": _sha256(net_path),
            },
            "runtime": {
                "path": _relative(runtime_path, root),
                "sha256": _sha256(runtime_path),
            },
        },
        "observations": {
            "fixture": {
                "first_lines": lines(fixture_first),
                "replacement_lines": lines(fixture_replacement),
            },
            "net": {
                "raw_first_lines": lines(raw_first),
                "state_first_lines": lines(state_first),
                "raw_replacement_lines": lines(raw_replacement),
                "state_replacement_lines": lines(state_replacement),
            },
            "runtime": {
                "show_seq2_style5_lines": lines(runtime_first),
                "clear_seq3_cleared1_lines": lines(runtime_clear),
                "show_seq3_style3_lines": lines(runtime_replacement),
            },
            "exception_filter": exception_filter,
        },
        "contract": {
            "fixture": (
                "one fixed raw RPC73 style-5 payload followed by one fixed "
                "raw RPC73 style-3 payload"
            ),
            "runtime": (
                "show seq2 style5 -> clear_all seq3 cleared=1 -> "
                "show seq3 style3"
            ),
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
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze(args.artifact)
    except (FileNotFoundError, OSError, ValueError) as error:
        parser.error(str(error))
    _render(result, args.output)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
