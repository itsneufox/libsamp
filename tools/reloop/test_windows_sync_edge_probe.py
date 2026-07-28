import contextlib
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("windows_sync_edge_probe.py")
SPEC = importlib.util.spec_from_file_location("windows_sync_edge_probe", MODULE_PATH)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def make_x86_pe(path: Path, machine: int = 0x014C) -> None:
    value = bytearray(0x100)
    value[:2] = b"MZ"
    struct.pack_into("<I", value, 0x3C, 0x80)
    value[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", value, 0x84, machine)
    path.write_bytes(value)


class ParsingTests(unittest.TestCase):
    def test_extracts_nested_run_id(self):
        text = json.dumps(
            {
                "status": "ok",
                "result": {
                    "run_id": "20260727_123456_dist_edge_deadbeef",
                },
            }
        )
        self.assertEqual(
            probe.extract_run_id(text),
            "20260727_123456_dist_edge_deadbeef",
        )

    def test_extracts_pretty_json_after_ssh_banner(self):
        text = "\n".join(
            [
                "Warning: Permanently added 'host' (ED25519) to known hosts.",
                "{",
                '  "status": "ok",',
                '  "result": {',
                '    "run_id": "20260727_123456_dist_edge_deadbeef"',
                "  }",
                "}",
            ]
        )
        self.assertEqual(
            probe.extract_run_id(text),
            "20260727_123456_dist_edge_deadbeef",
        )

    def test_rejects_unsafe_or_missing_run_id(self):
        self.assertIsNone(probe.extract_run_id('{"result":{"run_id":"../bad"}}'))
        self.assertIsNone(probe.extract_run_id('{"status":"queued"}'))
        self.assertIsNone(probe.extract_run_id("not json"))

    def test_extracts_windows_process_inventory(self):
        self.assertEqual(
            probe.extract_processes(
                '{"result":{"processes":[{"name":"gta_sa","id":42}]}}'
            ),
            [{"name": "gta_sa", "id": 42}],
        )
        self.assertEqual(
            probe.extract_processes('{"result":{"processes":[]}}'),
            [],
        )
        self.assertIsNone(probe.extract_processes('{"status":"queued"}'))


class WindowsLogSliceTests(unittest.TestCase):
    def test_prefers_current_run_slices_over_historical_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archived = root / "run" / "logs"
            current = root / "run" / "latest_log_bytes"
            archived.mkdir(parents=True)
            current.mkdir()
            (archived / "samp_runtime.root.log").write_text(
                "exception_filter: historical\n",
                encoding="utf-8",
            )
            (current / "samp_runtime.root.log").write_text(
                "process_attach: current\nprocess_detach: done\n",
                encoding="utf-8",
            )

            collected = probe.collect_windows_logs(root)

            self.assertIn("process_attach: current", collected)
            self.assertNotIn("exception_filter: historical", collected)


class PeValidationTests(unittest.TestCase):
    def test_accepts_x86_pe_and_records_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samp.dll"
            make_x86_pe(path)
            result = probe.validate_x86_pe(path)
            self.assertEqual(result["machine"], "0x014C")
            self.assertEqual(result["sha256"], probe.reloop.sha256(path))

    def test_rejects_non_x86_pe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samp.dll"
            make_x86_pe(path, machine=0x8664)
            with self.assertRaisesRegex(probe.WindowsSyncEdgeError, "not x86"):
                probe.validate_x86_pe(path)


class DriverCommandTests(unittest.TestCase):
    def test_passenger_g_is_explicit_without_changing_legacy_all_set(self):
        self.assertIn("passenger_g", probe.WINDOWS_EDGE_SCENARIOS)
        self.assertNotIn("passenger_g", probe.EDGE_SCENARIOS)

    def test_passes_steering_capture_to_sync_pair_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = SimpleNamespace(returncode=0)
            with mock.patch.object(
                probe.subprocess, "run", return_value=completed
            ) as run:
                self.assertEqual(
                    probe.run_driver(
                        "trailer",
                        root,
                        fixture_timeout=1.0,
                        action_seconds=0.1,
                        screenshot_count=2,
                        screenshot_interval=0.025,
                        steer_during_capture="left",
                    ),
                    0,
                )
            command = run.call_args.args[0]
            self.assertEqual(
                command[-2:],
                ["--steer-during-capture", "left"],
            )

    def test_host_observer_screenshot_falls_back_to_original_f8(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gta_root = root / "gta"
            gta_root.mkdir()
            source = gta_root / "sa-mp-016.png"
            control = mock.Mock()

            def command_side_effect(command: str, **_fields):
                if command == "samp_screenshot":
                    raise RuntimeError("old control ASI")
                return {"ok": True}

            def key_side_effect(vk: int, action: str):
                self.assertEqual(vk, probe.VK_F8)
                if action == "down":
                    source.write_bytes(b"\x89PNG\r\n\x1a\nunit")
                return {"ok": True}

            control.command.side_effect = command_side_effect
            control.key.side_effect = key_side_effect
            with (
                mock.patch.object(
                    probe.reloop,
                    "take_screenshot",
                    return_value=(False, "gnome-screenshot:timeout"),
                ),
                mock.patch.object(probe.shutil, "which", return_value=None),
                mock.patch.object(probe, "wait_for_api", return_value=control),
            ):
                result = probe.capture_host_observer_screenshot(
                    root / "artifact",
                    "passenger_g",
                    SimpleNamespace(gta_root=gta_root),
                )

            destination = (
                root
                / "artifact/observer/screenshots/passenger_g-after-entry.png"
            )
            self.assertTrue(result["captured"])
            self.assertIn("original-r5-f8", result["backend"])
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(
                control.command.call_args_list,
                [
                    mock.call("samp_screenshot"),
                    mock.call("focus"),
                ],
            )
            self.assertEqual(
                control.key.call_args_list,
                [
                    mock.call(probe.VK_F8, "down"),
                    mock.call(probe.VK_F8, "up"),
                ],
            )
            control.close.assert_called_once_with()

    def test_host_observer_screenshot_uses_guarded_r5_request_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gta_root = root / "gta"
            gta_root.mkdir()
            prefix = root / "prefix"
            screens = (
                prefix
                / "drive_c/users/steamuser/Documents"
                / "GTA San Andreas User Files/SAMP/screens"
            )
            screens.mkdir(parents=True)
            source = screens / "sa-mp-003.png"
            control = mock.Mock()

            def command_side_effect(command: str, **_fields):
                self.assertEqual(command, "samp_screenshot")
                source.write_bytes(b"\x89PNG\r\n\x1a\nunit")
                return {"ok": True}

            control.command.side_effect = command_side_effect
            with (
                mock.patch.object(
                    probe.reloop,
                    "take_screenshot",
                    return_value=(False, "gnome-screenshot:timeout"),
                ),
                mock.patch.object(probe.shutil, "which", return_value=None),
                mock.patch.object(probe, "wait_for_api", return_value=control),
            ):
                result = probe.capture_host_observer_screenshot(
                    root / "artifact",
                    "passenger_g",
                    SimpleNamespace(gta_root=gta_root, prefix=prefix),
                )

            self.assertTrue(result["captured"])
            self.assertIn("original-r5-request-flag", result["backend"])
            self.assertEqual(result["source"], str(source))
            control.command.assert_called_once_with("samp_screenshot")
            control.key.assert_not_called()
            control.close.assert_called_once_with()

    def test_host_observer_screenshot_prefers_input_free_x11_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gta_root = root / "gta"
            gta_root.mkdir()

            def run_side_effect(command, **_kwargs):
                if command[0] == "xwininfo":
                    return SimpleNamespace(
                        returncode=0,
                        stdout=(
                            "xwininfo: Window id: 0x4a0001c "
                            '"GTA: San Andreas"\n'
                        ),
                    )
                self.assertEqual(command[0], "ffmpeg")
                Path(command[-1]).write_bytes(b"\x89PNG\r\n\x1a\nunit")
                return SimpleNamespace(returncode=0, stdout="")

            with (
                mock.patch.object(
                    probe.reloop,
                    "take_screenshot",
                    return_value=(False, "gnome-screenshot:timeout"),
                ),
                mock.patch.object(probe.shutil, "which", return_value="/usr/bin/tool"),
                mock.patch.object(
                    probe.subprocess,
                    "run",
                    side_effect=run_side_effect,
                ),
                mock.patch.object(
                    probe,
                    "wait_for_api",
                    side_effect=AssertionError(
                        "successful X11 capture must not inject F8"
                    ),
                ),
            ):
                result = probe.capture_host_observer_screenshot(
                    root / "artifact",
                    "passenger_g",
                    SimpleNamespace(gta_root=gta_root),
                )

            self.assertTrue(result["captured"])
            self.assertIn("x11-window:0x4a0001c", result["backend"])

    def test_windows_pilot_driver_only_queues_then_injects_g_then_waits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def queue_side_effect(*_args, **_kwargs):
                calls.append("queue")
                return 17

            def lab_side_effect(*_args, **_kwargs):
                calls.append("passenger")
                return SimpleNamespace(returncode=0, stdout="{}")

            def wait_side_effect(*_args, **_kwargs):
                calls.append("result")
                return "marker=PASSENGER_ENTRY_RESULT status=PASS"

            with (
                mock.patch.object(
                    probe.sync_pair_client,
                    "queue_sync_pair_scenario",
                    side_effect=queue_side_effect,
                ) as queue,
                mock.patch.object(probe, "run_lab", side_effect=lab_side_effect) as lab,
                mock.patch.object(
                    probe.sync_pair_client,
                    "wait_for_sync_pair_result",
                    side_effect=wait_side_effect,
                ) as wait,
                mock.patch.object(probe.time, "sleep"),
            ):
                returncode = probe.run_windows_pilot_driver(
                    "passenger_g",
                    root,
                    request_path=root / "request.txt",
                    results_path=root / "results.log",
                    fixture_timeout=1.0,
                    action_seconds=0.1,
                    lab_timeout=1.0,
                )

            self.assertEqual(returncode, 0)
            self.assertEqual(calls, ["queue", "passenger", "result"])
            self.assertEqual(queue.call_args.args[0], "passenger_g")
            self.assertEqual(lab.call_args.args[2][:2], ["key", "PASSENGER"])
            self.assertEqual(wait.call_args.args[:3], (
                "PASSENGER_ENTRY_RESULT",
                "passenger_g",
                17,
            ))
            result = json.loads(
                (root / "driver/passenger_g.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["input_action"], "PASSENGER")
            self.assertEqual(result["returncode"], 0)

    def test_windows_pilot_role_is_passenger_g_only(self):
        probe.validate_role_scenario("pilot", "passenger_g")
        for scenario in ("trailer", "passenger", "all"):
            with self.subTest(scenario=scenario):
                with self.assertRaisesRegex(
                    probe.WindowsSyncEdgeError,
                    "only supported",
                ):
                    probe.validate_role_scenario("pilot", scenario)


class VerdictTests(unittest.TestCase):
    def test_trace_pass_never_claims_visual_parity(self):
        verdict = probe.build_verdict(
            scenarios=["trailer"],
            server_text="marker=TRAILER_UPDATE count=1",
            windows_logs="\n".join(
                [
                    "packet-state id=210 remote_trailer seq=1",
                    "remote_trailer: apply seq=1 attached=1 readback=1",
                    "remote_edge: consume movement_seq=1 packet=210 "
                    "packet_seq=1 type=4 result=applied",
                ]
            ),
            windows_manifest={"samp_sha256": "replacement"},
            driver_returncodes={"trailer": 0},
            candidate=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
        )
        self.assertEqual(verdict["verdict"], "TRACE_PASS_VISUAL_UNVERIFIED")
        self.assertEqual(verdict["visual_parity"], "TODO_VERIFY")

    def test_windows_replacement_pilot_uses_original_host_observer_contract(self):
        server_text = "\n".join(
            [
                "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                "scenario=passenger_g detail=rpc=26 vehicle=4 "
                "expected_vehicle=4 is_passenger=1",
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=4 is_passenger=1 vehicle=4 seat=1 state=3",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=4",
            ]
        )
        verdict = probe.build_verdict(
            scenarios=["passenger_g"],
            server_text=server_text,
            windows_logs="replacement pilot process_attach",
            local_logs="original observer process_attach",
            windows_manifest={"samp_sha256": "replacement"},
            driver_returncodes={"passenger_g": 0},
            candidate=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_role="pilot",
            host_observer_screenshot={
                "captured": True,
                "backend": "unit",
                "path": "observer/screenshots/passenger_g-after-entry.png",
            },
        )

        self.assertEqual(
            verdict["verdict"],
            "SERVER_TRACE_PASS_OBSERVER_INTERNALS_UNAVAILABLE",
        )
        self.assertEqual(
            verdict["topology"],
            "native_windows_pilot+local_original_observer",
        )
        self.assertEqual(verdict["pilot_identity"], "installed_non_original")
        self.assertEqual(verdict["observer_identity"], "original_r5")
        self.assertTrue(verdict["windows_pilot_is_replacement"])
        self.assertNotIn(
            "observer_packet_decoded",
            verdict["scenarios"]["passenger_g"]["checks"],
        )

    def test_windows_original_pilot_cannot_pass_replacement_probe(self):
        server_text = "\n".join(
            [
                "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                "scenario=passenger_g detail=rpc=26 vehicle=4 "
                "expected_vehicle=4 is_passenger=1",
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=4 is_passenger=1 vehicle=4 seat=1 state=3",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=4",
            ]
        )
        verdict = probe.build_verdict(
            scenarios=["passenger_g"],
            server_text=server_text,
            windows_logs="original pilot process_attach",
            local_logs="original observer process_attach",
            windows_manifest={"samp_sha256": probe.ORIGINAL_R5_SHA256},
            driver_returncodes={"passenger_g": 0},
            candidate=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_role="pilot",
            host_observer_screenshot={
                "captured": True,
                "backend": "unit",
                "path": "observer/screenshots/passenger_g-after-entry.png",
            },
        )

        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(verdict["windows_pilot_is_replacement"])

    def test_windows_pilot_requires_host_observer_screenshot(self):
        server_text = "\n".join(
            [
                "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                "scenario=passenger_g detail=rpc=26 vehicle=4 "
                "expected_vehicle=4 is_passenger=1",
                "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                "enter_vehicle=4 is_passenger=1 vehicle=4 seat=1 state=3",
                "marker=PILOT_SYNC scenario=passenger_g sample=2 state=3 vehicle=4",
            ]
        )
        verdict = probe.build_verdict(
            scenarios=["passenger_g"],
            server_text=server_text,
            windows_logs="replacement pilot process_attach",
            local_logs="original observer process_attach",
            windows_manifest={"samp_sha256": "replacement"},
            driver_returncodes={"passenger_g": 0},
            candidate=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_role="pilot",
        )

        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(verdict["host_observer_screenshot_captured"])
        self.assertFalse(verdict["host_observer_screenshot_requirement_met"])


class ExecuteTests(unittest.TestCase):
    def make_fixture(
        self,
        root: Path,
        *,
        candidate: Path | None = None,
        driver_returncode: int = 0,
        scenario: str = "trailer",
        windows_role: str = "observer",
    ) -> tuple[Path, SimpleNamespace, list[object], mock.Mock]:
        original_prefix = root / "original"
        replacement_prefix = root / "replacement"
        original = probe.reloop.ClientProfile("original", original_prefix, None, None)
        replacement = probe.reloop.ClientProfile(
            "replacement", replacement_prefix, None, None
        )
        original.gta_root.mkdir(parents=True)
        replacement.gta_root.mkdir(parents=True)
        original.samp_exe.write_bytes(b"launcher")
        original.samp_dll.write_bytes(b"original")

        server_root = root / "server"
        (server_root / "filterscripts").mkdir(parents=True)
        (server_root / "scriptfiles").mkdir()
        (server_root / "filterscripts/sync_pair.amx").write_bytes(b"fixture")
        settings = SimpleNamespace(
            clients={"original": original, "replacement": replacement},
            artifacts_root=root / "artifacts",
            server_root=server_root,
            server_executable=server_root / "omp-server",
            server_ready_timeout_s=1,
            shutdown_timeout_s=1,
            host="127.0.0.1",
            port=7798,
        )
        args = SimpleNamespace(
            config=root / "reloop.toml",
            scenario=scenario,
            server_mode="reuse",
            local_client_mode="replace",
            windows_client_mode="replace",
            windows_role=windows_role,
            windows_server_host="192.168.3.181",
            windows_favorite_index=3,
            deploy_windows_dll=candidate,
            client_ready_timeout=1.0,
            pair_ready_timeout=1.0,
            fixture_timeout=1.0,
            action_seconds=0.1,
            between=0.0,
            screenshot_count=2,
            screenshot_interval=0.025,
            steer_during_capture=None,
            windows_start_timeout=1.0,
            lab_timeout=1.0,
            fetch_timeout=1.0,
        )
        artifact = settings.artifacts_root / "windows-edge-unit"
        pilot_process = mock.Mock()
        api = mock.Mock()
        lab_calls: list[list[str]] = []
        candidate_hash = probe.reloop.sha256(candidate) if candidate else None

        def lab_side_effect(
            artifact_dir: Path,
            label: str,
            arguments: list[str],
            *,
            timeout: float,
            check: bool = True,
        ):
            del timeout, check
            lab_calls.append(arguments)
            output = "{}"
            if arguments[0] == "start":
                output = '{"result":{"run_id":"windows_run_1"}}'
            elif arguments[0] in {"collect", "stop"}:
                output = '{"result":{"run_id":"windows_run_1"}}'
            elif arguments[0] == "fetch-run":
                fetched = artifact_dir / "windows" / "windows_run_1"
                latest = fetched / "latest_log_bytes"
                latest.mkdir(parents=True)
                installed_hash = candidate_hash or "installed-replacement"
                (fetched / "manifest.json").write_text(
                    json.dumps(
                        {
                            "run_id": "windows_run_1",
                            "samp_sha256": installed_hash,
                        }
                    ),
                    encoding="utf-8",
                )
                (latest / "samp_runtime.log").write_text(
                    (
                        "replacement pilot process_attach\n"
                        if windows_role == "pilot"
                        else "\n".join(
                            [
                                "packet-state id=210 remote_trailer seq=1",
                                "remote_trailer: apply seq=1 attached=1 readback=1",
                                "remote_edge: consume movement_seq=1 packet=210 "
                                "packet_seq=1 type=4 result=applied",
                                "",
                            ]
                        )
                    ),
                    encoding="utf-8",
                )
            return SimpleNamespace(returncode=0, stdout=output)

        def driver_side_effect(*_args, **_kwargs):
            if scenario == "passenger_g":
                markers = "\n".join(
                    [
                        "marker=PASSENGER_ENTER_REQUEST request=7 status=ACTION "
                        "scenario=passenger_g detail=rpc=26 vehicle=4 "
                        "expected_vehicle=4 is_passenger=1",
                        "marker=PASSENGER_ENTRY_RESULT request=7 status=PASS "
                        "scenario=passenger_g detail=rpc=26 enter_seen=1 "
                        "enter_vehicle=4 is_passenger=1 vehicle=4 "
                        "seat=1 state=3",
                        "marker=PILOT_SYNC scenario=passenger_g sample=2 "
                        "state=3 vehicle=4",
                        "",
                    ]
                )
            else:
                markers = "marker=TRAILER_UPDATE count=1\n"
            (server_root / "log.txt").write_text(
                markers,
                encoding="utf-8",
            )
            return driver_returncode

        def screenshot_side_effect(destination: Path):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"png")
            return True, "unit"

        patches = [
            mock.patch.object(probe.reloop, "load_settings", return_value=settings),
            mock.patch.object(
                probe.reloop, "run_id", return_value="windows-edge-unit"
            ),
            mock.patch.object(probe, "validate_layout", return_value={}),
            mock.patch.object(probe.reloop, "replace_existing_client"),
            mock.patch.object(probe.sync_edge_probe, "tcp_port_available", return_value=True),
            mock.patch.object(
                probe.reloop, "replace_existing_server", return_value=True
            ),
            mock.patch.object(probe.reloop, "prefix_pids", return_value=set()),
            mock.patch.object(
                probe.reloop,
                "direct_client_launch",
                return_value=(["wine", "samp.exe", "127.0.0.1:7798", "-nX"], {}),
            ),
            mock.patch.object(
                probe.reloop, "start_process", return_value=pilot_process
            ),
            (
                mock.patch.object(
                    probe,
                    "wait_for_api",
                    side_effect=AssertionError(
                        "local observer must not open the control API"
                    ),
                )
                if windows_role == "pilot"
                else mock.patch.object(probe, "wait_for_api", return_value=api)
            ),
            mock.patch.object(probe.sync_edge_probe, "wait_for_pair"),
            (
                mock.patch.object(
                    probe,
                    "run_driver",
                    side_effect=AssertionError(
                        "Windows pilot must not use the host-input driver"
                    ),
                )
                if windows_role == "pilot"
                else mock.patch.object(
                    probe, "run_driver", side_effect=driver_side_effect
                )
            ),
            mock.patch.object(
                probe,
                "run_windows_pilot_driver",
                side_effect=driver_side_effect,
            ),
            mock.patch.object(probe, "run_lab", side_effect=lab_side_effect),
            mock.patch.object(probe.reloop, "terminate_pids", return_value=set()),
            mock.patch.object(probe.sync_edge_probe, "file_hashes", return_value={}),
            mock.patch.object(
                probe.reloop,
                "take_screenshot",
                side_effect=screenshot_side_effect,
            ),
            mock.patch.object(probe.time, "sleep"),
        ]
        return artifact, args, patches, mock.Mock(side_effect=lambda: lab_calls)

    def test_without_explicit_candidate_never_validates_or_deploys(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact, args, patches, calls_getter = self.make_fixture(Path(directory))
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                _path, verdict = probe.execute(args)

            commands = [call[0] for call in calls_getter.side_effect()]
            self.assertNotIn("validate", commands)
            self.assertNotIn("deploy", commands)
            self.assertIn("collect", commands)
            self.assertIn("stop", commands)
            self.assertIn("fetch-run", commands)
            self.assertEqual(verdict["verdict"], "TRACE_PASS_VISUAL_UNVERIFIED")
            self.assertTrue((artifact / "windows/windows_run_1/manifest.json").is_file())

    def test_explicit_candidate_is_validated_then_deployed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate.dll"
            make_x86_pe(candidate)
            _artifact, args, patches, calls_getter = self.make_fixture(
                root, candidate=candidate
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                _path, verdict = probe.execute(args)

            commands = [call[0] for call in calls_getter.side_effect()]
            self.assertLess(commands.index("validate"), commands.index("deploy"))
            self.assertTrue(verdict["explicit_candidate_hash_matches_manifest"])

    def test_driver_failure_still_collects_stops_and_fetches(self):
        with tempfile.TemporaryDirectory() as directory:
            _artifact, args, patches, calls_getter = self.make_fixture(
                Path(directory), driver_returncode=7
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                with self.assertRaisesRegex(
                    probe.WindowsSyncEdgeError, "driver failed"
                ):
                    probe.execute(args)

            commands = [call[0] for call in calls_getter.side_effect()]
            self.assertIn("collect", commands)
            self.assertIn("stop", commands)
            self.assertIn("fetch-run", commands)

    def test_windows_pilot_swaps_nicknames_without_host_input_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact, args, patches, calls_getter = self.make_fixture(
                Path(directory),
                scenario="passenger_g",
                windows_role="pilot",
            )
            with contextlib.ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                _path, verdict = probe.execute(args)

            start = next(
                call for call in calls_getter.side_effect()
                if call[0] == "start"
            )
            self.assertEqual(start[5], "SyncPilot")
            launch_order = json.loads(
                (artifact / "launch-order.json").read_text(encoding="utf-8")
            )
            self.assertIn("-nSyncObserver", launch_order["local_observer"])
            self.assertFalse(launch_order["local_observer_api_verified"])
            self.assertFalse(launch_order["local_observer_api_required"])
            self.assertTrue(
                (
                    artifact
                    / "observer/screenshots/passenger_g-after-entry.png"
                ).is_file()
            )
            self.assertEqual(
                verdict["verdict"],
                "SERVER_TRACE_PASS_OBSERVER_INTERNALS_UNAVAILABLE",
            )
            self.assertEqual(verdict["windows_role"], "pilot")
            self.assertEqual(verdict["observer_identity"], "original_r5")
            self.assertTrue(verdict["windows_pilot_is_replacement"])
            self.assertTrue(verdict["host_observer_screenshot_captured"])


if __name__ == "__main__":
    unittest.main()
