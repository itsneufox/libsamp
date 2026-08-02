#!/usr/bin/env python3
"""Contract tests for the pickup-only Original-R5 runner adapter."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import distributed_sync_runner as distributed  # noqa: E402
import pickup_r5_runner as pickup_runner  # noqa: E402


class PickupR5RunnerTests(unittest.TestCase):
    def test_server_state_is_scoped_to_requested_fixture(self) -> None:
        text = "\n".join(
            (
                "[sync_pair] marker=REQUEST_ACCEPTED request=1 "
                "status=ACTION scenario=pickup",
                "[sync_pair] marker=PICKUP_COLLECTED player=0 pickup=99",
                "[sync_pair] marker=REQUEST_ACCEPTED request=2 "
                "status=ACTION scenario=pickup",
                "[sync_pair] marker=PICKUP_CREATED pickup=5 player=0",
                "[sync_pair] marker=SCENARIO_START request=2 "
                "scenario=pickup pilot=0 observer=1",
                "[sync_pair] marker=REQUEST_DONE request=2 "
                "status=PASS scenario=pickup detail=scenario_started",
                "[sync_pair] marker=PICKUP_COLLECTED player=0 pickup=5",
            )
        )

        state = pickup_runner.pickup_request_state(text, 2)

        self.assertTrue(state["complete"])
        self.assertIn("pickup=5", state["collection_line"])

    def test_in_memory_patch_restores_shared_runner(self) -> None:
        prior_profile = distributed.PROBE_PROFILE_FLAGS.get(
            pickup_runner.PROFILE
        )
        prior_validate = distributed.validate_role_scenario
        prior_death_driver = distributed.run_windows_death_driver
        had_pickup_driver = hasattr(distributed, "run_windows_pickup_driver")
        prior_pickup_driver = getattr(
            distributed, "run_windows_pickup_driver", None
        )

        with pickup_runner.pickup_runner_patch():
            self.assertEqual(
                pickup_runner.PROFILE_FLAGS,
                distributed.PROBE_PROFILE_FLAGS[pickup_runner.PROFILE],
            )
            distributed.validate_role_scenario("pilot", "pickup")
            self.assertIs(
                pickup_runner.run_windows_pickup_driver,
                distributed.run_windows_death_driver,
            )

        self.assertIs(prior_validate, distributed.validate_role_scenario)
        self.assertIs(prior_death_driver, distributed.run_windows_death_driver)
        self.assertEqual(
            prior_profile,
            distributed.PROBE_PROFILE_FLAGS.get(pickup_runner.PROFILE),
        )
        self.assertEqual(
            had_pickup_driver,
            hasattr(distributed, "run_windows_pickup_driver"),
        )
        if had_pickup_driver:
            self.assertIs(
                prior_pickup_driver, distributed.run_windows_pickup_driver
            )

    def test_driver_waits_for_collection_and_writes_request_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            server_log = root / "server.log"
            request_path = root / "request.txt"
            results_path = root / "results.log"
            server_log.write_text("", encoding="utf-8")

            def queue(
                scenario: str,
                _request_path: Path,
                _results_path: Path,
                _timeout: float,
                output: list[dict],
            ) -> int:
                self.assertEqual("pickup", scenario)
                output.append(
                    {
                        "event": "sync_pair_scenario_queued",
                        "scenario": "pickup",
                        "request_id": 77,
                    }
                )
                server_log.write_text(
                    "\n".join(
                        (
                            "[sync_pair] marker=REQUEST_ACCEPTED request=77 "
                            "status=ACTION scenario=pickup",
                            "[sync_pair] marker=PICKUP_CREATED pickup=5 player=0",
                            "[sync_pair] marker=SCENARIO_START request=77 "
                            "scenario=pickup pilot=0 observer=1",
                            "[sync_pair] marker=REQUEST_DONE request=77 "
                            "status=PASS scenario=pickup detail=scenario_started",
                            "[sync_pair] marker=PICKUP_COLLECTED "
                            "player=0 pickup=5",
                        )
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return 77

            with (
                mock.patch.object(
                    pickup_runner.sync_pair_client,
                    "capture_observer",
                    return_value=None,
                ),
                mock.patch.object(
                    pickup_runner.sync_pair_client,
                    "queue_sync_pair_scenario",
                    side_effect=queue,
                ),
                mock.patch.object(pickup_runner.time, "sleep", return_value=None),
            ):
                returncode = pickup_runner.run_windows_pickup_driver(
                    artifact,
                    request_path=request_path,
                    results_path=results_path,
                    server_log=server_log,
                    fixture_timeout=1.0,
                    screenshot_count=2,
                    screenshot_interval=0.025,
                )

            receipt = json.loads(
                (artifact / "driver" / "pickup.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(0, returncode)
        self.assertEqual("ordinary type-1 pickup", receipt["fixture_scope"])
        self.assertEqual(77, receipt["events"][-1]["request_id"])
        self.assertTrue(
            any(
                event["event"] == "windows_pilot_pickup_observed"
                for event in receipt["events"]
            )
        )


if __name__ == "__main__":
    unittest.main()
