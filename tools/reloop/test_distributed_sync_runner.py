import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("distributed_sync_runner.py")
SPEC = importlib.util.spec_from_file_location("distributed_sync_runner", MODULE_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def valid_ping(**overrides):
    result = {
        "processes": [],
        "game_dir": r"C:\Games\GTA",
        "gta_sha256": "1" * 64,
        "samp_sha256": "2" * 64,
        "samp_probe_sha256": "3" * 64,
        "reloop_control_sha256": None,
        "autopause": {
            "path": r"C:\Games\GTA\III.VC.SA.WindowedMode.ini",
            "exists": True,
            "value": "0",
            "disabled": True,
        },
        "probe_flags": [],
    }
    result.update(overrides)
    return json.dumps({"status": "ok", "result": result})


class ScenarioTests(unittest.TestCase):
    def test_all_is_focused_and_excludes_gmx_and_trailer(self):
        self.assertEqual(runner.expand_scenarios("all"), list(runner.SCENARIOS))
        self.assertNotIn("gmx", runner.SCENARIOS)
        self.assertNotIn("trailer", runner.SCENARIOS)
        self.assertEqual(
            runner.SCENARIOS,
            ("pistol", "m4", "sniper", "angles", "jetpack", "death", "pickup"),
        )

    def test_gmx_is_an_explicit_standalone_scenario(self):
        self.assertEqual(runner.expand_scenarios("gmx"), ["gmx"])

    def test_ui_latches_is_explicit_and_not_part_of_all(self):
        self.assertEqual(
            runner.expand_scenarios("ui_latches"),
            ["ui_latches"],
        )
        self.assertNotIn("ui_latches", runner.SCENARIOS)

    def test_rejects_unknown_scenario(self):
        with self.assertRaisesRegex(runner.DistributedSyncError, "unsupported"):
            runner.expand_scenarios("trailer")

    def test_windows_pilot_is_limited_to_death_and_gmx(self):
        runner.validate_role_scenario("observer", "m4")
        runner.validate_role_scenario("pilot", "death")
        runner.validate_role_scenario("pilot", "gmx")
        runner.validate_role_scenario("pilot", "ui_latches")
        with self.assertRaisesRegex(
            runner.DistributedSyncError,
            "only supported with --scenario=death",
        ):
            runner.validate_role_scenario("pilot", "m4")
        with self.assertRaisesRegex(
            runner.DistributedSyncError,
            "requires --windows-role=pilot",
        ):
            runner.validate_role_scenario("observer", "gmx")
        with self.assertRaisesRegex(
            runner.DistributedSyncError,
            "requires --windows-role=pilot",
        ):
            runner.validate_role_scenario("observer", "ui_latches")

    def test_role_topologies_are_explicit(self):
        self.assertEqual(
            runner.topology_for_role("observer"),
            "local_original_r5_pilot+native_windows_observer",
        )
        self.assertEqual(
            runner.topology_for_role("pilot"),
            "native_windows_pilot+local_original_r5_observer",
        )

    def test_death_f4_is_reversed_death_only(self):
        runner.validate_death_f4(False, "observer", "m4")
        runner.validate_death_f4(True, "pilot", "death")
        for role, scenario in (("observer", "death"), ("pilot", "m4")):
            with self.assertRaisesRegex(
                runner.DistributedSyncError,
                "requires --scenario=death and --windows-role=pilot",
            ):
                runner.validate_death_f4(True, role, scenario)

    def test_ui_latches_requires_the_focused_probe_profile(self):
        runner.validate_ui_latch_profile(
            "ui_latches",
            "ui-latches-r5",
        )
        with self.assertRaisesRegex(
            runner.DistributedSyncError,
            "requires --windows-probe-profile=ui-latches-r5",
        ):
            runner.validate_ui_latch_profile("ui_latches", None)
        runner.validate_ui_latch_profile("death", None)


class WindowsPreflightTests(unittest.TestCase):
    def test_parses_idle_hash_and_autopause_state(self):
        state = runner.parse_windows_preflight(valid_ping())
        runner.validate_windows_idle(state)
        runner.validate_probe_state(state, None)
        self.assertEqual(state["samp_sha256"], "2" * 64)
        self.assertTrue(state["autopause"]["disabled"])

    def test_rejects_missing_autopause_zero(self):
        text = valid_ping(
            autopause={
                "path": r"C:\Games\GTA\III.VC.SA.WindowedMode.ini",
                "exists": True,
                "value": "1",
                "disabled": False,
            }
        )
        with self.assertRaisesRegex(runner.DistributedSyncError, "autoPause"):
            runner.parse_windows_preflight(text)

    def test_rejects_non_idle_windows(self):
        state = runner.parse_windows_preflight(
            valid_ping(processes=[{"name": "gta_sa", "id": 42}])
        )
        with self.assertRaisesRegex(runner.DistributedSyncError, "not idle"):
            runner.validate_windows_idle(state)

    def test_requires_explicit_profile_for_preexisting_flags(self):
        state = runner.parse_windows_preflight(
            valid_ping(probe_flags=["samp_probe_death_cleanup_hooks.flag"])
        )
        with self.assertRaisesRegex(runner.DistributedSyncError, "unmanaged"):
            runner.validate_probe_state(state, None)
        runner.validate_probe_state(state, "death-cleanup")

    def test_exact_profile_flag_set_is_required(self):
        state = runner.parse_windows_preflight(
            valid_ping(
                probe_flags=[
                    "samp_probe_textdraw_hooks.flag",
                    "samp_probe_textdraw_verbose.flag",
                ]
            )
        )
        runner.validate_probe_state(state, "textdraw-verbose")
        with self.assertRaisesRegex(runner.DistributedSyncError, "mismatch"):
            runner.validate_probe_state(state, "textdraw")


class ExplicitMutationTests(unittest.TestCase):
    def test_default_plan_has_no_windows_mutations(self):
        self.assertEqual(
            runner.windows_mutation_plan(None, None, None, "unit"),
            [],
        )

    def test_explicit_options_are_the_only_mutations(self):
        dll = {"path": "/tmp/samp.dll", "sha256": "a" * 64}
        probe = {"path": "/tmp/samp_probe.asi", "sha256": "b" * 64}
        self.assertEqual(
            runner.windows_mutation_plan(
                dll,
                probe,
                "aim-bullet-jetpack",
                "unit",
            ),
            [
                ("dll-validate", ["validate", "/tmp/samp.dll"]),
                ("dll-deploy", ["deploy", "/tmp/samp.dll", "unit"]),
                (
                    "probe-deploy",
                    ["deploy-probe", "/tmp/samp_probe.asi", "unit"],
                ),
                (
                    "probe-profile",
                    ["probe-profile", "aim-bullet-jetpack"],
                ),
            ],
        )

    def test_verifies_deployment_and_profile_receipts(self):
        candidate = {"sha256": "a" * 64}
        receipt = json.dumps(
            {
                "target_sha256_after": "a" * 64,
                "backup": r"C:\samp-test\backups\samp.dll",
            }
        )
        self.assertEqual(
            runner.verify_deploy_receipt(
                receipt,
                candidate,
                kind="DLL",
            )["installed_sha256"],
            "a" * 64,
        )
        profile = runner.verify_profile_receipt(
            json.dumps(
                {
                    "profile": "death-cleanup",
                    "enabled": ["samp_probe_death_cleanup_hooks.flag"],
                    "probe_sha256": "b" * 64,
                }
            ),
            "death-cleanup",
        )
        self.assertEqual(profile["profile"], "death-cleanup")


class DriverTests(unittest.TestCase):
    def test_reuses_sync_pair_client_and_requests_windows_screenshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(
                runner.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as run:
                self.assertEqual(
                    runner.run_driver(
                        "jetpack",
                        root,
                        fixture_timeout=1.0,
                        action_seconds=0.1,
                        screenshot_count=3,
                        screenshot_interval=0.05,
                    ),
                    0,
                )
        command = run.call_args.args[0]
        self.assertIn("sync_pair_client.py", command[1])
        self.assertIn("jetpack", command)
        self.assertEqual(
            command[command.index("--observer-screenshot-count") + 1],
            "3",
        )

    def test_windows_death_driver_spans_request_with_screenshot_burst(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = root / "sync_pair_request.txt"
            results = root / "sync_pair_results.log"
            server = root / "server.log"
            server.write_text("", encoding="utf-8")
            calls = []

            def capture(label, count, interval):
                calls.append(("capture", label, count, interval))

            def queue(scenario, request_path, results_path, timeout, output):
                calls.append(("queue", scenario))
                output.append(
                    {
                        "event": "sync_pair_scenario_queued",
                        "request_id": 23,
                    }
                )
                return 23

            def wait(server_log, start_offset, request_id, timeout, output):
                calls.append(("wait", request_id))
                return "marker=PLAYER_DEATH player=0"

            with (
                mock.patch.object(
                    runner.sync_pair_client,
                    "capture_observer",
                    side_effect=capture,
                ),
                mock.patch.object(
                    runner.sync_pair_client,
                    "queue_sync_pair_scenario",
                    side_effect=queue,
                ),
                mock.patch.object(
                    runner,
                    "wait_for_death_event",
                    side_effect=wait,
                ),
                mock.patch.object(runner.time, "sleep"),
            ):
                returncode = runner.run_windows_death_driver(
                    root / "artifact",
                    request_path=request,
                    results_path=results,
                    server_log=server,
                    fixture_timeout=1.0,
                    screenshot_count=5,
                    screenshot_interval=0.05,
                )

            self.assertEqual(returncode, 0)
            self.assertEqual(calls[0][0], "capture")
            self.assertIn(("queue", "death"), calls)
            self.assertIn(("wait", 23), calls)
            self.assertTrue(
                any(
                    call[0] == "capture"
                    and call[2:] == (5, 0.05)
                    for call in calls
                )
            )
            payload = json.loads(
                (
                    root / "artifact/driver/death.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["windows_role"], "pilot")
            self.assertFalse(payload["death_f4"])
            self.assertEqual(payload["returncode"], 0)

    def test_windows_death_driver_can_latch_f4_before_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = root / "server.log"
            server.write_text("", encoding="utf-8")
            order = []

            def lab(_artifact, label, arguments, *, timeout):
                order.append(("lab", label, tuple(arguments), timeout))
                return SimpleNamespace(returncode=0, stdout="{}")

            def capture(label, count, interval):
                order.append(("capture", label, count, interval))

            def queue(_scenario, _request, _results, _timeout, output):
                order.append(("queue",))
                output.append(
                    {
                        "event": "sync_pair_scenario_queued",
                        "request_id": 29,
                    }
                )
                return 29

            def wait(*_args):
                order.append(("wait",))
                return "marker=PLAYER_DEATH player=0"

            with (
                mock.patch.object(runner.windows_edge, "run_lab", side_effect=lab),
                mock.patch.object(
                    runner.sync_pair_client,
                    "capture_observer",
                    side_effect=capture,
                ),
                mock.patch.object(
                    runner.sync_pair_client,
                    "queue_sync_pair_scenario",
                    side_effect=queue,
                ),
                mock.patch.object(
                    runner,
                    "wait_for_death_event",
                    side_effect=wait,
                ),
                mock.patch.object(runner.time, "sleep"),
            ):
                returncode = runner.run_windows_death_driver(
                    root / "artifact",
                    request_path=root / "request.txt",
                    results_path=root / "results.log",
                    server_log=server,
                    fixture_timeout=1.0,
                    screenshot_count=3,
                    screenshot_interval=0.05,
                    death_f4=True,
                    lab_timeout=7.0,
                )

            self.assertEqual(returncode, 0)
            self.assertEqual(order[0][0:2], ("lab", "pilot-death-f4"))
            self.assertEqual(order[0][2][0:2], ("key", "CLASS"))
            self.assertLess(
                next(index for index, item in enumerate(order) if item[0] == "lab"),
                next(index for index, item in enumerate(order) if item[0] == "queue"),
            )
            payload = json.loads(
                (
                    root / "artifact/driver/death.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(payload["death_f4"])
            events = [event["event"] for event in payload["events"]]
            self.assertIn("windows_pilot_death_f4_requested", events)
            self.assertIn("windows_pilot_death_f4_completed", events)

    def test_windows_gmx_driver_uses_console_and_captures_before_burst_after(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server_console = root / "server.console.log"
            server_console.write_text("initial server\n", encoding="utf-8")
            order = []

            class FakeProcess:
                def poll(self):
                    return None

            class FakeServer:
                process = FakeProcess()

                def send(self, command):
                    order.append(("send", command))

            def capture(label, count, interval):
                order.append(("capture", label, count, interval))

            def wait(
                _server_console,
                _start_offset,
                nickname,
                _timeout,
                output,
                _process,
            ):
                order.append(("wait", nickname))
                output.append(
                    {
                        "event": "windows_pilot_gmx_server_restart_observed",
                        "scenario": "gmx",
                    }
                )
                return "RPC137 ServerJoin player=0 name=SyncPilot"

            with (
                mock.patch.object(
                    runner.sync_pair_client,
                    "capture_observer",
                    side_effect=capture,
                ),
                mock.patch.object(
                    runner,
                    "wait_for_gmx_server_restart",
                    side_effect=wait,
                ),
                mock.patch.object(runner.time, "sleep"),
            ):
                returncode = runner.run_windows_gmx_driver(
                    root / "artifact",
                    server=FakeServer(),
                    server_console=server_console,
                    fixture_timeout=1.0,
                    screenshot_count=4,
                    screenshot_interval=0.05,
                )

            self.assertEqual(returncode, 0)
            self.assertEqual(order[0][0], "capture")
            self.assertIn(("send", "gmx"), order)
            self.assertIn(("wait", "SyncPilot"), order)
            self.assertEqual(order[-1][0], "capture")
            self.assertTrue(order[-1][1].endswith("-after"))
            payload = json.loads(
                (
                    root / "artifact/driver/gmx.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["command_source"], "open.mp_console")
            self.assertEqual(payload["returncode"], 0)
            events = [event["event"] for event in payload["events"]]
            self.assertIn("windows_pilot_gmx_sent", events)
            self.assertIn("windows_pilot_gmx_capture_completed", events)

    def test_windows_ui_latch_driver_uses_only_bounded_key_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []

            def lab(_artifact, label, arguments, *, timeout):
                calls.append((label, tuple(arguments), timeout))
                return SimpleNamespace(returncode=0, stdout="{}")

            with mock.patch.object(
                runner.windows_edge,
                "run_lab",
                side_effect=lab,
            ):
                returncode = runner.run_windows_ui_latches_driver(
                    root / "artifact",
                    lab_timeout=7.0,
                )

            self.assertEqual(returncode, 0)
            self.assertEqual(
                [call[1][1] for call in calls],
                ["TAB", "TAB", "F6", "F6", "F7", "F7", "F7"],
            )
            self.assertTrue(all(call[1][0] == "key" for call in calls))
            self.assertFalse(
                any(
                    key in {"ESCAPE", "PAUSE"}
                    for key in [call[1][1] for call in calls]
                )
            )
            payload = json.loads(
                (
                    root / "artifact/driver/ui_latches.json"
                ).read_text(encoding="utf-8")
            )
            self.assertFalse(
                payload["input_contract"]["pause_or_escape_automation"]
            )
            self.assertEqual(
                payload["input_contract"]["tab_keyup_pulses"],
                2,
            )
            self.assertEqual(payload["returncode"], 0)


class DeathEventTests(unittest.TestCase):
    def test_waits_for_request_scoped_death_event(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "server.log"
            server.write_text(
                "\n".join(
                    [
                        "marker=SCENARIO_START request=31 scenario=death pilot=0 observer=1",
                        "marker=PLAYER_DEATH player=0 killer=65535 reason=255 scenario=9",
                    ]
                ),
                encoding="utf-8",
            )
            output = []
            result = runner.wait_for_death_event(
                server,
                0,
                31,
                0.1,
                output,
            )
            self.assertIn("marker=PLAYER_DEATH", result)
            self.assertEqual(
                output[0]["event"],
                "windows_pilot_death_observed",
            )


class GmxEventTests(unittest.TestCase):
    def test_waits_for_post_gmx_banner_then_windows_pilot_rejoin(self):
        with tempfile.TemporaryDirectory() as directory:
            server = Path(directory) / "server.console.log"
            server.write_text(
                "\n".join(
                    [
                        "pre-existing output",
                        "Bare open.mp Vehicle/Object Test Script",
                        "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
                    ]
                ),
                encoding="utf-8",
            )
            output = []
            result = runner.wait_for_gmx_server_restart(
                server,
                len("pre-existing output\n"),
                "SyncPilot",
                0.1,
                output,
            )
            self.assertIn("name=SyncPilot", result)
            self.assertEqual(
                output[0]["event"],
                "windows_pilot_gmx_server_restart_observed",
            )

    def test_server_cycle_requires_two_markers_in_the_same_slice(self):
        text = "\n".join(
            [
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
            ]
        )
        self.assertEqual(
            runner.gmx_server_cycle_checks(text, "SyncPilot"),
            (True, True),
        )


class RequestCleanupTests(unittest.TestCase):
    def test_removes_only_request_owned_by_driver_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver = root / "artifact/driver"
            driver.mkdir(parents=True)
            (driver / "death.json").write_text(
                json.dumps(
                    [
                        {
                            "event": "sync_pair_scenario_queued",
                            "request_id": 17,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            request = root / "sync_pair_request.txt"
            request.write_text("17 death\n", encoding="utf-8")
            cleaned, error = runner.cleanup_owned_request(
                request,
                root / "artifact",
            )
            self.assertTrue(cleaned)
            self.assertIsNone(error)
            self.assertFalse(request.exists())
            self.assertEqual(
                (
                    root
                    / "artifact/cleanup/pending-sync-pair-request.txt"
                ).read_text(encoding="utf-8"),
                "17 death\n",
            )

    def test_leaves_foreign_request_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifact/driver").mkdir(parents=True)
            request = root / "sync_pair_request.txt"
            request.write_text("99 death\n", encoding="utf-8")
            cleaned, error = runner.cleanup_owned_request(
                request,
                root / "artifact",
            )
            self.assertFalse(cleaned)
            self.assertEqual(error, "pending_request_not_owned")
            self.assertTrue(request.exists())


class VerdictTests(unittest.TestCase):
    SERVER_TEXT = "\n".join(
        [
            "marker=REQUEST_ACCEPTED request=1 status=ACTION scenario=pistol detail=host_request",
            "marker=REQUEST_DONE request=1 status=PASS scenario=pistol detail=scenario_started",
            "marker=SCENARIO_START request=1 scenario=onfoot pilot=0 observer=1 weapon=22",
            "marker=WEAPON_SHOT shot=1 weapon=22 expected_weapon=22 hittype=2",
            "marker=REQUEST_ACCEPTED request=2 status=ACTION scenario=m4 detail=host_request",
            "marker=REQUEST_DONE request=2 status=PASS scenario=m4 detail=scenario_started",
            "marker=SCENARIO_START request=2 scenario=onfoot pilot=0 observer=1 weapon=31",
            "marker=WEAPON_SHOT shot=1 weapon=31 expected_weapon=31 hittype=2",
            "marker=REQUEST_ACCEPTED request=3 status=ACTION scenario=sniper detail=host_request",
            "marker=REQUEST_DONE request=3 status=PASS scenario=sniper detail=scenario_started",
            "marker=SCENARIO_START request=3 scenario=onfoot pilot=0 observer=1 weapon=34",
            "marker=WEAPON_SHOT shot=1 weapon=34 expected_weapon=34 hittype=2",
            "marker=REQUEST_ACCEPTED request=4 status=ACTION scenario=m4 detail=host_request",
            "marker=REQUEST_DONE request=4 status=PASS scenario=m4 detail=scenario_started",
            "marker=SCENARIO_START request=4 scenario=onfoot pilot=0 observer=1 weapon=31",
            "marker=PILOT_SYNC scenario=onfoot sample=1 weapon=31 facing=90.0000",
            "marker=PILOT_SYNC scenario=onfoot sample=2 weapon=31 facing=270.0000",
            "marker=REQUEST_ACCEPTED request=5 status=ACTION scenario=jetpack detail=host_request",
            "marker=REQUEST_DONE request=5 status=PASS scenario=jetpack detail=scenario_started",
            "marker=SCENARIO_START request=5 scenario=jetpack pilot=0 observer=1 weapon=0",
            "marker=PILOT_SYNC scenario=jetpack sample=1 special=2",
            "marker=REQUEST_ACCEPTED request=6 status=ACTION scenario=pickup detail=host_request",
            "marker=REQUEST_DONE request=6 status=PASS scenario=pickup detail=scenario_started",
            "marker=PICKUP_CREATED pickup=3 player=0",
            "marker=PICKUP_COLLECTED player=0 pickup=3 scenario=8",
            "marker=REQUEST_ACCEPTED request=7 status=ACTION scenario=death detail=host_request",
            "marker=REQUEST_DONE request=7 status=PASS scenario=death detail=scenario_started",
            "marker=DEATH_TRIGGER player=0 method=health_zero",
            "marker=PLAYER_DEATH player=0 killer=65535 reason=255 scenario=9",
        ]
    )
    REQUEST_IDS = {
        "pistol": 1,
        "m4": 2,
        "sniper": 3,
        "angles": 4,
        "jetpack": 5,
        "pickup": 6,
        "death": 7,
    }

    def test_request_trace_does_not_borrow_adjacent_m4_evidence(self):
        m4 = runner.request_trace(self.SERVER_TEXT, 2)
        angles = runner.request_trace(self.SERVER_TEXT, 4)
        self.assertIn("marker=WEAPON_SHOT", m4)
        self.assertNotIn("facing=270.0000", m4)
        self.assertNotIn("marker=WEAPON_SHOT", angles)
        self.assertIn("facing=270.0000", angles)

    def test_ui_latch_checks_require_all_bounded_probe_edges(self):
        windows_logs = "\n".join(
            [
                "ui_latches_hook: summary installed=9 requested=9",
                "ui_latches_r5: seq=1 kind=scoreboard_show reason=0x01",
                "ui_latches_r5: seq=2 kind=scoreboard_hide reason=0x01",
                "ui_latches_r5: seq=3 kind=chat_open reason=0x01",
                "ui_latches_r5: seq=4 kind=chat_close reason=0x01",
                "ui_latches_r5: seq=5 kind=chat_mode_toggle reason=0x01",
                "ui_latches_r5: seq=6 kind=chat_mode_toggle reason=0x01",
                "ui_latches_r5: seq=7 kind=chat_mode_toggle reason=0x01",
            ]
        )
        checks = runner.scenario_checks(
            "ui_latches",
            "",
            windows_logs,
            {"ui_latches": 0},
            {},
            "ui-latches-r5",
        )
        self.assertTrue(all(checks.values()))
        self.assertNotIn("request_id_recorded", checks)

        missing_edge = runner.scenario_checks(
            "ui_latches",
            "",
            windows_logs.rsplit("\n", 1)[0],
            {"ui_latches": 0},
            {},
            "ui-latches-r5",
        )
        self.assertFalse(missing_edge["three_chat_mode_edges_seen"])

    def test_success_is_trace_capture_never_visual_parity(self):
        verdict = runner.build_verdict(
            scenarios=list(runner.SCENARIOS),
            server_text=self.SERVER_TEXT,
            windows_logs="process_attach: current",
            local_logs="reloop_control: ready",
            windows_manifest={
                "samp_sha256": "f" * 64,
                "samp_probe_sha256": None,
                "autopause": {"disabled": True},
                "probe_flags": [],
            },
            driver_returncodes={scenario: 0 for scenario in runner.SCENARIOS},
            driver_request_ids_by_scenario=self.REQUEST_IDS,
            dll_candidate=None,
            probe_candidate=None,
            requested_probe_profile=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=True,
        )
        self.assertEqual(
            verdict["verdict"],
            "TRACE_CAPTURED_VISUAL_UNVERIFIED",
        )
        self.assertEqual(verdict["visual_parity"], "TODO_VERIFY")
        self.assertNotIn("PASS", verdict["verdict"].replace("UNVERIFIED", ""))

    def test_missing_screenshot_or_hash_mismatch_fails(self):
        verdict = runner.build_verdict(
            scenarios=["death"],
            server_text=self.SERVER_TEXT,
            windows_logs="process_attach: current",
            local_logs="reloop_control: ready",
            windows_manifest={
                "samp_sha256": "f" * 64,
                "samp_probe_sha256": None,
                "autopause": {"disabled": True},
                "probe_flags": [],
            },
            driver_returncodes={"death": 0},
            driver_request_ids_by_scenario={"death": 7},
            dll_candidate={"sha256": "e" * 64},
            probe_candidate=None,
            requested_probe_profile=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=False,
        )
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertFalse(verdict["explicit_dll_hash_matches_manifest"])
        self.assertFalse(verdict["windows_screenshots_fetched"])

    def test_reversed_death_verdict_records_actual_roles(self):
        verdict = runner.build_verdict(
            windows_role="pilot",
            scenarios=["death"],
            server_text=self.SERVER_TEXT,
            windows_logs="process_attach: original r5",
            local_logs="observer connected",
            windows_manifest={
                "samp_sha256": runner.ORIGINAL_R5_SHA256,
                "samp_probe_sha256": None,
                "autopause": {"disabled": True},
                "probe_flags": [],
            },
            driver_returncodes={"death": 0},
            driver_request_ids_by_scenario={"death": 7},
            dll_candidate=None,
            probe_candidate=None,
            requested_probe_profile=None,
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=True,
        )
        self.assertEqual(verdict["windows_role"], "pilot")
        self.assertEqual(verdict["local_role"], "observer")
        self.assertEqual(
            verdict["topology"],
            "native_windows_pilot+local_original_r5_observer",
        )
        self.assertEqual(verdict["windows_identity"], "original_r5")

    def test_original_r5_gmx_requires_rpc_cycle_and_cleanup_probe_event(self):
        gmx_server = "\n".join(
            [
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
            ]
        )
        windows_logs = "\n".join(
            [
                "rpc-in id=139 name=ScrInitGame",
                "rpc-in id=40 name=ScrGameModeRestart",
                "death_cleanup_r5: seq=1 kind=gmx_reset cleanup=1",
                "rpc-in id=139 name=ScrInitGame",
            ]
        )
        verdict = runner.build_verdict(
            windows_role="pilot",
            scenarios=["gmx"],
            server_text=gmx_server,
            windows_logs=windows_logs,
            local_logs="observer connected",
            windows_manifest={
                "samp_sha256": runner.ORIGINAL_R5_SHA256,
                "samp_probe_sha256": "a" * 64,
                "autopause": {"disabled": True},
                "probe_flags": ["samp_probe_death_cleanup_hooks.flag"],
            },
            driver_returncodes={"gmx": 0},
            driver_request_ids_by_scenario={},
            dll_candidate=None,
            probe_candidate=None,
            requested_probe_profile="death-cleanup",
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=True,
        )
        self.assertEqual(
            verdict["verdict"],
            "TRACE_CAPTURED_VISUAL_UNVERIFIED",
        )
        self.assertTrue(
            all(verdict["scenarios"]["gmx"]["checks"].values())
        )
        self.assertEqual(verdict["windows_identity"], "original_r5")

    def test_original_r5_cleanup_gmx_does_not_require_replacement_net_trace(self):
        gmx_server = "\n".join(
            [
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
            ]
        )
        verdict = runner.build_verdict(
            windows_role="pilot",
            scenarios=["gmx"],
            server_text=gmx_server,
            windows_logs=(
                "ui-neutral original trace\n"
                "death_cleanup_r5: seq=1 event=1 kind=gmx_reset cleanup=1\n"
            ),
            local_logs="observer connected",
            windows_manifest={
                "samp_sha256": runner.ORIGINAL_R5_SHA256,
                "samp_probe_sha256": "a" * 64,
                "autopause": {"disabled": True},
                "probe_flags": ["samp_probe_death_cleanup_hooks.flag"],
            },
            driver_returncodes={"gmx": 0},
            driver_request_ids_by_scenario={},
            dll_candidate=None,
            probe_candidate=None,
            requested_probe_profile="death-cleanup",
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=True,
        )
        checks = verdict["scenarios"]["gmx"]["checks"]
        self.assertNotIn("initial_init_seen", checks)
        self.assertNotIn("gmx_rpc40_seen", checks)
        self.assertNotIn("post_gmx_init_seen", checks)
        self.assertTrue(all(checks.values()))
        self.assertEqual(
            "TRACE_CAPTURED_VISUAL_UNVERIFIED",
            verdict["verdict"],
        )

    def test_original_probe_gmx_rejects_non_r5_manifest_hash(self):
        gmx_server = "\n".join(
            [
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
                "Bare open.mp Vehicle/Object Test Script",
                "[bare-rpctest] RPC137 ServerJoin player=0 name=SyncPilot npc=0",
            ]
        )
        verdict = runner.build_verdict(
            windows_role="pilot",
            scenarios=["gmx"],
            server_text=gmx_server,
            windows_logs="death_cleanup_r5: kind=gmx_reset cleanup=1",
            local_logs="observer connected",
            windows_manifest={
                "samp_sha256": "f" * 64,
                "samp_probe_sha256": "a" * 64,
                "autopause": {"disabled": True},
                "probe_flags": ["samp_probe_death_cleanup_hooks.flag"],
            },
            driver_returncodes={"gmx": 0},
            driver_request_ids_by_scenario={},
            dll_candidate=None,
            probe_candidate=None,
            requested_probe_profile="death-cleanup",
            runner_error=None,
            cleanup_errors=[],
            local_hashes_unchanged=True,
            windows_artifact_fetched=True,
            windows_logs_fetched=True,
            windows_screenshots_fetched=True,
        )
        self.assertEqual("FAIL", verdict["verdict"])
        self.assertTrue(verdict["original_probe_identity_required"])
        self.assertFalse(verdict["original_probe_identity_matches"])


if __name__ == "__main__":
    unittest.main()
