#!/usr/bin/env python3
"""Unit tests for the focused raw-RPC73 GameText analyzer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from analyze_gametext_r5 import (  # noqa: E402
    FIRST_PAYLOAD,
    FIRST_TEXT,
    REPLACEMENT_PAYLOAD,
    REPLACEMENT_TEXT,
    analyze,
    main,
)


GOLDEN_ARTIFACT = (
    REPOSITORY_ROOT
    / "artifacts/runs/20260728-155306-replacement-pvars-1747209"
)


def valid_server() -> str:
    return "\n".join(
        (
            "[rpc73_gametext_fixture] phase=first player=0 rpc=73 "
            "style=5 time_ms=5000 text_len=18 payload_bits=240 "
            "payload=05000000881300001200000052504337335f5354594c45355f4649525354 "
            "text=RPC73_STYLE5_FIRST dispatchEvents=0 channel=2 sent=1",
            "[rpc73_gametext_fixture] scheduled player=0 "
            "replacement_delay_ms=350 generation=1",
            "[rpc73_gametext_fixture] phase=replacement player=0 rpc=73 "
            "style=3 time_ms=5000 text_len=19 payload_bits=248 "
            "payload=03000000881300001300000052504337335f5354594c45335f5345434f4e44 "
            "text=RPC73_STYLE3_SECOND dispatchEvents=0 channel=2 sent=1",
        )
    ) + "\n"


def valid_net() -> str:
    return "\n".join(
        (
            "rpc-in id=73 name=ScrDisplayGameText local=implemented "
            f"count=2 bits=240 bytes=30 first={FIRST_PAYLOAD}",
            "rpc-state id=73 game_text_seq=2 action=show style=5 time=5000 "
            f"text='{FIRST_TEXT}' evidence=PROBE_TRACE",
            "rpc-in id=73 name=ScrDisplayGameText local=implemented "
            f"count=3 bits=248 bytes=31 first={REPLACEMENT_PAYLOAD}",
            "rpc-state id=73 game_text_seq=3 action=show style=3 time=5000 "
            f"text='{REPLACEMENT_TEXT}' evidence=PROBE_TRACE",
        )
    ) + "\n"


def valid_runtime() -> str:
    return "\n".join(
        (
            "[sampdll-runtime] game_text: show seq=2 style=5 time=5000 "
            f"text='{FIRST_TEXT}' evidence=STATIC_037",
            "[sampdll-runtime] unrelated render marker",
            "[sampdll-runtime] game_text: clear_all seq=3 cleared=1 "
            "reason=replace_before_show evidence=STATIC_037",
            "[sampdll-runtime] game_text: show seq=3 style=3 time=5000 "
            f"text='{REPLACEMENT_TEXT}' evidence=STATIC_037",
        )
    ) + "\n"


def make_artifact(
    root: Path,
    *,
    server: str | None = None,
    net: str | None = None,
    runtime: str | None = None,
    extra_client_log: str = "",
) -> Path:
    artifact = root / "artifact"
    client = artifact / "client"
    client.mkdir(parents=True)
    (artifact / "server.console.log").write_text(
        valid_server() if server is None else server, encoding="utf-8"
    )
    (client / "samp_net_trace.log").write_text(
        valid_net() if net is None else net, encoding="utf-8"
    )
    (client / "samp_runtime.log").write_text(
        valid_runtime() if runtime is None else runtime, encoding="utf-8"
    )
    (client / "samp_hook_trace.log").write_text(
        extra_client_log, encoding="utf-8"
    )
    return artifact


class GameTextR5AnalyzerTests(unittest.TestCase):
    def test_complete_fixed_sequence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(make_artifact(Path(directory)))

        self.assertEqual("PASS", result["verdict"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(
            [1],
            result["observations"]["runtime"]["show_seq2_style5_lines"],
        )
        self.assertEqual(
            [3],
            result["observations"]["runtime"]["clear_seq3_cleared1_lines"],
        )
        self.assertEqual(
            [4],
            result["observations"]["runtime"]["show_seq3_style3_lines"],
        )

    @unittest.skipUnless(
        GOLDEN_ARTIFACT.is_dir(),
        "repository-local successful GameText artifact is unavailable",
    )
    def test_successful_repository_artifact_is_pass(self) -> None:
        result = analyze(GOLDEN_ARTIFACT)

        self.assertEqual("PASS", result["verdict"])
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(
            [825],
            result["observations"]["runtime"]["show_seq2_style5_lines"],
        )
        self.assertEqual(
            [830],
            result["observations"]["runtime"]["clear_seq3_cleared1_lines"],
        )
        self.assertEqual(
            [831],
            result["observations"]["runtime"]["show_seq3_style3_lines"],
        )

    def test_fixture_transport_failure_is_mismatch(self) -> None:
        server = valid_server().replace("channel=2 sent=1", "channel=2 sent=0", 1)
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(make_artifact(Path(directory), server=server))

        self.assertEqual("MISMATCH", result["verdict"])
        self.assertFalse(result["checks"]["fixture_first_sent"])
        self.assertTrue(result["checks"]["fixture_replacement_sent"])

    def test_wrong_net_style_or_text_is_mismatch(self) -> None:
        net = valid_net().replace(
            "style=3 time=5000 text='RPC73_STYLE3_SECOND'",
            "style=4 time=5000 text='WRONG'",
        )
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(make_artifact(Path(directory), net=net))

        self.assertEqual("MISMATCH", result["verdict"])
        self.assertFalse(result["checks"]["net_rpc73_replacement_style_text"])
        self.assertFalse(result["checks"]["net_rpc73_sequence"])

    def test_wrong_clear_count_is_mismatch(self) -> None:
        runtime = valid_runtime().replace("cleared=1", "cleared=0")
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                make_artifact(Path(directory), runtime=runtime)
            )

        self.assertEqual("MISMATCH", result["verdict"])
        self.assertFalse(result["checks"]["runtime_clear_seq3_cleared1"])
        self.assertFalse(result["checks"]["runtime_replacement_sequence"])

    def test_reversed_runtime_order_is_mismatch(self) -> None:
        runtime_lines = valid_runtime().splitlines()
        runtime = "\n".join(
            (runtime_lines[0], runtime_lines[1], runtime_lines[3], runtime_lines[2])
        ) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                make_artifact(Path(directory), runtime=runtime)
            )

        self.assertEqual("MISMATCH", result["verdict"])
        self.assertTrue(result["checks"]["runtime_clear_seq3_cleared1"])
        self.assertTrue(result["checks"]["runtime_show_seq3_style3"])
        self.assertFalse(result["checks"]["runtime_replacement_sequence"])

    def test_exception_filter_in_any_artifact_log_is_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                make_artifact(
                    Path(directory),
                    extra_client_log="exception_filter: code=0xc0000005\n",
                )
            )

        self.assertEqual("MISMATCH", result["verdict"])
        self.assertFalse(result["checks"]["no_exception_filter"])
        self.assertEqual(
            [{"file": "client/samp_hook_trace.log", "line": 1}],
            result["observations"]["exception_filter"],
        )

    def test_missing_required_trace_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = make_artifact(Path(directory))
            (artifact / "client/samp_runtime.log").unlink()
            with self.assertRaises(FileNotFoundError):
                analyze(artifact)

    def test_cli_writes_pass_json_and_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = make_artifact(root)
            output = root / "gametext-analysis.json"
            with mock.patch("builtins.print"):
                result = main([str(artifact), "--output", str(output)])

            self.assertEqual(0, result)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("PASS", written["verdict"])


if __name__ == "__main__":
    unittest.main()
