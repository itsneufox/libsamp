#!/usr/bin/env python3
"""Unit tests for lifecycle_probe's artifact-only analyzer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from lifecycle_probe import _click_replacement_spawn_button, analyze_lifecycle


SUCCESS_RUNTIME = """\
[sampdll-runtime] object: bridge active events=3 active=2 pending=0 latest_seq=3
[sampdll-runtime] mp_session_bridge: spawn_finalize seq=1 previous=0 outcome=1
[sampdll-runtime] textdraw: show seq=7 id=14 pos=(320.00,240.00)
[sampdll-runtime] menu_overlay: active event_seq=9 menu=2 columns=1 rows=12/0
[sampdll-runtime] menu_native: hidden panel=1 reason=gamemode_restart active=1 ok=1
[sampdll-runtime] object: destroy id=4 gta=91 visual=1 reason=gamemode_restart
[sampdll-runtime] remote_player: destroy id=3 gta=44 path=actor gta_slot=0 player_destroyed=1 reason=gamemode_restart
[sampdll-runtime] client_control: session_reset reason=gamemode_restart generation=1 logical_state=WAIT_CONNECT transport_connected=1 session_reset=complete preconnect_ready=0
[sampdll-runtime] client_control: consumers_reset generation=1 reason=session_reset
[sampdll-runtime] chat_d3dx: drawing enabled textdraws=0
[sampdll-runtime] mp_session_bridge: spawn_finalize seq=2 previous=0 outcome=1
[sampdll-runtime] chat_input: local quit command connected=1->0 block_ms=500
[sampdll-runtime] chat_input: quit_after_frame elapsed_ms=1002 action=network_shutdown
[sampdll-runtime] chat_input: quit_after_frame action=ExitProcess code=0
"""

SUCCESS_NET = """\
rpc-in id=137 name=ScrServerJoin count=1
rpc-in id=139 name=ScrInitGame count=1
rpc-in id=40 name=ScrGameModeRestart count=1
rpc-state id=40 game_mode_restart_seq=1 session_probe_reset=1 transport_preserved=1
rpc-in id=139 name=ScrInitGame count=1
"""

SUCCESS_PROBE = """\
call: WSAStartup count=1 rc=0 err=0
call: WSACleanup count=1 rc=0 err=0
call: WSACleanup count=2 rc=0 err=0
"""


class LifecycleAnalyzerTests(unittest.TestCase):
    def make_run(
        self,
        root: Path,
        runtime: str = SUCCESS_RUNTIME,
        net: str = SUCCESS_NET,
        probe: str = SUCCESS_PROBE,
        done: bool = True,
    ) -> Path:
        run = root / "run"
        client = run / "client"
        client.mkdir(parents=True)
        (client / "samp_runtime.log").write_text(runtime, encoding="utf-8")
        (client / "samp_net_trace.log").write_text(net, encoding="utf-8")
        (client / "samp_probe.log").write_text(probe, encoding="utf-8")
        (run / "server.console.log").write_text("Legacy Network started\n", encoding="utf-8")
        (run / "server-results.log").write_text(
            "[test_cmds] event=ui_textdraw status=OBSERVE\n", encoding="utf-8"
        )
        records = [
            {"state": "GMX_SENT"},
            {"state": "CLIENT_NATIVE_EXIT", "clean": True},
        ]
        if done:
            records.append({"state": "RUNNER_DONE"})
        (run / "lifecycle-events.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return run

    def test_success_accepts_expected_missing_process_detach(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(Path(directory))
            result = analyze_lifecycle(run, write_outputs=False)

        self.assertEqual("PASS", result["verdict"])
        self.assertEqual([], result["required_failures"])
        self.assertEqual(
            "EXPECTED_ABSENT_EXITPROCESS", result["diagnostics"]["process_detach"]
        )
        self.assertIn(
            "process_detach_classification", result["informational_checks"]
        )

    def test_invalid_winsock_cleanup_and_missing_reinit_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(
                Path(directory),
                net=SUCCESS_NET.rsplit("rpc-in id=139", 1)[0],
                probe=SUCCESS_PROBE
                + "call: WSACleanup count=3 rc=-1 err=10093\n",
            )
            result = analyze_lifecycle(run, write_outputs=False)

        self.assertEqual("FAIL", result["verdict"])
        self.assertIn("post_gmx_init", result["required_failures"])
        self.assertIn("winsock_cleanup_valid", result["required_failures"])
        self.assertEqual(1, result["diagnostics"]["wsa_cleanup_failure_count"])

    def test_runner_error_is_a_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = self.make_run(Path(directory), done=False)
            with (run / "lifecycle-events.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"state": "RUNNER_ERROR", "error": "timeout"}) + "\n")
            result = analyze_lifecycle(run, write_outputs=False)

        self.assertEqual("FAIL", result["verdict"])
        self.assertIn("runner_completed", result["required_failures"])

    def test_spawn_button_click_tracks_replacement_layout(self) -> None:
        class FakeControl:
            def __init__(self) -> None:
                self.commands: list[tuple[str, dict[str, object]]] = []

            def command(self, command: str, **fields: object) -> dict[str, object]:
                self.commands.append((command, fields))
                return {"ok": True}

        control = FakeControl()
        _click_replacement_spawn_button(  # type: ignore[arg-type]
            control, {"client_w": 640, "client_h": 448}
        )
        self.assertEqual(
            [("mouse", {"action": "click", "x": 416, "y": 394})],
            control.commands,
        )


if __name__ == "__main__":
    unittest.main()
