import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("sync_pair_client.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("sync_pair_client", MODULE_PATH)
assert SPEC and SPEC.loader
sync_pair_client = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_pair_client
SPEC.loader.exec_module(sync_pair_client)


class RelativeAimClient:
    def __init__(self, degrees_per_mouse_count: float = 0.5):
        self.heading = 0.0
        self.degrees_per_mouse_count = degrees_per_mouse_count
        self.mouse_commands: list[dict[str, object]] = []

    def command(self, command: str, **fields):
        if command == "mouse":
            self.mouse_commands.append(fields)
            self.heading += (
                float(fields["x"]) * self.degrees_per_mouse_count
            )
            return {"ok": True, "event": "mouse"}
        if command == "state":
            radians = math.radians(self.heading)
            return {
                "ok": True,
                "event": "state",
                "aim_front_x": math.cos(radians),
                "aim_front_y": math.sin(radians),
                "aim_front_z": 0.0,
                "player_forward_x": math.cos(radians),
                "player_forward_y": math.sin(radians),
                "player_forward_z": 0.0,
            }
        raise AssertionError(f"unexpected command {command!r}")


class AngleSweepTests(unittest.TestCase):
    def test_angle_delta_wraps_at_360_degrees(self):
        self.assertAlmostEqual(
            sync_pair_client.signed_angle_delta_degrees(5.0, 355.0),
            10.0,
        )
        self.assertAlmostEqual(
            sync_pair_client.signed_angle_delta_degrees(355.0, 5.0),
            -10.0,
        )

    def test_missing_internal_aim_fields_rejects_trace(self):
        with self.assertRaisesRegex(RuntimeError, "current control ASI"):
            sync_pair_client.aim_heading_degrees({"aim_x": 1.0, "aim_y": 0.0})

    def test_relative_input_is_calibrated_and_reaches_symmetric_targets(self):
        client = RelativeAimClient()
        output: list[dict[str, object]] = []
        with mock.patch.object(sync_pair_client.time, "sleep"):
            left_sign, calibration_pulses = (
                sync_pair_client.calibrate_left_aim_sign(
                    client,
                    0.0,
                    output,
                )
            )
            left = sync_pair_client.drive_aim_to_relative_target(
                client,
                output,
                "angles_after_left",
                0.0,
                left_sign,
                -sync_pair_client.ANGLE_SWEEP_MOUSE_PULSE_X,
                calibration_pulses,
            )
            right = sync_pair_client.drive_aim_to_relative_target(
                client,
                output,
                "angles_after_right",
                0.0,
                -left_sign,
                sync_pair_client.ANGLE_SWEEP_MOUSE_PULSE_X,
            )

        self.assertEqual(left_sign, -1)
        self.assertLessEqual(
            left["aim_delta_from_baseline_degrees"],
            -(
                sync_pair_client.ANGLE_SWEEP_TARGET_DEGREES
                - sync_pair_client.ANGLE_SWEEP_TOLERANCE_DEGREES
            ),
        )
        self.assertGreaterEqual(
            right["aim_delta_from_baseline_degrees"],
            (
                sync_pair_client.ANGLE_SWEEP_TARGET_DEGREES
                - sync_pair_client.ANGLE_SWEEP_TOLERANCE_DEGREES
            ),
        )
        self.assertTrue(client.mouse_commands)
        self.assertTrue(
            all(
                command["action"] == "move_delta"
                for command in client.mouse_commands
            )
        )
        self.assertEqual(
            output[0]["event"],
            "angles_relative_input_calibrated",
        )

    def test_unchanged_internal_aim_rejects_false_angle_trace(self):
        client = RelativeAimClient(degrees_per_mouse_count=0.0)
        with (
            mock.patch.object(sync_pair_client.time, "sleep"),
            self.assertRaisesRegex(RuntimeError, "would not be valid"),
        ):
            sync_pair_client.calibrate_left_aim_sign(client, 0.0, [])
        self.assertEqual(len(client.mouse_commands), 12)


class PassengerGQueueTests(unittest.TestCase):
    def test_waits_for_streamed_onfoot_edge_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "sync_pair_request.txt"
            results_path = root / "sync_pair_results.log"
            output: list[dict[str, object]] = []

            def emit_edge_setup(_seconds: float) -> None:
                results_path.write_text(
                    "[sync_pair] marker=EDGE_SETUP request=123 status=PASS "
                    "scenario=passenger_g detail=vehicle=4 state=1 seat=-1 "
                    "distance=2.452 action=vk_g attempts=1\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(sync_pair_client.time, "time_ns", return_value=123),
                mock.patch.object(
                    sync_pair_client.time,
                    "monotonic",
                    side_effect=[0.0, 0.0, 0.0],
                ),
                mock.patch.object(
                    sync_pair_client.time,
                    "sleep",
                    side_effect=emit_edge_setup,
                ),
            ):
                request_id = sync_pair_client.queue_sync_pair_scenario(
                    "passenger_g",
                    request_path,
                    results_path,
                    1.0,
                    output,
                )

            self.assertEqual(request_id, 123)
            self.assertEqual(
                request_path.read_text(encoding="utf-8"),
                "123 passenger_g\n",
            )
            self.assertEqual(
                output[-1]["event"],
                "sync_pair_edge_setup_acknowledged",
            )


class PassengerGDriverTests(unittest.TestCase):
    def test_presses_g_then_waits_for_verified_passenger_result(self):
        client = mock.Mock()
        output: list[dict[str, object]] = []
        request_path = Path("/tmp/sync_pair_request.txt")
        results_path = Path("/tmp/sync_pair_results.log")

        with (
            mock.patch.object(
                sync_pair_client,
                "queue_sync_pair_scenario",
                return_value=456,
            ),
            mock.patch.object(
                sync_pair_client,
                "wait_for_sync_pair_result",
                return_value="status=PASS",
            ) as wait_for_result,
            mock.patch.object(sync_pair_client, "sample", return_value={}),
            mock.patch.object(sync_pair_client, "capture_observer"),
            mock.patch.object(sync_pair_client.time, "sleep"),
        ):
            sync_pair_client.drive_scenario(
                client,
                "passenger_g",
                output,
                0.0,
                0.1,
                None,
                1,
                0.0,
                None,
                None,
                Path("/tmp/test_cmds_request.txt"),
                Path("/tmp/test_cmds_results.log"),
                1,
                250,
                1.0,
                request_path,
                results_path,
                1.0,
            )

        self.assertEqual(
            client.key.call_args_list,
            [
                mock.call(sync_pair_client.VK_G, "down"),
                mock.call(sync_pair_client.VK_G, "up"),
            ],
        )
        wait_for_result.assert_called_once_with(
            "PASSENGER_ENTRY_RESULT",
            "passenger_g",
            456,
            results_path,
            1.0,
            output,
        )


if __name__ == "__main__":
    unittest.main()
