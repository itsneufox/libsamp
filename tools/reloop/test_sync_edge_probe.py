import contextlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("sync_edge_probe.py")
SPEC = importlib.util.spec_from_file_location("sync_edge_probe", MODULE_PATH)
assert SPEC and SPEC.loader
sync_edge_probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_edge_probe
SPEC.loader.exec_module(sync_edge_probe)


class AutoPauseTests(unittest.TestCase):
    def test_requires_game_section_and_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "windowed.ini"
            path.write_text(
                "[other]\nautoPause=1\n[game]\nautoPause = 0 ; keep running\n",
                encoding="utf-8",
            )
            self.assertTrue(sync_edge_probe.autopause_disabled(path))

    def test_missing_or_enabled_is_false(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "windowed.ini"
            self.assertFalse(sync_edge_probe.autopause_disabled(path))
            path.write_text("[game]\nautoPause=1\n", encoding="utf-8")
            self.assertFalse(sync_edge_probe.autopause_disabled(path))


class EvidenceTests(unittest.TestCase):
    def test_replacement_observer_requires_decode_and_apply(self):
        server = "\n".join(
            [
                "marker=SCENARIO_START request=1 scenario=passenger",
                "marker=PILOT_SYNC scenario=passenger sample=1 state=3 vehicle=4",
                "marker=UNOCCUPIED_UPDATE count=1",
                "marker=TRAILER_UPDATE count=1",
            ]
        )
        observer = "\n".join(
            [
                "packet-state id=211 remote_passenger seq=1",
                "remote_passenger: apply seq=1 mode=already_seated seated=1 seat_read=1",
                "remote_edge: consume movement_seq=1 packet=211 packet_seq=1 type=3 result=applied",
                "packet-state id=209 remote_unoccupied seq=1",
                "remote_unoccupied: apply seq=1 mode=noop readback=1",
                "remote_edge: consume movement_seq=2 packet=209 packet_seq=1 type=2 result=applied",
                "packet-state id=210 remote_trailer seq=1",
                "remote_trailer: apply seq=1 attached=1 readback=1",
                "remote_edge: consume movement_seq=3 packet=210 packet_seq=1 type=4 result=applied",
            ]
        )
        verdict = sync_edge_probe.evaluate_evidence(
            list(sync_edge_probe.EDGE_SCENARIOS),
            server,
            observer,
            True,
            {name: 0 for name in sync_edge_probe.EDGE_SCENARIOS},
        )
        self.assertEqual(verdict["verdict"], "TRACE_PASS_VISUAL_UNVERIFIED")
        self.assertEqual(verdict["visual_parity"], "TODO_VERIFY")

    def test_missing_runtime_apply_fails(self):
        verdict = sync_edge_probe.evaluate_evidence(
            ["trailer"],
            "marker=TRAILER_UPDATE count=1",
            "\n".join(
                [
                    "packet-state id=210 remote_trailer seq=1",
                    "remote_edge: consume movement_seq=1 packet=210 packet_seq=1 type=4 result=applied",
                ]
            ),
            True,
            {"trailer": 0},
        )
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(
            verdict["scenarios"]["trailer"]["checks"]["observer_runtime_apply_seen"]
        )

    def test_passenger_g_requires_rpc26_and_verified_passenger_state(self):
        server = "\n".join(
            [
                "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                "scenario=passenger_g detail=rpc=26 vehicle=4 "
                "expected_vehicle=4 is_passenger=1 state_before=1 "
                "current_vehicle=0 seat_before=-1",
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=4 is_passenger=1 vehicle=4 seat=1 state=3 "
                "verify_attempt=4",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=4",
            ]
        )
        observer = "\n".join(
            [
                "packet-state id=211 remote_passenger seq=1",
                "remote_passenger: apply seq=1 mode=already_seated seated=1 seat_read=1",
                "remote_edge: consume movement_seq=1 packet=211 "
                "packet_seq=1 type=3 result=applied",
            ]
        )

        verdict = sync_edge_probe.evaluate_evidence(
            ["passenger_g"],
            server,
            observer,
            True,
            {"passenger_g": 0},
        )

        self.assertEqual(verdict["verdict"], "TRACE_PASS_VISUAL_UNVERIFIED")
        checks = verdict["scenarios"]["passenger_g"]["checks"]
        self.assertTrue(checks["server_rpc26_passenger_request_seen"])
        self.assertTrue(checks["server_passenger_entry_verified"])
        self.assertTrue(checks["server_passenger_vehicle_verified"])
        self.assertTrue(checks["server_passenger_state_seen"])

    def test_passenger_g_without_rpc26_callback_fails(self):
        server = "\n".join(
            [
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=4 is_passenger=1 vehicle=4 seat=1 state=3",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=4",
            ]
        )
        verdict = sync_edge_probe.evaluate_evidence(
            ["passenger_g"],
            server,
            "",
            False,
            {"passenger_g": 0},
        )

        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(
            verdict["scenarios"]["passenger_g"]["checks"][
                "server_rpc26_passenger_request_seen"
            ]
        )

    def test_passenger_g_rejects_mismatched_vehicle_ids(self):
        server = "\n".join(
            [
                "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                "scenario=passenger_g detail=rpc=26 vehicle=4 "
                "expected_vehicle=4 is_passenger=1",
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=5 is_passenger=1 vehicle=5 seat=1 state=3",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=5",
            ]
        )
        verdict = sync_edge_probe.evaluate_evidence(
            ["passenger_g"],
            server,
            "",
            False,
            {"passenger_g": 0},
        )

        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(
            verdict["scenarios"]["passenger_g"]["checks"][
                "server_passenger_vehicle_verified"
            ]
        )

    def test_original_observer_does_not_claim_internal_evidence(self):
        verdict = sync_edge_probe.evaluate_evidence(
            ["unoccupied"],
            "marker=UNOCCUPIED_UPDATE count=1",
            "",
            False,
            {"unoccupied": 0},
        )
        self.assertEqual(
            verdict["verdict"],
            "SERVER_TRACE_PASS_OBSERVER_INTERNALS_UNAVAILABLE",
        )
        self.assertNotIn(
            "observer_packet_decoded",
            verdict["scenarios"]["unoccupied"]["checks"],
        )


class AnalyzeTests(unittest.TestCase):
    def test_analyze_writes_separate_reanalysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "scenarios": ["trailer"],
                        "observer": "replacement",
                    }
                ),
                encoding="utf-8",
            )
            (root / "server.log").write_text(
                "marker=TRAILER_UPDATE count=1\n", encoding="utf-8"
            )
            client = root / "observer/client"
            client.mkdir(parents=True)
            (client / "samp_runtime.log").write_text(
                "\n".join(
                    [
                        "remote_trailer: apply seq=1 attached=1 readback=1",
                        "remote_edge: consume movement_seq=1 packet=210 packet_seq=1 type=4 result=applied",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (client / "samp_net_trace.log").write_text(
                "packet-state id=210 remote_trailer seq=1\n", encoding="utf-8"
            )
            (root / "verdict.json").write_text(
                '{"driver_returncodes":{"trailer":0}}\n', encoding="utf-8"
            )

            verdict = sync_edge_probe.analyze(root)

            self.assertEqual(verdict["verdict"], "TRACE_PASS_VISUAL_UNVERIFIED")
            self.assertTrue((root / "verdict.reanalyzed.json").is_file())


class ArtifactFinalizationTests(unittest.TestCase):
    @staticmethod
    def _profile(root: Path, name: str) -> object:
        prefix = root / name
        gta_root = prefix / sync_edge_probe.reloop.GTA_RELATIVE_ROOT
        gta_root.mkdir(parents=True)
        return sync_edge_probe.reloop.ClientProfile(name, prefix, None, None)

    def test_pre_teardown_checkpoint_is_explicitly_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact"
            artifact.mkdir()
            pilot = self._profile(root, "original")
            observer = self._profile(root, "replacement")
            server_source = root / "server-source.log"
            result_source = root / "results-source.log"
            observer_source = observer.gta_root / "samp_runtime.log"
            server_snapshot = sync_edge_probe.reloop.FileSnapshot.take(server_source)
            result_snapshot = sync_edge_probe.reloop.FileSnapshot.take(result_source)
            observer_snapshot = sync_edge_probe.reloop.FileSnapshot.take(observer_source)
            server_source.write_text(
                "marker=SCENARIO_START request=1 scenario=passenger\n"
                "marker=PILOT_SYNC scenario=passenger sample=1 state=3 vehicle=4\n",
                encoding="utf-8",
            )
            observer_source.write_text(
                "packet-state id=211 remote_passenger seq=1\n"
                "remote_passenger: apply seq=1 mode=already_seated seated=1 seat_read=1\n"
                "remote_edge: consume movement_seq=1 packet=211 packet_seq=1 "
                "type=3 result=applied\n",
                encoding="utf-8",
            )

            verdict = sync_edge_probe.finalize_artifact(
                artifact_dir=artifact,
                metadata={"observer": "replacement"},
                scenarios=["passenger"],
                server_console=artifact / "server.console.log",
                server_snapshot=server_snapshot,
                result_snapshot=result_snapshot,
                pilot_snapshots={},
                observer_snapshots={"samp_runtime.log": observer_snapshot},
                pilot=pilot,
                observer=observer,
                asi_before={"pilot": {}, "observer": {}},
                driver_returncodes={"passenger": 0},
                runner_error=None,
                teardown_errors=[],
                capture_complete=False,
            )

            self.assertEqual(verdict["verdict"], "INCOMPLETE_TEARDOWN")
            self.assertFalse(verdict["artifact_complete"])
            self.assertTrue((artifact / "server.log").is_file())
            self.assertTrue((artifact / "observer/client/samp_runtime.log").is_file())
            on_disk = json.loads((artifact / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["verdict"], "INCOMPLETE_TEARDOWN")

    def _execute_fixture(
        self,
        root: Path,
        *,
        run_driver_side_effect: Exception | None = None,
        observer_stop_side_effect: Exception | None = None,
    ) -> tuple[Path, SimpleNamespace, list[object]]:
        pilot = self._profile(root, "original")
        observer = self._profile(root, "replacement")
        server_root = root / "server"
        (server_root / "filterscripts").mkdir(parents=True)
        (server_root / "filterscripts/sync_pair.amx").write_bytes(b"fixture")
        settings = SimpleNamespace(
            clients={"original": pilot, "replacement": observer},
            artifacts_root=root / "artifacts",
            server_root=server_root,
            server_executable=server_root / "omp-server",
            server_ready_timeout_s=1,
            shutdown_timeout_s=1,
            host="127.0.0.1",
            port=7777,
        )
        args = SimpleNamespace(
            config=root / "reloop.toml",
            pilot="original",
            observer="replacement",
            scenario="passenger",
            server_mode="reuse",
            client_mode="replace",
            client_ready_timeout=1.0,
            pair_ready_timeout=1.0,
            fixture_timeout=1.0,
            action_seconds=0.1,
            between=0.0,
        )
        pilot_process = mock.Mock()
        observer_process = mock.Mock()
        observer_process.stop.side_effect = observer_stop_side_effect
        api = mock.Mock()
        run_driver = (
            mock.Mock(side_effect=run_driver_side_effect)
            if run_driver_side_effect is not None
            else mock.Mock(return_value=(0, root / "driver.log"))
        )
        patches = [
            mock.patch.object(sync_edge_probe.reloop, "load_settings", return_value=settings),
            mock.patch.object(sync_edge_probe.reloop, "run_id", return_value="edge-unit"),
            mock.patch.object(sync_edge_probe, "validate_layout", return_value={}),
            mock.patch.object(sync_edge_probe, "file_hashes", return_value={}),
            mock.patch.object(sync_edge_probe.reloop, "replace_existing_client"),
            mock.patch.object(sync_edge_probe, "tcp_port_available", return_value=True),
            mock.patch.object(
                sync_edge_probe.reloop, "replace_existing_server", return_value=True
            ),
            mock.patch.object(sync_edge_probe.reloop, "prefix_pids", return_value=set()),
            mock.patch.object(
                sync_edge_probe.reloop,
                "direct_client_launch",
                return_value=(["wine", "samp.exe", "-nTest"], {}),
            ),
            mock.patch.object(
                sync_edge_probe.reloop,
                "start_process",
                side_effect=[pilot_process, observer_process],
            ),
            mock.patch.object(sync_edge_probe, "wait_for_api", return_value=api),
            mock.patch.object(sync_edge_probe, "wait_for_pair"),
            mock.patch.object(sync_edge_probe, "run_driver", run_driver),
            mock.patch.object(sync_edge_probe.reloop, "terminate_pids", return_value=set()),
            mock.patch.object(sync_edge_probe.time, "sleep"),
        ]
        return settings.artifacts_root / "edge-unit", args, patches

    def test_runtime_exception_still_writes_complete_failure_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact, args, patches = self._execute_fixture(
                Path(directory),
                run_driver_side_effect=sync_edge_probe.SyncEdgeError("driver failed"),
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with self.assertRaisesRegex(sync_edge_probe.SyncEdgeError, "driver failed"):
                    sync_edge_probe.execute(args)

            verdict = json.loads((artifact / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["verdict"], "FAIL")
            self.assertTrue(verdict["artifact_complete"])
            self.assertIn("SyncEdgeError: driver failed", verdict["runner_error"])

    def test_teardown_error_does_not_skip_remaining_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact, args, patches = self._execute_fixture(
                Path(directory),
                observer_stop_side_effect=RuntimeError("observer stop failed"),
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with self.assertRaisesRegex(
                    sync_edge_probe.SyncEdgeError, "observer_stop"
                ):
                    sync_edge_probe.execute(args)

            verdict = json.loads((artifact / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["verdict"], "FAIL")
            self.assertTrue(verdict["artifact_complete"])
            self.assertTrue(
                any("observer_stop" in error for error in verdict["teardown_errors"])
            )


if __name__ == "__main__":
    unittest.main()
