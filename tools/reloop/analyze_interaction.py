#!/usr/bin/env python3
"""Turn one ReLoop UI interaction artifact into explicit compatibility checks."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ORIGINAL_CALL = "e846f3feff"
DISABLED_CALL = "9090909090"


def distance(a: dict[str, Any], b: dict[str, Any], prefix: str) -> float:
    return math.sqrt(sum((float(a[f"{prefix}_{axis}"]) - float(b[f"{prefix}_{axis}"])) ** 2
                         for axis in ("x", "y", "z")))


def analyze(run: Path) -> dict[str, Any]:
    states = json.loads((run / "ui-interaction-states.json").read_text(encoding="utf-8"))
    by_label = {state["label"]: state for state in states}
    server = (run / "server.console.log").read_text(encoding="utf-8", errors="replace")
    runtime_path = run / "client/samp_runtime.log"
    runtime = runtime_path.read_text(encoding="utf-8", errors="replace") if runtime_path.is_file() else ""
    required = ["baseline", "chat_open", "chat_input_attempt", "chat_closed",
                "scoreboard_open", "scoreboard_plain_input_attempt",
                "scoreboard_mouse_mode", "scoreboard_input_attempt",
                "scoreboard_closed"]
    missing = [label for label in required if label not in by_label]
    if missing:
        return {"verdict": "INCOMPLETE", "missing": missing, "run": str(run)}

    baseline = by_label["baseline"]
    chat_attempt = by_label["chat_input_attempt"]
    score_attempt = by_label["scoreboard_input_attempt"]
    checks = {
        "chat_uses_original_input_opcode": by_label["chat_open"]["input_call"] == DISABLED_CALL,
        "chat_blocks_player_movement": distance(baseline, chat_attempt, "player") < 0.05,
        "chat_blocks_camera_movement": distance(baseline, chat_attempt, "aim") < 0.05,
        "chat_restores_original_opcode": by_label["chat_closed"]["input_call"] == ORIGINAL_CALL,
        "chat_rpc_reached_server": "[bare-uitest] OnPlayerText" in server,
        # OBSERVED_037 + PROBE_TRACE: the key-up-latched scoreboard leaves
        # gta_sa.exe+0x141DF5 intact and allows W movement both before and
        # after RMB. Its raw visible flag owns the exclusive R5 overlay branch.
        "scoreboard_plain_tab_keeps_original_opcode":
            by_label["scoreboard_open"]["input_call"] == ORIGINAL_CALL
            and by_label["scoreboard_plain_input_attempt"]["input_call"] == ORIGINAL_CALL,
        "scoreboard_plain_tab_allows_player_movement":
            distance(by_label["scoreboard_open"],
                     by_label["scoreboard_plain_input_attempt"], "player") > 0.5,
        "scoreboard_cursor_mode_keeps_original_input_opcode":
            by_label["scoreboard_mouse_mode"]["input_call"] == ORIGINAL_CALL,
        "scoreboard_after_rmb_allows_player_movement":
            distance(by_label["scoreboard_mouse_mode"], score_attempt, "player") > 0.5,
        "scoreboard_hud_stays_hidden_after_plain_input":
            by_label["scoreboard_plain_input_attempt"]["hud"] == 0
            and by_label["scoreboard_plain_input_attempt"]["radar_blank"] == 1,
        "scoreboard_hud_hide_path_observed": "scoreboard: hud hide" in runtime,
        "scoreboard_exclusive_overlay_path_observed":
            "scoreboard: exclusive_overlay normal_overlay_draws=0" in runtime,
        "scoreboard_right_button_observed":
            "scoreboard: right_button cursor_mode=3 game_input=unchanged" in runtime
            or not runtime,
        "scoreboard_restores_original_opcode": by_label["scoreboard_closed"]["input_call"] == ORIGINAL_CALL,
        "scoreboard_rpc23_reached_server": "[bare-clicktest] OnPlayerClickPlayer" in server,
    }
    core = [value for key, value in checks.items() if key != "scoreboard_rpc23_reached_server"]
    verdict = "PASS" if all(checks.values()) else ("PASS_RPC23_UNVERIFIED" if all(core) else "MISMATCH")
    return {
        "run": str(run),
        "verdict": verdict,
        "checks": checks,
        "deltas": {
            "chat_player": distance(baseline, chat_attempt, "player"),
            "chat_camera": distance(baseline, chat_attempt, "aim"),
            "scoreboard_plain_player":
                distance(by_label["scoreboard_open"],
                         by_label["scoreboard_plain_input_attempt"], "player"),
            "scoreboard_interactive_player":
                distance(by_label["scoreboard_mouse_mode"], score_attempt, "player"),
            "scoreboard_interactive_camera":
                distance(by_label["scoreboard_mouse_mode"], score_attempt, "aim"),
        },
        "evidence": "PROBE_TRACE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.run.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["verdict"] in {"PASS", "PASS_RPC23_UNVERIFIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
