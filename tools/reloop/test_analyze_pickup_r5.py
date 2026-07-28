#!/usr/bin/env python3
"""Unit tests for the artifact-only Original-R5 pickup analyzer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from analyze_pickup_r5 import (  # noqa: E402
    GTA_10_US_SHA256,
    ORIGINAL_R5_SHA256,
    PICKUP_FLAG,
    analyze_log,
)


HOOK_SUMMARY = (
    "pickup_hook: summary installed=2 requested=2 "
    "rvas=0x13440,0x13520 evidence=STATIC_037,TODO_VERIFY\n"
)


def event_line(
    ring_seq: int,
    event_seq: int,
    kind: str,
    *,
    hook: str,
    caller: str = "0xffffffff",
    raw: int = 0xFFFFFFFF,
    ordinal: int = 0,
    gate: tuple[int, int] = (0, 0),
    delta_ms: int = 0,
    delta_frames: int = 0,
    rpc: int = 0,
    bits: int = 0,
    payload_valid: int = 0,
    payload: int = 0,
    priority: int = 0,
    reliability: int = 0,
    channel: int = 0,
    result: int = 0,
) -> str:
    return (
        f"pickup_r5: seq={ring_seq} event={event_seq} tick=987654 "
        f"thread=77 frame=1234 kind={kind} caller_rva={caller} "
        f"hook_rva={hook} pool=0xdeadbeef raw_argument={raw} "
        f"process_ordinal={ordinal} process_gate={gate[0]},{gate[1]} "
        f"cadence_delta={delta_ms}_ms/{delta_frames}_frames rpc={rpc} "
        f"bits={bits} payload_valid={payload_valid} payload={payload} "
        f"priority={priority} reliability={reliability} channel={channel} "
        f"result={result} evidence=STATIC_037,TODO_VERIFY\n"
    )


def pool_line(
    ring_seq: int,
    event_seq: int,
    phase: str,
    slots: list[dict[str, int]],
) -> str:
    lines = [
        f"pickup_pool_r5: seq={ring_seq} event={event_seq} phase={phase} "
        f"valid=0x00000001 pool=0xdeadbeef count={len(slots)} "
        f"active={len(slots)} captured={len(slots)}\n"
    ]
    for sample, slot in enumerate(slots):
        lines.append(
            f"pickup_slot_r5: seq={ring_seq} event={event_seq} phase={phase} "
            f"sample={sample} valid=0x0000001f slot={slot['slot']} "
            f"handle=0x{slot['handle']:08x} "
            f"raw_gta_index={slot['raw']} timer={slot['timer']} "
            f"dropped={slot.get('dropped', 0)} "
            f"from_player={slot.get('from_player', 65535)} "
            f"model={slot.get('model', 1240)} type={slot.get('type', 1)} "
            "pos_bits=3f800000,40000000,40400000\n"
        )
    return "".join(lines)


def process_event(
    ring_seq: int,
    event_seq: int,
    ordinal: int,
    *,
    delta_frames: int,
    slots_pre: list[dict[str, int]] | None = None,
    slots_post: list[dict[str, int]] | None = None,
) -> str:
    before = slots_pre or []
    after = slots_post if slots_post is not None else before
    return "".join(
        (
            event_line(
                ring_seq,
                event_seq,
                "process",
                hook="0x00013520",
                caller="0x00008ca8",
                ordinal=ordinal,
                gate=(6, 6),
                delta_ms=116 if delta_frames else 0,
                delta_frames=delta_frames,
            ),
            pool_line(ring_seq, event_seq, "pre", before),
            pool_line(ring_seq, event_seq, "post", after),
        )
    )


def rpc_event(
    ring_seq: int,
    event_seq: int,
    rpc_id: int,
    payload: int,
    reliability: int,
    slots: list[dict[str, int]],
    *,
    result: int = 1,
) -> str:
    return "".join(
        (
            event_line(
                ring_seq,
                event_seq,
                f"rpc_{rpc_id}",
                hook="0x00000000",
                rpc=rpc_id,
                bits=32 if rpc_id == 131 else 16,
                payload_valid=1,
                payload=payload,
                priority=1,
                reliability=reliability,
                channel=0,
                result=result,
            ),
            pool_line(ring_seq, event_seq, "rpc", slots),
        )
    )


def ordinary_trace(
    *,
    reliability: int = 9,
    post_timer: int = 15,
    handle: int = 0x0002002A,
    raw: int = 42,
) -> str:
    before = {
        "slot": 5,
        "handle": handle,
        "raw": raw,
        "timer": 0,
        "type": 1,
    }
    after = {**before, "timer": post_timer}
    return "".join(
        (
            HOOK_SUMMARY,
            process_event(1, 1, 1, delta_frames=0),
            process_event(2, 2, 2, delta_frames=7),
            rpc_event(3, 4, 131, 5, reliability, [before]),
            event_line(
                4,
                3,
                "picked_up",
                hook="0x00013440",
                raw=raw,
                ordinal=2,
                gate=(0, 0),
            ),
            pool_line(4, 3, "pre", [before]),
            pool_line(4, 3, "post", [after]),
        )
    )


def add_type14_and_dropped(trace: str) -> str:
    type14 = {
        "slot": 6,
        "handle": 0x00010033,
        "raw": 51,
        "timer": 0,
        "type": 14,
    }
    dropped = {
        "slot": 7,
        "handle": 0x00010034,
        "raw": 52,
        "timer": 0,
        "type": 4,
        "dropped": 1,
        "from_player": 9,
    }
    return "".join(
        (
            trace,
            rpc_event(5, 6, 131, 6, 10, [type14, dropped]),
            rpc_event(6, 7, 97, 9, 10, [type14, dropped]),
            process_event(
                7,
                5,
                3,
                delta_frames=7,
                slots_pre=[type14, dropped],
                slots_post=[type14, dropped],
            ),
        )
    )


class PickupAnalyzerTests(unittest.TestCase):
    def make_artifact(
        self,
        root: Path,
        trace: str,
        *,
        samp_hash: str = ORIGINAL_R5_SHA256,
        duplicate_log: bool = False,
    ) -> Path:
        artifact = root / "distributed-sync-pickup"
        run = artifact / "windows" / "run-1"
        latest = run / "latest_log_bytes" / "samp_probe.log"
        latest.parent.mkdir(parents=True)
        latest.write_text(trace, encoding="utf-8")
        if duplicate_log:
            copied = run / "logs" / "samp_probe.log"
            copied.parent.mkdir(parents=True)
            copied.write_text(trace, encoding="utf-8")
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "samp_sha256": samp_hash,
                    "gta_sha256": GTA_10_US_SHA256,
                    "probe_flags": [PICKUP_FLAG],
                }
            ),
            encoding="utf-8",
        )
        driver = artifact / "driver" / "pickup.json"
        driver.parent.mkdir(parents=True)
        driver.write_text(
            json.dumps(
                {
                    "scenario": "pickup",
                    "returncode": 0,
                    "events": [
                        {
                            "event": "sync_pair_scenario_queued",
                            "scenario": "pickup",
                            "request_id": 123,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (artifact / "server.log").write_text(
            "\n".join(
                (
                    "[sync_pair] marker=REQUEST_ACCEPTED request=123 "
                    "status=ACTION scenario=pickup detail=host_request",
                    "[sync_pair] marker=PICKUP_CREATED pickup=5 player=0",
                    "[sync_pair] marker=SCENARIO_START request=123 "
                    "scenario=pickup pilot=0 observer=1",
                    "[sync_pair] marker=REQUEST_DONE request=123 "
                    "status=PASS scenario=pickup detail=scenario_started",
                    "[sync_pair] marker=PICKUP_COLLECTED player=0 pickup=5 "
                    "scenario=11",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return artifact

    def test_complete_ordinary_artifact_has_bounded_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory), ordinary_trace(), duplicate_log=True
            )
            result = analyze_log(artifact)

        self.assertEqual("OBSERVED_ORDINARY", result["assessment"])
        self.assertEqual("OBSERVED", result["identity"]["status"])
        self.assertEqual("OBSERVED", result["fixture"]["status"])
        ordinary = result["ordinary_picked_up"]
        self.assertEqual("OBSERVED", ordinary["status"])
        self.assertEqual(9, ordinary["observations"][0]["rpc"]["reliability"])
        self.assertEqual({"pre": 0, "post": 15}, ordinary["observations"][0]["timer"])
        self.assertEqual("TODO_VERIFY", result["type14_process"]["status"])
        self.assertEqual("TODO_VERIFY", result["dropped_process"]["status"])
        rendered = json.dumps(result)
        self.assertNotIn("PASS", rendered)
        self.assertNotIn("0xdeadbeef", rendered)
        self.assertNotIn("987654", rendered)

    def test_handle_low_word_relationship_is_observed_not_assumed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory),
                ordinary_trace(handle=0x00020007, raw=42),
            )
            result = analyze_log(artifact)

        observation = result["ordinary_picked_up"]["observations"][0]
        self.assertFalse(observation["raw_equals_handle_index"])
        self.assertEqual("OBSERVED_ORDINARY", result["assessment"])

    def test_wrong_ordinary_rpc_reliability_is_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory), ordinary_trace(reliability=10)
            )
            result = analyze_log(artifact)

        self.assertEqual("MISMATCH", result["assessment"])
        errors = result["ordinary_picked_up"]["observations"][0]["errors"]
        self.assertTrue(any("reliability" in error for error in errors))
        self.assertEqual("MISMATCH", result["ordinary_picked_up"]["status"])

    def test_wrong_timer_transition_is_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory), ordinary_trace(post_timer=0)
            )
            result = analyze_log(artifact)

        self.assertEqual("MISMATCH", result["assessment"])
        self.assertTrue(
            any(
                "post timer=0" in error
                for error in result["ordinary_picked_up"]["observations"][0][
                    "errors"
                ]
            )
        )

    def test_type14_and_dropped_process_qos_are_separate_oracles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory), add_type14_and_dropped(ordinary_trace())
            )
            result = analyze_log(artifact)

        self.assertEqual("OBSERVED", result["type14_process"]["status"])
        self.assertEqual(10, result["type14_process"]["observations"][0]["qos"]["reliability"])
        self.assertEqual("OBSERVED", result["dropped_process"]["status"])
        self.assertEqual(97, result["dropped_process"]["static_oracle"]["rpc"])

    def test_positive_process_timer_sample_confirms_tick_countdown(self) -> None:
        before = {
            "slot": 5,
            "handle": 0x0002002A,
            "raw": 42,
            "timer": 15,
            "type": 1,
        }
        after = {**before, "timer": 14}
        trace = ordinary_trace() + process_event(
            5,
            5,
            3,
            delta_frames=7,
            slots_pre=[before],
            slots_post=[after],
        )
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(Path(directory), trace)
            result = analyze_log(artifact)

        timer = result["process"]["ordinary_timer_countdown"]
        self.assertEqual("OBSERVED", timer["status"])
        self.assertEqual(1, timer["positive_timer_sample_count"])

    def test_wrong_binary_identity_is_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(
                Path(directory), ordinary_trace(), samp_hash="0" * 64
            )
            result = analyze_log(artifact)

        self.assertEqual("MISMATCH", result["identity"]["status"])
        self.assertEqual("MISMATCH", result["assessment"])

    def test_overflow_is_integrity_mismatch(self) -> None:
        trace = (
            ordinary_trace()
            + "pickup_r5: overflow skipped=3 total_skipped=3 ring=256\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            artifact = self.make_artifact(Path(directory), trace)
            result = analyze_log(artifact)

        self.assertEqual("MISMATCH", result["integrity"]["status"])
        self.assertEqual(3, result["integrity"]["overflow"]["skipped"])
        self.assertEqual("MISMATCH", result["assessment"])

    def test_direct_hook_only_log_keeps_claims_todo_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "samp_probe.log"
            log.write_text(HOOK_SUMMARY, encoding="utf-8")
            result = analyze_log(log)

        self.assertEqual("TODO_VERIFY", result["assessment"])
        self.assertEqual("TODO_VERIFY", result["identity"]["status"])
        self.assertEqual("TODO_VERIFY", result["ordinary_picked_up"]["status"])


if __name__ == "__main__":
    unittest.main()
