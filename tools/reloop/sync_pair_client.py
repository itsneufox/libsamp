#!/usr/bin/env python3
"""Drive the SyncPilot side of the deterministic two-client fixture."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from control_client import ControlClient, wait_for_api

VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_SPACE = 0x20
VK_A = ord("A")
VK_D = ord("D")
VK_H = ord("H")
VK_S = ord("S")
VK_W = ord("W")
DEFAULT_TEST_CMDS_REQUEST = (
    Path(__file__).resolve().parents[2]
    / "omp-server-bare"
    / "scriptfiles"
    / "test_cmds_request.txt"
)
DEFAULT_TEST_CMDS_RESULTS = (
    Path(__file__).resolve().parents[2]
    / "omp-server-bare"
    / "scriptfiles"
    / "test_cmds_results.log"
)
DEFAULT_SYNC_PAIR_REQUEST = (
    Path(__file__).resolve().parents[2]
    / "omp-server-bare"
    / "scriptfiles"
    / "sync_pair_request.txt"
)
DEFAULT_SYNC_PAIR_RESULTS = (
    Path(__file__).resolve().parents[2]
    / "omp-server-bare"
    / "scriptfiles"
    / "sync_pair_results.log"
)


def sample(client: ControlClient, label: str, output: list[dict[str, Any]]) -> dict[str, Any]:
    state = client.command("state")
    state["label"] = label
    state["host_time"] = time.time()
    output.append(state)
    print(json.dumps(state, sort_keys=True))
    return state


def chat_command(client: ControlClient, command: str) -> None:
    client.command("char", code=ord("t"))
    time.sleep(0.35)
    # The original 0.3.7 chat input consumes WM_CHAR messages on the render
    # cadence.  Posting a complete command back-to-back can therefore leave
    # only the final characters in the edit buffer on slower probe runs.
    for character in command:
        client.command("char", code=ord(character))
        time.sleep(0.04)
    client.command("window_key", vk=VK_RETURN)


def hold_key(client: ControlClient, vk: int, seconds: float) -> None:
    client.key(vk, "down")
    try:
        time.sleep(seconds)
    finally:
        client.key(vk, "up")


def queue_sync_pair_scenario(
    scenario: str,
    request_path: Path,
    results_path: Path,
    timeout_seconds: float,
    output: list[dict[str, Any]],
) -> int:
    request_id = max(1, time.time_ns() % 2_000_000_000)
    request_path = request_path.resolve()
    results_path = results_path.resolve()
    temporary_path = request_path.with_name(f".{request_path.name}.{request_id}.tmp")
    if request_path.exists():
        raise RuntimeError(f"sync_pair request is already pending: {request_path}")

    result_offset = results_path.stat().st_size if results_path.exists() else 0
    request_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text(f"{request_id} {scenario}\n", encoding="utf-8")
    temporary_path.replace(request_path)
    queued = {
        "event": "sync_pair_scenario_queued",
        "scenario": scenario,
        "request_id": request_id,
        "request_path": str(request_path),
        "results_path": str(results_path),
        "host_time": time.time(),
    }
    output.append(queued)
    print(json.dumps(queued, sort_keys=True))

    deadline = time.monotonic() + timeout_seconds
    request_token = f" request={request_id} "
    while time.monotonic() < deadline:
        if results_path.exists():
            result_bytes = results_path.read_bytes()
            if len(result_bytes) < result_offset:
                result_offset = 0
            appended = result_bytes[result_offset:].decode("utf-8", errors="replace")
            for line in appended.splitlines():
                if request_token not in line:
                    continue
                if "marker=REQUEST_REJECTED " in line:
                    raise RuntimeError(
                        f"sync_pair rejected scenario {scenario!r}: {line}"
                    )
                if (
                    "marker=REQUEST_DONE " in line
                    and " status=PASS " in line
                    and f" scenario={scenario} " in line
                ):
                    acknowledged = {
                        "event": "sync_pair_scenario_acknowledged",
                        "scenario": scenario,
                        "request_id": request_id,
                        "result": line,
                        "host_time": time.time(),
                    }
                    output.append(acknowledged)
                    print(json.dumps(acknowledged, sort_keys=True))
                    return request_id
        time.sleep(0.05)

    raise TimeoutError(
        f"sync_pair did not acknowledge request {request_id} "
        f"for scenario {scenario!r} within {timeout_seconds:.1f}s"
    )


def drive_control_matrix(
    client: ControlClient,
    output: list[dict[str, Any]],
    action_seconds: float,
    sync_pair_request_path: Path,
    sync_pair_results_path: Path,
    sync_pair_request_timeout: float,
) -> None:
    client.command("focus")
    queue_sync_pair_scenario(
        "car",
        sync_pair_request_path,
        sync_pair_results_path,
        sync_pair_request_timeout,
        output,
    )
    time.sleep(1.0)
    sample(client, "controls_ready", output)

    for label, vk in (
        ("gas_w", VK_W),
        ("steer_left_a", VK_A),
        ("steer_right_d", VK_D),
        ("brake_reverse_s", VK_S),
        ("handbrake_space", VK_SPACE),
        ("horn_h", VK_H),
    ):
        hold_key(client, vk, action_seconds)
        time.sleep(0.8)
        sample(client, f"controls_after_{label}", output)


def capture_observer(label: str | None, count: int, interval: float) -> None:
    if not label:
        return
    lab = Path(__file__).resolve().parents[1] / "windows" / "remote_lab" / "samp_lab.sh"
    if count > 1:
        interval_ms = max(25, round(interval * 1000.0))
        subprocess.run(
            [str(lab), "screenshot-burst", label, str(count), str(interval_ms)],
            check=True,
        )
        return
    for index in range(count):
        capture_label = label if count == 1 else f"{label}_{index + 1:02d}"
        subprocess.run([str(lab), "screenshot", capture_label], check=True)
        if interval > 0.0 and index + 1 < count:
            time.sleep(interval)


def queue_active_aim_transition(
    transition: str,
    request_path: Path,
    results_path: Path,
    request_id: int,
    delay_ms: int,
    timeout_seconds: float,
    output: list[dict[str, Any]],
) -> None:
    group = "vehicle" if transition == "vehicle" else "player"
    request_path = request_path.resolve()
    results_path = results_path.resolve()
    temporary_path = request_path.with_name(f".{request_path.name}.{request_id}.tmp")
    if request_path.exists():
        raise RuntimeError(f"test_cmds request is already pending: {request_path}")
    result_offset = results_path.stat().st_size if results_path.exists() else 0
    request_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text(
        f"{request_id} {group} {delay_ms} 0 SyncPilot\n",
        encoding="utf-8",
    )
    temporary_path.replace(request_path)
    event = {
        "event": "active_aim_transition_queued",
        "transition": transition,
        "test_cmds_group": group,
        "request_id": request_id,
        "delay_ms": delay_ms,
        "request_path": str(request_path),
        "results_path": str(results_path),
        "host_time": time.time(),
    }
    output.append(event)
    print(json.dumps(event, sort_keys=True))

    deadline = time.monotonic() + timeout_seconds
    request_token = f" request={request_id} "
    while time.monotonic() < deadline:
        if results_path.exists():
            result_bytes = results_path.read_bytes()
            if len(result_bytes) < result_offset:
                result_offset = 0
            appended = result_bytes[result_offset:].decode("utf-8", errors="replace")
            for line in appended.splitlines():
                if request_token not in line:
                    continue
                if "marker=RUN_ABORT " in line:
                    raise RuntimeError(
                        f"test_cmds aborted active transition {transition!r}: {line}"
                    )
                if "marker=RUN_START " in line:
                    acknowledged = {
                        "event": "active_aim_transition_started",
                        "transition": transition,
                        "request_id": request_id,
                        "result": line,
                        "host_time": time.time(),
                    }
                    output.append(acknowledged)
                    print(json.dumps(acknowledged, sort_keys=True))
                    return
        time.sleep(0.05)

    raise TimeoutError(
        f"test_cmds did not start request {request_id} "
        f"for transition {transition!r} within {timeout_seconds:.1f}s"
    )


def drive_onfoot_weapon(
    client: ControlClient,
    scenario: str,
    output: list[dict[str, Any]],
    pre_action_seconds: float,
    action_seconds: float,
    observer_screenshot_label: str | None,
    observer_screenshot_count: int,
    observer_screenshot_interval: float,
    active_transition: str | None,
    test_cmds_request_path: Path,
    test_cmds_results_path: Path,
    transition_request_id: int,
    transition_delay_ms: int,
    transition_request_timeout: float,
    sync_pair_request_path: Path,
    sync_pair_results_path: Path,
    sync_pair_request_timeout: float,
) -> None:
    client.command("focus")
    queue_sync_pair_scenario(
        scenario,
        sync_pair_request_path,
        sync_pair_results_path,
        sync_pair_request_timeout,
        output,
    )
    time.sleep(1.0)
    ready = sample(client, f"{scenario}_ready", output)
    time.sleep(pre_action_seconds)

    center_x = max(10, int(ready.get("client_w", 800)) // 2)
    center_y = max(10, int(ready.get("client_h", 600)) // 2)
    client.command("mouse", action="move", x=center_x, y=center_y)
    client.command("mouse", action="right_down", x=center_x, y=center_y)
    try:
        time.sleep(1.0)
        if observer_screenshot_label:
            capture_observer(f"{observer_screenshot_label}_aim", 1, 0.0)

        client.command("mouse", action="left_down", x=center_x, y=center_y)
        try:
            action_started = time.monotonic()
            if active_transition:
                time.sleep(0.35)
                if active_transition == "streamout":
                    queue_sync_pair_scenario(
                        "streamout",
                        sync_pair_request_path,
                        sync_pair_results_path,
                        sync_pair_request_timeout,
                        output,
                    )
                else:
                    queue_active_aim_transition(
                        active_transition,
                        test_cmds_request_path,
                        test_cmds_results_path,
                        transition_request_id,
                        transition_delay_ms,
                        transition_request_timeout,
                        output,
                    )
            if observer_screenshot_label:
                capture_observer(
                    observer_screenshot_label,
                    observer_screenshot_count,
                    observer_screenshot_interval,
                )
            minimum_hold_seconds = max(action_seconds, 5.0 if active_transition else 0.0)
            remaining = minimum_hold_seconds - (time.monotonic() - action_started)
            if remaining > 0.0:
                time.sleep(remaining)
        finally:
            client.command("mouse", action="left_up", x=center_x, y=center_y)
        time.sleep(0.8)
    finally:
        client.command("mouse", action="right_up", x=center_x, y=center_y)

    time.sleep(1.0)
    sample(client, f"{scenario}_after_fire", output)


def drive_angle_sweep(
    client: ControlClient,
    output: list[dict[str, Any]],
    observer_screenshot_label: str | None,
    sync_pair_request_path: Path,
    sync_pair_results_path: Path,
    sync_pair_request_timeout: float,
) -> None:
    client.command("focus")
    queue_sync_pair_scenario(
        "m4",
        sync_pair_request_path,
        sync_pair_results_path,
        sync_pair_request_timeout,
        output,
    )
    time.sleep(1.0)
    ready = sample(client, "angles_ready", output)
    center_x = max(200, int(ready.get("client_w", 800)) // 2)
    center_y = max(100, int(ready.get("client_h", 600)) // 2)

    client.command("mouse", action="move", x=center_x, y=center_y)
    client.command("mouse", action="right_down", x=center_x, y=center_y)
    try:
        time.sleep(1.0)
        sample(client, "angles_aim_baseline", output)
        capture_observer(
            f"{observer_screenshot_label}_baseline"
            if observer_screenshot_label
            else None,
            1,
            0.0,
        )

        # PROBE_TRACE:
        # GTA recentres the cursor while mouse-look owns input. Repeated moves
        # to one side therefore provide deterministic yaw deltas without
        # depending on the host's physical mouse.
        for direction, offset in (("left", -140), ("right", 140)):
            for _ in range(20):
                client.command(
                    "mouse",
                    action="move",
                    x=center_x + offset,
                    y=center_y,
                )
                time.sleep(0.08)
            time.sleep(1.2)
            sample(client, f"angles_after_{direction}", output)
            capture_observer(
                f"{observer_screenshot_label}_{direction}"
                if observer_screenshot_label
                else None,
                1,
                0.0,
            )
    finally:
        client.command("mouse", action="right_up", x=center_x, y=center_y)

    time.sleep(1.0)
    sample(client, "angles_after_release", output)


def drive_scenario(
    client: ControlClient,
    scenario: str,
    output: list[dict[str, Any]],
    pre_action_seconds: float,
    action_seconds: float,
    observer_screenshot_label: str | None,
    observer_screenshot_count: int,
    observer_screenshot_interval: float,
    active_transition: str | None,
    test_cmds_request_path: Path,
    test_cmds_results_path: Path,
    transition_request_id: int,
    transition_delay_ms: int,
    transition_request_timeout: float,
    sync_pair_request_path: Path,
    sync_pair_results_path: Path,
    sync_pair_request_timeout: float,
) -> None:
    if scenario == "angles":
        drive_angle_sweep(
            client,
            output,
            observer_screenshot_label,
            sync_pair_request_path,
            sync_pair_results_path,
            sync_pair_request_timeout,
        )
        return

    if scenario == "controls":
        drive_control_matrix(
            client,
            output,
            action_seconds,
            sync_pair_request_path,
            sync_pair_results_path,
            sync_pair_request_timeout,
        )
        return

    if scenario in {"onfoot", "pistol", "m4", "sniper"}:
        drive_onfoot_weapon(
            client,
            scenario,
            output,
            pre_action_seconds,
            action_seconds,
            observer_screenshot_label,
            observer_screenshot_count,
            observer_screenshot_interval,
            active_transition,
            test_cmds_request_path,
            test_cmds_results_path,
            transition_request_id,
            transition_delay_ms,
            transition_request_timeout,
            sync_pair_request_path,
            sync_pair_results_path,
            sync_pair_request_timeout,
        )
        return

    client.command("focus")
    queue_sync_pair_scenario(
        scenario,
        sync_pair_request_path,
        sync_pair_results_path,
        sync_pair_request_timeout,
        output,
    )
    time.sleep(1.0)
    sample(client, f"{scenario}_ready", output)
    time.sleep(pre_action_seconds)

    if scenario == "car":
        client.key(VK_W, "down")
        try:
            capture_observer(
                observer_screenshot_label,
                observer_screenshot_count,
                observer_screenshot_interval,
            )
            time.sleep(action_seconds)
        finally:
            client.key(VK_W, "up")
        hold_key(client, VK_A, 1.0)
        hold_key(client, VK_S, 0.8)
        time.sleep(1.0)
        sample(client, "car_after_drive", output)
    elif scenario == "rustler":
        client.key(VK_CONTROL, "down")
        try:
            capture_observer(
                observer_screenshot_label,
                observer_screenshot_count,
                observer_screenshot_interval,
            )
            time.sleep(action_seconds)
        finally:
            client.key(VK_CONTROL, "up")
        time.sleep(1.0)
        sample(client, "rustler_after_fire", output)
    elif scenario == "jetpack":
        client.key(VK_W, "down")
        client.key(VK_SPACE, "down")
        try:
            capture_observer(
                observer_screenshot_label,
                observer_screenshot_count,
                observer_screenshot_interval,
            )
            time.sleep(action_seconds)
        finally:
            client.key(VK_SPACE, "up")
            client.key(VK_W, "up")
        time.sleep(1.0)
        sample(client, "jetpack_after_flight", output)
    elif scenario == "pickup":
        capture_observer(
            observer_screenshot_label,
            observer_screenshot_count,
            observer_screenshot_interval,
        )
        time.sleep(max(action_seconds, 1.0))
        sample(client, "pickup_after_collect", output)
    elif scenario == "death":
        capture_observer(
            observer_screenshot_label,
            observer_screenshot_count,
            observer_screenshot_interval,
        )
        time.sleep(max(action_seconds, 6.0))
        sample(client, "death_after_respawn_window", output)
    else:
        raise ValueError(f"unsupported scenario: {scenario}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario",
        choices=[
            "onfoot",
            "pistol",
            "m4",
            "sniper",
            "combat",
            "car",
            "rustler",
            "jetpack",
            "pickup",
            "death",
            "controls",
            "angles",
            "all",
        ],
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--between", type=float, default=2.0)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--pre-action-seconds", type=float, default=0.0)
    parser.add_argument("--action-seconds", type=float, default=2.5)
    parser.add_argument("--observer-screenshot-label")
    parser.add_argument("--observer-screenshot-count", type=int, default=1)
    parser.add_argument("--observer-screenshot-interval", type=float, default=0.15)
    parser.add_argument(
        "--active-transition",
        choices=["vehicle", "streamout"],
        help="queue an asynchronous server transition while RMB/LMB remain held",
    )
    parser.add_argument(
        "--test-cmds-request-path",
        type=Path,
        default=DEFAULT_TEST_CMDS_REQUEST,
    )
    parser.add_argument(
        "--test-cmds-results-path",
        type=Path,
        default=DEFAULT_TEST_CMDS_RESULTS,
    )
    parser.add_argument("--transition-request-timeout", type=float, default=10.0)
    parser.add_argument(
        "--sync-pair-request-path",
        type=Path,
        default=DEFAULT_SYNC_PAIR_REQUEST,
    )
    parser.add_argument(
        "--sync-pair-results-path",
        type=Path,
        default=DEFAULT_SYNC_PAIR_RESULTS,
    )
    parser.add_argument("--sync-pair-request-timeout", type=float, default=10.0)
    parser.add_argument("--transition-request-id", type=int)
    parser.add_argument("--transition-delay-ms", type=int, default=250)
    args = parser.parse_args()
    if args.observer_screenshot_count < 1:
        parser.error("--observer-screenshot-count must be at least 1")
    if args.observer_screenshot_interval < 0.0:
        parser.error("--observer-screenshot-interval must not be negative")
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")
    if args.sync_pair_request_timeout <= 0.0:
        parser.error("--sync-pair-request-timeout must be positive")
    if args.transition_request_timeout <= 0.0:
        parser.error("--transition-request-timeout must be positive")
    if not 250 <= args.transition_delay_ms <= 10000:
        parser.error("--transition-delay-ms must be in the fixture range 250..10000")
    if args.transition_request_id is not None and args.transition_request_id < 1:
        parser.error("--transition-request-id must be positive")
    if args.active_transition and (
        args.scenario not in {"onfoot", "pistol", "m4", "sniper"}
        or args.repetitions != 1
    ):
        parser.error(
            "--active-transition requires one onfoot/pistol/m4/sniper scenario"
        )

    if args.scenario == "all":
        scenarios = ["onfoot", "car", "rustler", "jetpack", "pickup", "death"]
    elif args.scenario == "combat":
        scenarios = ["pistol", "m4", "sniper"]
    else:
        scenarios = [args.scenario]
    output: list[dict[str, Any]] = []
    client = wait_for_api()
    transition_request_id = args.transition_request_id
    if transition_request_id is None:
        transition_request_id = max(
            1, int(time.time() * 1000.0) % 2_000_000_000
        )
    try:
        run_index = 0
        for scenario in scenarios:
            for repetition in range(1, args.repetitions + 1):
                if run_index:
                    time.sleep(args.between)
                screenshot_label = args.observer_screenshot_label
                if screenshot_label and (len(scenarios) > 1 or args.repetitions > 1):
                    screenshot_label = f"{screenshot_label}_{scenario}_r{repetition:02d}"
                drive_scenario(
                    client,
                    scenario,
                    output,
                    args.pre_action_seconds,
                    args.action_seconds,
                    screenshot_label,
                    args.observer_screenshot_count,
                    args.observer_screenshot_interval,
                    args.active_transition,
                    args.test_cmds_request_path,
                    args.test_cmds_results_path,
                    transition_request_id,
                    args.transition_delay_ms,
                    args.transition_request_timeout,
                    args.sync_pair_request_path,
                    args.sync_pair_results_path,
                    args.sync_pair_request_timeout,
                )
                run_index += 1
        queue_sync_pair_scenario(
            "stop",
            args.sync_pair_request_path,
            args.sync_pair_results_path,
            args.sync_pair_request_timeout,
            output,
        )
    finally:
        for vk in (VK_CONTROL, VK_SPACE, VK_W, VK_A, VK_D, VK_S, VK_H):
            try:
                client.key(vk, "up")
            except (OSError, RuntimeError):
                pass
        try:
            client.command("mouse", action="left_up", x=0, y=0)
            client.command("mouse", action="right_up", x=0, y=0)
        except (OSError, RuntimeError):
            pass
        client.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
