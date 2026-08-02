#!/usr/bin/env python3
"""Drive the SyncPilot side of the deterministic two-client fixture."""

from __future__ import annotations

import argparse
import json
import math
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
VK_G = ord("G")
VK_H = ord("H")
VK_S = ord("S")
VK_W = ord("W")
ANGLE_SWEEP_TARGET_DEGREES = 35.0
ANGLE_SWEEP_TOLERANCE_DEGREES = 2.0
ANGLE_SWEEP_MOUSE_PULSE_X = 6
ANGLE_SWEEP_PULSE_SECONDS = 0.08
ANGLE_SWEEP_NETWORK_SETTLE_SECONDS = 0.6
ANGLE_SWEEP_MAX_PULSES = 120
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
    edge_setup_required = scenario in {
        "passenger",
        "passenger_g",
        "unoccupied",
        "trailer",
    }
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
                    edge_setup_required
                    and "marker=EDGE_SETUP " in line
                    and f" scenario={scenario} " in line
                ):
                    if " status=FAIL " in line:
                        raise RuntimeError(
                            f"sync_pair failed edge setup {scenario!r}: {line}"
                        )
                    if " status=PASS " in line:
                        acknowledged = {
                            "event": "sync_pair_edge_setup_acknowledged",
                            "scenario": scenario,
                            "request_id": request_id,
                            "result": line,
                            "host_time": time.time(),
                        }
                        output.append(acknowledged)
                        print(json.dumps(acknowledged, sort_keys=True))
                        return request_id
                if (
                    "marker=REQUEST_DONE " in line
                    and " status=PASS " in line
                    and f" scenario={scenario} " in line
                ):
                    if edge_setup_required:
                        continue
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


def wait_for_sync_pair_result(
    marker: str,
    scenario: str,
    request_id: int,
    results_path: Path,
    timeout_seconds: float,
    output: list[dict[str, Any]],
) -> str:
    """Wait for one request-scoped PASS/FAIL result emitted after host input."""
    deadline = time.monotonic() + timeout_seconds
    request_token = f" request={request_id} "
    marker_token = f"marker={marker} "
    while time.monotonic() < deadline:
        if results_path.exists():
            text = results_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if (
                    request_token not in line
                    or marker_token not in line
                    or f" scenario={scenario} " not in line
                ):
                    continue
                if " status=FAIL " in line:
                    raise RuntimeError(
                        f"sync_pair failed {scenario!r} after host input: {line}"
                    )
                if " status=PASS " in line:
                    completed = {
                        "event": "sync_pair_input_result_acknowledged",
                        "marker": marker,
                        "scenario": scenario,
                        "request_id": request_id,
                        "result": line,
                        "host_time": time.time(),
                    }
                    output.append(completed)
                    print(json.dumps(completed, sort_keys=True))
                    return line
        time.sleep(0.05)

    raise TimeoutError(
        f"sync_pair did not emit {marker} for request {request_id} "
        f"and scenario {scenario!r} within {timeout_seconds:.1f}s"
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
    edge_stream_wakeup = scenario in {"passenger", "unoccupied", "trailer"}
    if edge_stream_wakeup:
        # PROBE_TRACE:
        # In repeated two-prefix runs the unfocused original pilot could be
        # mutually player-streamed while sending no OnPlayerUpdate during a
        # newly created vehicle's stream-in window. Keep one ordinary movement
        # key active until the server verifies the physical edge setup.
        client.key(VK_W, "down")
    try:
        queue_sync_pair_scenario(
            scenario,
            sync_pair_request_path,
            sync_pair_results_path,
            sync_pair_request_timeout,
            output,
        )
    finally:
        if edge_stream_wakeup:
            client.key(VK_W, "up")
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


def vector_heading_degrees(x: float, y: float, label: str) -> float:
    if not math.isfinite(x) or not math.isfinite(y) or math.hypot(x, y) < 0.05:
        raise RuntimeError(f"{label} is unavailable or degenerate: ({x!r}, {y!r})")
    return math.degrees(math.atan2(y, x)) % 360.0


def signed_angle_delta_degrees(angle: float, baseline: float) -> float:
    return (angle - baseline + 180.0) % 360.0 - 180.0


def aim_heading_degrees(state: dict[str, Any]) -> float:
    try:
        front_x = float(state["aim_front_x"])
        front_y = float(state["aim_front_y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "reloop_control state lacks CCamera::InternalAim front-vector fields; "
            "deploy the current control ASI before running angles"
        ) from exc
    return vector_heading_degrees(front_x, front_y, "aim front")


def annotate_angle_state(
    state: dict[str, Any],
    baseline_heading: float,
    mouse_pulses: int,
) -> None:
    heading = aim_heading_degrees(state)
    state["aim_heading_degrees"] = heading
    state["aim_delta_from_baseline_degrees"] = signed_angle_delta_degrees(
        heading,
        baseline_heading,
    )
    state["relative_mouse_pulses"] = mouse_pulses
    try:
        state["player_heading_degrees"] = vector_heading_degrees(
            float(state["player_forward_x"]),
            float(state["player_forward_y"]),
            "player forward",
        )
    except (KeyError, TypeError, ValueError, RuntimeError):
        state["player_heading_degrees"] = None


def calibrate_left_aim_sign(
    client: ControlClient,
    baseline_heading: float,
    output: list[dict[str, Any]],
) -> tuple[int, int]:
    """Return the world-heading sign produced by a physical left mouse pulse."""
    for pulse_count in range(1, 13):
        client.command(
            "mouse",
            action="move_delta",
            x=-ANGLE_SWEEP_MOUSE_PULSE_X,
            y=0,
        )
        time.sleep(ANGLE_SWEEP_PULSE_SECONDS)
        state = client.command("state")
        delta = signed_angle_delta_degrees(
            aim_heading_degrees(state),
            baseline_heading,
        )
        if abs(delta) >= 0.5:
            event = {
                "event": "angles_relative_input_calibrated",
                "mouse_delta_x": -ANGLE_SWEEP_MOUSE_PULSE_X,
                "pulses": pulse_count,
                "observed_heading_delta_degrees": delta,
                "left_heading_sign": 1 if delta > 0.0 else -1,
                "host_time": time.time(),
            }
            output.append(event)
            print(json.dumps(event, sort_keys=True))
            return event["left_heading_sign"], pulse_count
    raise RuntimeError(
        "relative mouse input did not change CCamera::InternalAim after 12 "
        "bounded pulses; angles trace would not be valid"
    )


def drive_aim_to_relative_target(
    client: ControlClient,
    output: list[dict[str, Any]],
    label: str,
    baseline_heading: float,
    target_sign: int,
    mouse_delta_x: int,
    initial_pulses: int = 0,
) -> dict[str, Any]:
    """Drive to a measured relative heading and reject stalled input."""
    best_progress = -181.0
    stale_pulses = 0
    pulse_count = initial_pulses
    for _ in range(ANGLE_SWEEP_MAX_PULSES + 1):
        state = client.command("state")
        heading = aim_heading_degrees(state)
        delta = signed_angle_delta_degrees(heading, baseline_heading)
        progress = delta * target_sign
        if progress >= (
            ANGLE_SWEEP_TARGET_DEGREES - ANGLE_SWEEP_TOLERANCE_DEGREES
        ):
            # Let at least several normal aim-sync intervals reach the observer
            # before its screenshot is requested, then prove the local heading
            # did not fall back during that window.
            time.sleep(ANGLE_SWEEP_NETWORK_SETTLE_SECONDS)
            state = client.command("state")
            heading = aim_heading_degrees(state)
            delta = signed_angle_delta_degrees(heading, baseline_heading)
            if delta * target_sign < (
                ANGLE_SWEEP_TARGET_DEGREES
                - ANGLE_SWEEP_TOLERANCE_DEGREES
            ):
                raise RuntimeError(
                    f"aim heading fell back before observer capture for {label}: "
                    f"delta={delta:.3f}"
                )
            state["label"] = label
            state["host_time"] = time.time()
            annotate_angle_state(state, baseline_heading, pulse_count)
            output.append(state)
            print(json.dumps(state, sort_keys=True))
            return state

        if progress > best_progress + 0.1:
            best_progress = progress
            stale_pulses = 0
        else:
            stale_pulses += 1
            if stale_pulses >= 16:
                raise RuntimeError(
                    f"relative mouse input stalled before {label}: "
                    f"best_progress={best_progress:.3f} "
                    f"target={ANGLE_SWEEP_TARGET_DEGREES:.3f}"
                )

        client.command(
            "mouse",
            action="move_delta",
            x=mouse_delta_x,
            y=0,
        )
        pulse_count += 1
        time.sleep(ANGLE_SWEEP_PULSE_SECONDS)

    raise RuntimeError(
        f"relative mouse input did not reach {label} within "
        f"{ANGLE_SWEEP_MAX_PULSES} pulses"
    )


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
        baseline = sample(client, "angles_aim_baseline", output)
        baseline_heading = aim_heading_degrees(baseline)
        annotate_angle_state(baseline, baseline_heading, 0)
        capture_observer(
            f"{observer_screenshot_label}_baseline"
            if observer_screenshot_label
            else None,
            1,
            0.0,
        )

        # PROBE_TRACE:
        # Runs 20260728-aim-{original,replacement}-observer-manual proved that
        # absolute SetCursorPos/WM_MOUSEMOVE changed cursor_x but left the
        # sampled CCamera::InternalAim camera position unchanged. Use bounded
        # relative SendInput pulses and stop on the measured front vector, so
        # frame-rate/input coalescing cannot silently turn the angle comparison
        # into two identical frames.
        left_heading_sign, calibration_pulses = calibrate_left_aim_sign(
            client,
            baseline_heading,
            output,
        )
        for direction, target_sign, mouse_delta_x, initial_pulses in (
            (
                "left",
                left_heading_sign,
                -ANGLE_SWEEP_MOUSE_PULSE_X,
                calibration_pulses,
            ),
            (
                "right",
                -left_heading_sign,
                ANGLE_SWEEP_MOUSE_PULSE_X,
                0,
            ),
        ):
            drive_aim_to_relative_target(
                client,
                output,
                f"angles_after_{direction}",
                baseline_heading,
                target_sign,
                mouse_delta_x,
                initial_pulses,
            )
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
    steer_during_capture: str | None,
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
    request_id = queue_sync_pair_scenario(
        scenario,
        sync_pair_request_path,
        sync_pair_results_path,
        sync_pair_request_timeout,
        output,
    )
    time.sleep(1.0)
    sample(client, f"{scenario}_ready", output)
    time.sleep(pre_action_seconds)

    if scenario in {"car", "trailer"}:
        steering_key = {
            "left": VK_A,
            "right": VK_D,
        }.get(steer_during_capture)
        client.key(VK_W, "down")
        if steering_key is not None:
            client.key(steering_key, "down")
        try:
            capture_observer(
                observer_screenshot_label,
                observer_screenshot_count,
                observer_screenshot_interval,
            )
            time.sleep(action_seconds)
        finally:
            if steering_key is not None:
                client.key(steering_key, "up")
            client.key(VK_W, "up")
        hold_key(client, VK_A, 1.0)
        hold_key(client, VK_S, 0.8)
        time.sleep(1.0)
        sample(client, f"{scenario}_after_drive", output)
    elif scenario in {"passenger", "unoccupied"}:
        capture_observer(
            observer_screenshot_label,
            observer_screenshot_count,
            observer_screenshot_interval,
        )
        time.sleep(max(action_seconds, 1.0))
        sample(client, f"{scenario}_after_sync", output)
    elif scenario == "passenger_g":
        # STATIC_037:
        # R5 consumes the passenger control on its first pressed frame and
        # immediately sends RPC 26. Keep VK_G down across several render/input
        # frames without turning this into a long held-key scenario.
        hold_key(client, VK_G, 0.15)
        wait_for_sync_pair_result(
            "PASSENGER_ENTRY_RESULT",
            scenario,
            request_id,
            sync_pair_results_path,
            sync_pair_request_timeout,
            output,
        )
        capture_observer(
            observer_screenshot_label,
            observer_screenshot_count,
            observer_screenshot_interval,
        )
        time.sleep(max(action_seconds, 1.0))
        sample(client, "passenger_g_after_sync", output)
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
            "passenger",
            "passenger_g",
            "unoccupied",
            "trailer",
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
        "--steer-during-capture",
        choices=["left", "right"],
        help=(
            "hold steering together with throttle during car/trailer screenshot "
            "capture so articulated motion remains in the recorded window"
        ),
    )
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
        scenarios = [
            "onfoot",
            "car",
            "rustler",
            "passenger",
            "unoccupied",
            "trailer",
            "jetpack",
            "pickup",
            "death",
        ]
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
                    args.steer_during_capture,
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
    finally:
        for vk in (VK_CONTROL, VK_SPACE, VK_W, VK_A, VK_D, VK_G, VK_S, VK_H):
            try:
                client.key(vk, "up")
            except (OSError, RuntimeError):
                pass
        try:
            client.command("mouse", action="left_up", x=0, y=0)
            client.command("mouse", action="right_up", x=0, y=0)
        except (OSError, RuntimeError):
            pass
        try:
            queue_sync_pair_scenario(
                "stop",
                args.sync_pair_request_path,
                args.sync_pair_results_path,
                args.sync_pair_request_timeout,
                output,
            )
        except (OSError, RuntimeError, TimeoutError) as exc:
            cleanup = {
                "event": "sync_pair_stop_request_failed",
                "error": str(exc),
                "fallback": "chat_command",
                "host_time": time.time(),
            }
            output.append(cleanup)
            print(json.dumps(cleanup, sort_keys=True))
            try:
                chat_command(client, "/syncpair stop")
            except (OSError, RuntimeError) as fallback_exc:
                cleanup["fallback_error"] = str(fallback_exc)
        client.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
