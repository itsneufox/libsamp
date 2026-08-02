import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("reloop.py")
SPEC = importlib.util.spec_from_file_location("reloop", MODULE_PATH)
assert SPEC and SPEC.loader
reloop = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reloop
SPEC.loader.exec_module(reloop)


class ResultParsingTests(unittest.TestCase):
    def test_parse_result_line(self):
        parsed = reloop.parse_result_line(
            "[test_cmds] request=123 run=1 player=0 name=ReLoop case=vehicle "
            "step=2 status=PASS event=vehicle_enter_verify detail=ok"
        )
        self.assertEqual(parsed["request"], "123")
        self.assertEqual(parsed["status"], "PASS")
        self.assertEqual(parsed["event"], "vehicle_enter_verify")

    def test_done_with_observation_is_warning_pass(self):
        lines = [
            "[test_cmds] request=1 marker=RUN_START status=ACTION",
            "[test_cmds] request=1 status=OBSERVE event=ui_gametext",
            "[test_cmds] request=1 marker=RUN_DONE status=PASS",
        ]
        verdict, warnings = reloop.classify_run(lines, None, "", False)
        self.assertEqual(verdict, "PASS_WITH_WARNINGS")
        self.assertTrue(warnings)

    def test_preconnect_exit(self):
        verdict, _warnings = reloop.classify_run([], 1, "", False)
        self.assertEqual(verdict, "PRECONNECT_CRASH")

    def test_preconnect_streaming_timeout_uses_last_open_step(self):
        client_logs = "\n".join([
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadSceneCollision phase=begin evidence=PROBE_TRACE",
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadSceneCollision phase=end evidence=PROBE_TRACE",
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadScene phase=begin evidence=PROBE_TRACE",
        ])
        verdict, warnings = reloop.classify_run([], 0, client_logs, True)
        self.assertEqual(verdict, "HANG_PRECONNECT_STREAMING")
        self.assertIn("reason=preconnect step=LoadScene phase=begin", warnings[0])
        self.assertIn("Join/NetGame evidence absent", warnings[0])

    def test_spawn_streaming_timeout_requires_join_evidence(self):
        client_logs = "\n".join([
            "rpc-auto-out id=25 name=ClientJoin nickname=ReLoop sent=1",
            "rpc-in id=139 name=ScrInitGame local=implemented count=1",
            "[sampdll-runtime] scene_prepare_step: reason=spawn "
            "step=LoadSceneCollision phase=begin evidence=PROBE_TRACE",
            "[sampdll-runtime] scene_prepare_step: reason=spawn "
            "step=LoadSceneCollision phase=end evidence=PROBE_TRACE",
            "[sampdll-runtime] scene_prepare_step: reason=spawn "
            "step=LoadScene phase=begin evidence=PROBE_TRACE",
        ])
        verdict, warnings = reloop.classify_run([], 0, client_logs, True)
        self.assertEqual(verdict, "HANG_SPAWN_STREAMING")
        self.assertIn("Join/NetGame evidence present", warnings[0])

    def test_closed_streaming_step_is_not_classified_as_hang(self):
        client_logs = "\n".join([
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadScene phase=begin evidence=PROBE_TRACE",
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadScene phase=end evidence=PROBE_TRACE",
        ])
        verdict, _warnings = reloop.classify_run([], 0, client_logs, True)
        self.assertEqual(verdict, "PRECONNECT_CRASH")

    def test_exception_marker_takes_precedence_over_open_streaming_step(self):
        client_logs = "\n".join([
            "[sampdll-runtime] scene_prepare_step: reason=preconnect "
            "step=LoadScene phase=begin evidence=PROBE_TRACE",
            "[sampdll-runtime] exception_filter: code=0xc0000005",
        ])
        verdict, _warnings = reloop.classify_run([], 1, client_logs, True)
        self.assertEqual(verdict, "PRECONNECT_CRASH")

    def test_failure_is_state_mismatch(self):
        lines = [
            "[test_cmds] request=1 marker=RUN_START status=ACTION",
            "[test_cmds] request=1 status=FAIL event=vehicle_enter_verify",
            "[test_cmds] request=1 marker=RUN_DONE status=FAIL",
        ]
        verdict, _warnings = reloop.classify_run(lines, None, "", False)
        self.assertEqual(verdict, "STATE_MISMATCH")

    def test_crash_retry_requires_remaining_attempt(self):
        self.assertTrue(reloop.should_retry_crash("PRECONNECT_CRASH", 1, 3))
        self.assertTrue(reloop.should_retry_crash("RUNTIME_CRASH", 2, 3))
        self.assertTrue(reloop.should_retry_crash("HANG_PRECONNECT_STREAMING", 1, 3))
        self.assertTrue(reloop.should_retry_crash("HANG_SPAWN_STREAMING", 2, 3))
        self.assertFalse(reloop.should_retry_crash("RUNTIME_CRASH", 3, 3))
        self.assertFalse(reloop.should_retry_crash("HANG_SPAWN_STREAMING", 3, 3))
        self.assertFalse(reloop.should_retry_crash("STATE_MISMATCH", 1, 3))

    def test_retry_wrapper_enforces_three_attempt_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempts = []

            def fake_execute_run(**_kwargs):
                attempt = len(attempts) + 1
                artifact = root / f"attempt-{attempt}"
                artifact.mkdir()
                (artifact / "metadata.json").write_text(
                    '{"run_id":"test","client":"replacement","prefix":"p","request_id":1,'
                    '"group":"all","delay_ms":1200,"started_at":"now"}\n',
                    encoding="utf-8",
                )
                verdict = {
                    "verdict": "PRECONNECT_CRASH",
                    "warnings": [],
                    "finished_at": "now",
                    "result_line_count": 0,
                }
                attempts.append(attempt)
                return artifact, verdict

            with mock.patch.object(reloop, "execute_run", side_effect=fake_execute_run) as execute_run:
                final, _verdict = reloop.execute_with_crash_retries(
                    settings=object(), client_name="replacement", group="all", delay_ms=1200,
                    timeout_s=30, server_mode="replace", client_mode="replace", build=False,
                    deploy=False, screenshots=False, keep_client=False, crash_attempts=1,
                )

            self.assertEqual(attempts, [1, 2, 3])
            retry_record = __import__("json").loads((final / "retry-series.json").read_text(encoding="utf-8"))
            self.assertTrue(retry_record["repeated_crash"])


class SnapshotTests(unittest.TestCase):
    def test_capture_only_appended_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.log"
            destination = Path(directory) / "captured.log"
            source.write_text("old\n", encoding="utf-8")
            snapshot = reloop.FileSnapshot.take(source)
            with source.open("a", encoding="utf-8") as handle:
                handle.write("new\n")
            self.assertEqual(snapshot.capture_append(destination), 4)
            self.assertEqual(destination.read_text(encoding="utf-8"), "new\n")


class MetadataTests(unittest.TestCase):
    def test_metadata_hashes_match_deployed_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / "prefix"
            profile = reloop.ClientProfile("replacement", prefix, None, None)
            profile.gta_root.mkdir(parents=True)
            profile.samp_dll.write_bytes(b"previous dll")
            previous_hash = reloop.sha256(profile.samp_dll)

            built_dll = root / "build" / "samp.dll"
            built_dll.parent.mkdir()
            built_dll.write_bytes(b"current dll")
            pawn_output = root / "test_cmds.amx"
            pawn_output.write_bytes(b"current pawn")
            settings = type("SettingsStub", (), {
                "built_dll": built_dll,
                "pawn_output": pawn_output,
                "clients": {"replacement": profile},
            })()
            artifact_dir = root / "artifact"
            metadata = {
                "dll_sha256": previous_hash,
                "built_dll_sha256": "stale-build-hash",
                "pawn_sha256": "stale-pawn-hash",
            }

            deploy = reloop.deploy_replacement(settings, artifact_dir / "build")
            reloop.write_run_metadata(artifact_dir, metadata, settings, profile)

            persisted = __import__("json").loads(
                (artifact_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["dll_sha256"], deploy["installed_sha256"])
            self.assertEqual(persisted["dll_sha256"], persisted["built_dll_sha256"])
            self.assertEqual(persisted["pawn_sha256"], reloop.sha256(pawn_output))
            self.assertNotEqual(persisted["dll_sha256"], previous_hash)


class ComparisonTests(unittest.TestCase):
    def test_matching_state_is_not_claimed_as_opcode_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            candidate = root / "candidate"
            output = root / "comparison"
            for run in (reference, candidate):
                run.mkdir()
                (run / "verdict.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
                (run / "server-results.log").write_text(
                    "[test_cmds] request=1 status=PASS event=player_state_verify\n",
                    encoding="utf-8",
                )

            result = reloop.compare_runs(reference, candidate, output)

            self.assertEqual(result["state_verdict"], "PASS")
            self.assertEqual(result["opcode_path_verdict"], "TODO_VERIFY")
            self.assertEqual(result["verdict"], "OPCODE_PARITY_UNVERIFIED")


class LaunchTests(unittest.TestCase):
    def test_direct_launch_uses_samp_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proton = root / "proton"
            wine = proton / "files/bin/wine"
            wine.parent.mkdir(parents=True)
            wine.write_bytes(b"wine")
            wine.chmod(0o755)
            (proton / "files/lib").mkdir(parents=True)
            prefix = root / "prefix"
            gta_root = prefix / reloop.GTA_RELATIVE_ROOT
            gta_root.mkdir(parents=True)
            samp_exe = gta_root / "samp.exe"
            samp_exe.write_bytes(b"samp")
            profile = reloop.ClientProfile("original", prefix, None, None)
            settings = type("SettingsStub", (), {
                "proton_root": proton,
                "host": "127.0.0.1",
                "port": 7778,
                "nickname": "ReLoop",
            })()

            command, _env = reloop.direct_client_launch(settings, profile, root / "artifact")

            self.assertEqual(command, [str(wine), str(samp_exe), "127.0.0.1:7778", "-nReLoop"])


if __name__ == "__main__":
    unittest.main()
