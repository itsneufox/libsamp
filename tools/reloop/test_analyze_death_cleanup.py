#!/usr/bin/env python3
"""Unit tests for the artifact-only R5 death/cleanup analyzer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from analyze_death_cleanup import analyze_log


HOOK_SUMMARY = "death_cleanup_hook: summary installed=6 requested=6\n"


def event_line(ring_seq: int, event_seq: int, kind: str, cleanup: int = 1) -> str:
    return (
        f"death_cleanup_r5: seq={ring_seq} event={event_seq} tick=987654 "
        f"thread=7 frame=99 kind={kind} caller_rva=0x00000011 "
        "hook_rva=0x00000022 object=0xdeadbeef argument=0xcafebabe "
        f"result=0x00000000 cleanup={cleanup} evidence=PROBE_TRACE\n"
    )


def ui_line(
    ring_seq: int,
    event_seq: int,
    phase: str,
    *,
    dialog: int = 0,
    scoreboard: int = 0,
) -> str:
    return (
        f"death_cleanup_ui_r5: seq={ring_seq} event={event_seq} phase={phase} "
        f"scoreboard=0xdead0001 visible={scoreboard} "
        f"dialog=0xdead0002 active={dialog} "
        "selector=0xdead0003 active=0 chat=0xdead0004 active=0 "
        "class_gui=0xdead0005 visible=0 game=0xdead0006 "
        "input_depth=1,2 camera=3,4 frontend=5,6,7\n"
    )


def pools_line(
    ring_seq: int,
    event_seq: int,
    phase: str,
    *,
    vehicle: int = 2,
    remote: int = 1,
    objects: int = 3,
    remove_building: int = 4,
) -> str:
    return (
        f"death_cleanup_pools_r5: seq={ring_seq} event={event_seq} phase={phase} "
        "valid=0x000000ff netgame=0xdead1000 pools=0xdead1001 "
        "pool_ptrs=0xdead1002,0xdead1003 "
        f"vehicle={vehicle}/{vehicle} remote={remote}/{remote} "
        "pickup_raw=2/2/2 "
        f"object={objects}/{objects} actor=1/1 gangzone=1 "
        "textdraw=2 label=3 menu=1 current=1 "
        f"remove_building_count={remove_building}\n"
    )


def complete_event(
    ring_seq: int,
    event_seq: int,
    kind: str,
    *,
    post_vehicle: int = 0,
    post_remote: int = 0,
    post_objects: int = 0,
    remove_pre: int = 4,
    remove_post: int = 4,
) -> str:
    return "".join(
        (
            event_line(ring_seq, event_seq, kind),
            ui_line(ring_seq, event_seq, "pre", dialog=1, scoreboard=1),
            ui_line(ring_seq, event_seq, "post"),
            pools_line(
                ring_seq,
                event_seq,
                "pre",
                remove_building=remove_pre,
            ),
            pools_line(
                ring_seq,
                event_seq,
                "post",
                vehicle=post_vehicle,
                remote=post_remote,
                objects=post_objects,
                remove_building=remove_post,
            ),
        )
    )


class DeathCleanupAnalyzerTests(unittest.TestCase):
    def analyze(self, root: Path, text: str, nested: bool = False) -> dict:
        if nested:
            log = root / "windows" / "run-1" / "logs" / "samp_probe.log"
        else:
            log = root / "samp_probe.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
        return analyze_log(root if nested else log)

    def test_missing_events_remain_todo_verify_and_never_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), HOOK_SUMMARY)

        self.assertEqual("TODO_VERIFY", result["assessment"])
        self.assertEqual(
            {"TODO_VERIFY"},
            {scenario["status"] for scenario in result["scenarios"].values()},
        )
        self.assertEqual(
            "TODO_VERIFY", result["connection_lost_to_gmx_ordering"]["status"]
        )
        self.assertNotIn("PASS", json.dumps(result))

    def test_gmx_reports_pool_ui_and_persistent_remove_building(self) -> None:
        trace = HOOK_SUMMARY + complete_event(
            10,
            20,
            "gmx_reset",
            post_vehicle=0,
            post_remote=0,
            post_objects=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace)

        scenario = result["scenarios"]["gmx_reset"]
        self.assertEqual("OBSERVED", scenario["status"])
        observation = scenario["observations"][0]
        self.assertEqual(-2, observation["pools"]["delta"]["vehicle_listed"])
        self.assertEqual(-2, observation["pools"]["delta"]["object_listed"])
        self.assertEqual(
            {"pre": 1, "post": 0},
            observation["ui"]["changes"]["dialog_active"],
        )
        self.assertEqual("PERSISTED", observation["remove_building"]["assessment"])
        rendered = json.dumps(result)
        self.assertNotIn("0xdeadbeef", rendered)
        self.assertNotIn("0xcafebabe", rendered)
        self.assertNotIn("0xdead1002", rendered)
        self.assertNotIn("987654", rendered)

    def test_connection_lost_pairs_with_nested_gmx_publication_order(self) -> None:
        trace = (
            HOOK_SUMMARY
            + complete_event(4, 21, "gmx_reset")
            + complete_event(5, 20, "connection_lost")
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace, nested=True)

        ordering = result["connection_lost_to_gmx_ordering"]
        self.assertEqual("OBSERVED", ordering["status"])
        self.assertEqual(1, ordering["pairs"][0]["event_seq_delta"])
        self.assertEqual(1, ordering["pairs"][0]["publish_seq_delta"])

    def test_non_nested_connection_gmx_order_is_mismatch(self) -> None:
        trace = (
            HOOK_SUMMARY
            + complete_event(4, 20, "connection_lost")
            + complete_event(5, 21, "gmx_reset")
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace)

        self.assertEqual(
            "MISMATCH", result["connection_lost_to_gmx_ordering"]["status"]
        )
        self.assertEqual("MISMATCH", result["assessment"])

    def test_destructor_pre_post_and_remove_building_change(self) -> None:
        trace = HOOK_SUMMARY + complete_event(
            30,
            40,
            "quit_destructor",
            remove_pre=5,
            remove_post=0,
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace)

        observation = result["scenarios"]["quit_destructor"]["observations"][0]
        self.assertEqual("OBSERVED", observation["status"])
        self.assertEqual(-5, observation["remove_building"]["delta"])
        self.assertEqual("CHANGED", observation["remove_building"]["assessment"])

    def test_present_event_with_missing_snapshots_is_todo_verify(self) -> None:
        trace = HOOK_SUMMARY + event_line(50, 60, "gmx_reset")
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace)

        observation = result["scenarios"]["gmx_reset"]["observations"][0]
        self.assertEqual("TODO_VERIFY", observation["status"])
        self.assertEqual(
            ["ui.pre", "ui.post", "pools.pre", "pools.post"],
            observation["missing"],
        )
        self.assertNotIn("PASS", json.dumps(result))

    def test_overflow_is_integrity_mismatch(self) -> None:
        trace = (
            HOOK_SUMMARY
            + "death_cleanup_r5: overflow skipped=2 total_skipped=2 ring=256\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self.analyze(Path(directory), trace)

        self.assertEqual("MISMATCH", result["integrity"]["status"])
        self.assertEqual("MISMATCH", result["assessment"])


if __name__ == "__main__":
    unittest.main()
