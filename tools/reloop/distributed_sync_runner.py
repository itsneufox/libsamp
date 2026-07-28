#!/usr/bin/env python3
"""Coordinate focused sync_pair scenarios across host Original R5 and Windows.

The default topology is:

    local Original R5 SyncPilot + native-Windows SyncObserver

For death and GMX state-machine probes, ``--windows-role=pilot`` reverses the
roles so the native-Windows client receives the transition. Windows deployment
and probe-profile changes are opt-in only. Successful automation produces
trace and screenshot artifacts; it never asserts visual parity.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import reloop  # noqa: E402
import lifecycle_probe  # noqa: E402
import sync_edge_probe  # noqa: E402
import sync_pair_client  # noqa: E402
import windows_sync_edge_probe as windows_edge  # noqa: E402
from control_client import wait_for_api  # noqa: E402


SCENARIOS = ("pistol", "m4", "sniper", "angles", "jetpack", "death", "pickup")
GMX_SCENARIO = "gmx"
UI_LATCH_SCENARIO = "ui_latches"
WINDOWS_ROLES = ("observer", "pilot")
WEAPON_IDS = {"pistol": 22, "m4": 31, "sniper": 34}
UI_LATCH_ACTIONS = (
    # STATIC_037: WndProc toggles the scoreboard on WM_KEYUP at
    # samp.dll+0x61785..+0x617B6. Two complete key pulses are therefore
    # required to observe one show edge followed by one hide edge.
    ("tab_show_keyup", "TAB"),
    ("tab_hide_keyup", "TAB"),
    ("chat_open_edge", "F6"),
    ("chat_close_edge", "F6"),
    ("chat_mode_edge_1", "F7"),
    ("chat_mode_edge_2", "F7"),
    ("chat_mode_edge_3", "F7"),
)
ORIGINAL_R5_SHA256 = windows_edge.ORIGINAL_R5_SHA256
AUTOPAUSE_INI = sync_edge_probe.AUTOPAUSE_INI
CONTROL_PORT = sync_edge_probe.CONTROL_PORT
LAB_WRAPPER = windows_edge.LAB_WRAPPER
SAFE_HOST = windows_edge.SAFE_HOST
CRASH_MARKERS = sync_edge_probe.CRASH_MARKERS
PROBE_PROFILE_FLAGS: dict[str, tuple[str, ...]] = {
    "passive": (),
    "no-hooks": ("samp_probe_no_hooks.flag",),
    "asset-paths": ("samp_probe_asset_paths.flag",),
    "custom-object-heavy": ("samp_probe_custom_object_heavy.flag",),
    "textdraw": ("samp_probe_textdraw_hooks.flag",),
    "textdraw-verbose": (
        "samp_probe_textdraw_hooks.flag",
        "samp_probe_textdraw_verbose.flag",
    ),
    "textdraw-render": ("samp_probe_textdraw_render.flag",),
    "font5": ("samp_probe_font5_hooks.flag",),
    "actor": ("samp_probe_actor_hooks.flag",),
    "actor-heavy": ("samp_probe_actor_heavy.flag",),
    "rpc-gap": ("samp_probe_rpc_gap_hooks.flag",),
    "dialog-menu": ("samp_probe_dialog_menu_rpc_hooks.flag",),
    "trailer-r5": (
        "samp_probe_trailer_sync_hooks.flag",
        "samp_probe_trailer_physics_hooks.flag",
    ),
    "vehicle-lifecycle": ("samp_probe_vehicle_lifecycle_hooks.flag",),
    "aim-bullet-jetpack": ("samp_probe_aim_bullet_jetpack_hooks.flag",),
    "death-cleanup": ("samp_probe_death_cleanup_hooks.flag",),
    "ui-latches-r5": ("samp_probe_ui_latches_hooks.flag",),
}


class DistributedSyncError(RuntimeError):
    """Expected operator-facing distributed runner failure."""


def validate_role_scenario(windows_role: str, scenario: str) -> None:
    """Keep the reversed topology limited to Windows state-machine probes."""
    if windows_role not in WINDOWS_ROLES:
        raise DistributedSyncError(f"unsupported Windows role: {windows_role}")
    if windows_role == "pilot" and scenario not in (
        "death",
        GMX_SCENARIO,
        UI_LATCH_SCENARIO,
    ):
        raise DistributedSyncError(
            "--windows-role=pilot is only supported with "
            "--scenario=death, --scenario=gmx, or --scenario=ui_latches"
        )
    if (
        scenario in (GMX_SCENARIO, UI_LATCH_SCENARIO)
        and windows_role != "pilot"
    ):
        raise DistributedSyncError(
            f"--scenario={scenario} requires --windows-role=pilot"
        )


def validate_death_f4(
    death_f4: bool,
    windows_role: str,
    scenario: str,
) -> None:
    if death_f4 and not (windows_role == "pilot" and scenario == "death"):
        raise DistributedSyncError(
            "--death-f4 requires --scenario=death and --windows-role=pilot"
        )


def validate_ui_latch_profile(scenario: str, probe_profile: str | None) -> None:
    if scenario == UI_LATCH_SCENARIO and probe_profile != "ui-latches-r5":
        raise DistributedSyncError(
            "--scenario=ui_latches requires "
            "--windows-probe-profile=ui-latches-r5"
        )


def topology_for_role(windows_role: str) -> str:
    if windows_role == "pilot":
        return "native_windows_pilot+local_original_r5_observer"
    return "local_original_r5_pilot+native_windows_observer"


def optional_sha256(path: Path) -> str | None:
    return reloop.sha256(path) if path.is_file() else None


def expand_scenarios(value: str) -> list[str]:
    if value == "all":
        return list(SCENARIOS)
    if value in (GMX_SCENARIO, UI_LATCH_SCENARIO):
        return [value]
    if value not in SCENARIOS:
        raise DistributedSyncError(f"unsupported distributed scenario: {value}")
    return [value]


def _find(value: Any, key: str) -> Any | None:
    return windows_edge._find_key(value, key)


def parse_windows_preflight(text: str) -> dict[str, Any]:
    """Extract the read-only lab state returned by the interactive agent."""
    value = windows_edge._json_value(text)
    if value is None:
        raise DistributedSyncError("Windows ping returned no JSON state")
    processes = _find(value, "processes")
    autopause = _find(value, "autopause")
    probe_flags = _find(value, "probe_flags")
    state = {
        "processes": processes,
        "game_dir": _find(value, "game_dir"),
        "gta_sha256": _find(value, "gta_sha256"),
        "samp_sha256": _find(value, "samp_sha256"),
        "samp_probe_sha256": _find(value, "samp_probe_sha256"),
        "reloop_control_sha256": _find(value, "reloop_control_sha256"),
        "autopause": autopause,
        "probe_flags": probe_flags,
    }
    if not isinstance(processes, list):
        raise DistributedSyncError(
            "Windows ping did not expose an authoritative process inventory"
        )
    if not isinstance(autopause, dict) or autopause.get("disabled") is not True:
        path = autopause.get("path") if isinstance(autopause, dict) else None
        observed = autopause.get("value") if isinstance(autopause, dict) else None
        raise DistributedSyncError(
            "Windows requires [game] autoPause = 0 in "
            f"{path or AUTOPAUSE_INI}; observed value={observed!r}"
        )
    if not isinstance(probe_flags, list) or not all(
        isinstance(item, str) for item in probe_flags
    ):
        raise DistributedSyncError("Windows ping did not expose probe flag state")
    for key in ("gta_sha256", "samp_sha256"):
        if not isinstance(state[key], str) or len(state[key]) != 64:
            raise DistributedSyncError(f"Windows ping returned no valid {key}")
    return state


def validate_windows_idle(state: dict[str, Any]) -> None:
    processes = state.get("processes")
    if not isinstance(processes, list) or processes:
        raise DistributedSyncError(
            f"Windows GTA/SA-MP is not idle: processes={processes!r}"
        )


def expected_profile_flags(profile: str | None) -> tuple[str, ...] | None:
    if profile is None:
        return None
    try:
        return PROBE_PROFILE_FLAGS[profile]
    except KeyError as error:
        raise DistributedSyncError(
            f"unsupported managed probe profile: {profile}"
        ) from error


def validate_probe_state(
    state: dict[str, Any],
    requested_profile: str | None,
) -> None:
    active = tuple(sorted(state.get("probe_flags", [])))
    expected = expected_profile_flags(requested_profile)
    if expected is None:
        if active:
            raise DistributedSyncError(
                "Windows has unmanaged probe flags active; either clear them "
                "manually or explicitly request --windows-probe-profile passive: "
                f"{list(active)}"
            )
        return
    if active != tuple(sorted(expected)):
        raise DistributedSyncError(
            f"Windows probe profile mismatch: expected={sorted(expected)} "
            f"active={list(active)}"
        )
    if expected and not state.get("samp_probe_sha256"):
        raise DistributedSyncError(
            f"probe profile {requested_profile!r} requires samp_probe.asi"
        )


def verify_profile_receipt(text: str, requested_profile: str) -> dict[str, Any]:
    value = windows_edge._json_value(text)
    if value is None:
        raise DistributedSyncError("probe-profile command returned no JSON")
    profile = _find(value, "profile")
    enabled = _find(value, "enabled")
    expected = sorted(expected_profile_flags(requested_profile) or ())
    if profile != requested_profile or not isinstance(enabled, list):
        raise DistributedSyncError(
            f"probe-profile receipt is incomplete for {requested_profile!r}"
        )
    if sorted(enabled) != expected:
        raise DistributedSyncError(
            f"probe-profile receipt mismatch: expected={expected} enabled={enabled}"
        )
    return {
        "profile": profile,
        "enabled": enabled,
        "probe_sha256": _find(value, "probe_sha256"),
    }


def verify_deploy_receipt(
    text: str,
    candidate: dict[str, Any],
    *,
    kind: str,
) -> dict[str, Any]:
    value = windows_edge._json_value(text)
    if value is None:
        raise DistributedSyncError(f"Windows {kind} deployment returned no JSON")
    installed_hash = _find(value, "target_sha256_after")
    if installed_hash != candidate["sha256"]:
        raise DistributedSyncError(
            f"Windows {kind} deployment hash mismatch: "
            f"candidate={candidate['sha256']} installed={installed_hash}"
        )
    return {
        "candidate_sha256": candidate["sha256"],
        "installed_sha256": installed_hash,
        "backup": _find(value, "backup"),
    }


def windows_mutation_plan(
    dll_candidate: dict[str, Any] | None,
    probe_candidate: dict[str, Any] | None,
    probe_profile: str | None,
    label: str,
) -> list[tuple[str, list[str]]]:
    """Return only explicitly requested Windows mutations."""
    actions: list[tuple[str, list[str]]] = []
    if dll_candidate is not None:
        path = str(dll_candidate["path"])
        actions.extend(
            (
                ("dll-validate", ["validate", path]),
                ("dll-deploy", ["deploy", path, label]),
            )
        )
    if probe_candidate is not None:
        actions.append(
            (
                "probe-deploy",
                ["deploy-probe", str(probe_candidate["path"]), label],
            )
        )
    if probe_profile is not None:
        actions.append(
            ("probe-profile", ["probe-profile", probe_profile])
        )
    return actions


def validate_local_layout(
    settings: reloop.Settings,
    local_client: reloop.ClientProfile,
    windows_role: str = "observer",
) -> dict[str, Any]:
    layout = windows_edge.validate_layout(settings, local_client, windows_role)
    if reloop.sha256(local_client.samp_dll) != ORIGINAL_R5_SHA256:
        raise DistributedSyncError(
            "local Original client is not the documented Original R5"
        )
    installed_control = local_client.gta_root / reloop.CONTROL_ASI.name
    if windows_role == "observer" and not installed_control.is_file():
        raise DistributedSyncError(
            f"local Original pilot control ASI is missing: {installed_control}"
        )
    return {
        **layout,
        "topology": topology_for_role(windows_role),
        "local_control_path": str(installed_control),
        "local_control_sha256": (
            reloop.sha256(installed_control) if installed_control.is_file() else None
        ),
        "local_control_required": windows_role == "observer",
    }


def run_driver(
    scenario: str,
    artifact_dir: Path,
    *,
    fixture_timeout: float,
    action_seconds: float,
    screenshot_count: int,
    screenshot_interval: float,
) -> int:
    """Reuse sync_pair_client without importing any scenario implementation."""
    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    label = f"dist-sync-{scenario}-{int(time.time())}"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "sync_pair_client.py"),
        scenario,
        "--output",
        str(output_path),
        "--action-seconds",
        str(action_seconds),
        "--observer-screenshot-label",
        label,
        "--observer-screenshot-count",
        str(screenshot_count),
        "--observer-screenshot-interval",
        str(screenshot_interval),
        "--sync-pair-request-timeout",
        str(fixture_timeout),
    ]
    capture_seconds = screenshot_count * max(0.025, screenshot_interval)
    with console_path.open("wb") as handle:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=fixture_timeout + action_seconds + capture_seconds + 60.0,
            check=False,
        )
    return completed.returncode


def wait_for_death_event(
    server_log: Path,
    start_offset: int,
    request_id: int,
    timeout_seconds: float,
    output: list[dict[str, Any]],
) -> str:
    """Wait for the client-originated death callback in this request block."""
    deadline = time.monotonic() + timeout_seconds
    request_token = f"request={request_id} "
    while time.monotonic() < deadline:
        if server_log.exists():
            data = server_log.read_bytes()
            if len(data) < start_offset:
                start_offset = 0
            appended = data[start_offset:].decode("utf-8", errors="replace")
            request_seen = (
                "marker=SCENARIO_START" in appended
                and request_token in appended
                and "scenario=death " in appended
            )
            death_line = next(
                (
                    line
                    for line in appended.splitlines()
                    if "marker=PLAYER_DEATH " in line
                ),
                None,
            )
            if request_seen and death_line is not None:
                event = {
                    "event": "windows_pilot_death_observed",
                    "scenario": "death",
                    "request_id": request_id,
                    "result": death_line,
                    "host_time": time.time(),
                }
                output.append(event)
                print(json.dumps(event, sort_keys=True))
                return death_line
        time.sleep(0.05)
    raise TimeoutError(
        f"sync_pair emitted no PLAYER_DEATH for request {request_id} "
        f"within {timeout_seconds:.1f}s"
    )


def run_windows_death_driver(
    artifact_dir: Path,
    *,
    request_path: Path,
    results_path: Path,
    server_log: Path,
    fixture_timeout: float,
    screenshot_count: int,
    screenshot_interval: float,
    death_f4: bool = False,
    lab_timeout: float = 45.0,
) -> int:
    """Capture the Windows SyncPilot while the host queues its death."""
    scenario = "death"
    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    returncode = 0
    screenshot_label = f"dist-sync-death-pilot-{int(time.time())}"
    start_offset = server_log.stat().st_size if server_log.exists() else 0

    with console_path.open("w", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                if death_f4:
                    f4_started = time.time()
                    requested = {
                        "event": "windows_pilot_death_f4_requested",
                        "scenario": scenario,
                        "input_action": "CLASS",
                        "phase": "before_death_request",
                        "host_time": f4_started,
                    }
                    output.append(requested)
                    print(json.dumps(requested, sort_keys=True))
                    windows_edge.run_lab(
                        artifact_dir,
                        "pilot-death-f4",
                        [
                            "key",
                            "CLASS",
                            f"dist-sync-death-f4-{int(f4_started)}",
                        ],
                        timeout=lab_timeout,
                    )
                    # Preserve a visible, timestamped edge between the F4
                    # latch and the server-side SetPlayerHealth(0) request.
                    f4_settle_seconds = 0.75
                    time.sleep(f4_settle_seconds)
                    completed = {
                        "event": "windows_pilot_death_f4_completed",
                        "scenario": scenario,
                        "input_action": "CLASS",
                        "phase": "before_death_request",
                        "started_host_time": f4_started,
                        "completed_host_time": time.time(),
                        "settle_seconds": f4_settle_seconds,
                    }
                    output.append(completed)
                    print(json.dumps(completed, sort_keys=True))
                sync_pair_client.capture_observer(
                    f"{screenshot_label}-before",
                    1,
                    0.0,
                )
                # Begin the burst before the one-shot host request. The server
                # request is independent of the Windows command queue, so the
                # captured frames span SetPlayerHealth(0) and OnPlayerDeath.
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    burst = pool.submit(
                        sync_pair_client.capture_observer,
                        screenshot_label,
                        screenshot_count,
                        screenshot_interval,
                    )
                    time.sleep(min(1.0, max(0.5, screenshot_interval * 4.0)))
                    request_id = sync_pair_client.queue_sync_pair_scenario(
                        scenario,
                        request_path,
                        results_path,
                        fixture_timeout,
                        output,
                    )
                    wait_for_death_event(
                        server_log,
                        start_offset,
                        request_id,
                        fixture_timeout,
                        output,
                    )
                    burst.result(
                        timeout=fixture_timeout
                        + screenshot_count * max(0.025, screenshot_interval)
                        + 30.0
                    )
                output.append(
                    {
                        "event": "windows_pilot_death_capture_completed",
                        "scenario": scenario,
                        "request_id": request_id,
                        "screenshot_label": screenshot_label,
                        "screenshot_count": screenshot_count,
                        "screenshot_interval": screenshot_interval,
                        "host_time": time.time(),
                    }
                )
            except Exception as error:
                returncode = 1
                output.append(
                    {
                        "event": "windows_pilot_death_driver_error",
                        "scenario": scenario,
                        "error": f"{type(error).__name__}: {error}",
                        "host_time": time.time(),
                    }
                )
                traceback.print_exc()
    reloop.write_json(
        output_path,
        {
            "scenario": scenario,
            "windows_role": "pilot",
            "death_f4": death_f4,
            "returncode": returncode,
            "events": output,
        },
    )
    return returncode


def run_windows_ui_latches_driver(
    artifact_dir: Path,
    *,
    lab_timeout: float = 45.0,
) -> int:
    """Exercise only the fixed TAB/F6/F7 actions on Windows Original R5."""
    scenario = UI_LATCH_SCENARIO
    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    returncode = 0

    with console_path.open("w", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                for step, key in UI_LATCH_ACTIONS:
                    started = time.time()
                    requested = {
                        "event": "windows_pilot_ui_latch_key_requested",
                        "scenario": scenario,
                        "step": step,
                        "input_action": key,
                        "host_time": started,
                    }
                    output.append(requested)
                    print(json.dumps(requested, sort_keys=True))
                    windows_edge.run_lab(
                        artifact_dir,
                        f"pilot-ui-latches-{step}",
                        [
                            "key",
                            key,
                            f"dist-sync-ui-latches-{step}",
                        ],
                        timeout=lab_timeout,
                    )
                    completed = {
                        "event": "windows_pilot_ui_latch_key_completed",
                        "scenario": scenario,
                        "step": step,
                        "input_action": key,
                        "started_host_time": started,
                        "completed_host_time": time.time(),
                    }
                    output.append(completed)
                    print(json.dumps(completed, sort_keys=True))
            except Exception as error:
                returncode = 1
                output.append(
                    {
                        "event": "windows_pilot_ui_latch_driver_error",
                        "scenario": scenario,
                        "error": f"{type(error).__name__}: {error}",
                        "host_time": time.time(),
                    }
                )
                traceback.print_exc()

    reloop.write_json(
        output_path,
        {
            "scenario": scenario,
            "windows_role": "pilot",
            "input_contract": {
                "bounded_actions": [key for _step, key in UI_LATCH_ACTIONS],
                "tab_keyup_pulses": 2,
                "tab_hold_ms": 750,
                "f6_f7_hold_ms": 100,
                "pause_or_escape_automation": False,
            },
            "returncode": returncode,
            "events": output,
        },
    )
    return returncode


def wait_for_gmx_server_restart(
    server_console: Path,
    start_offset: int,
    nickname: str,
    timeout_seconds: float,
    output: list[dict[str, Any]],
    process: subprocess.Popen[Any] | None = None,
) -> str:
    """Wait for the new gamemode and this run's Windows pilot to rejoin."""
    deadline = time.monotonic() + timeout_seconds
    banner = "Bare open.mp Vehicle/Object Test Script"
    join_pattern = re.compile(
        rf"\[bare-rpctest\] RPC137 ServerJoin player=\d+ "
        rf"name={re.escape(nickname)}\b"
    )
    while time.monotonic() < deadline:
        if server_console.exists():
            data = server_console.read_bytes()
            if len(data) < start_offset:
                start_offset = 0
            appended = data[start_offset:].decode("utf-8", errors="replace")
            banner_index = appended.find(banner)
            if banner_index >= 0:
                joined = join_pattern.search(appended, banner_index)
                if joined is not None:
                    event = {
                        "event": "windows_pilot_gmx_server_restart_observed",
                        "scenario": GMX_SCENARIO,
                        "server_banner": banner,
                        "server_join": joined.group(0),
                        "host_time": time.time(),
                    }
                    output.append(event)
                    print(json.dumps(event, sort_keys=True))
                    return joined.group(0)
        if process is not None and process.poll() is not None:
            raise DistributedSyncError(
                "open.mp exited while waiting for the post-GMX restart"
            )
        time.sleep(0.05)
    raise TimeoutError(
        f"open.mp emitted no post-GMX restart and {nickname} rejoin "
        f"within {timeout_seconds:.1f}s"
    )


def run_windows_gmx_driver(
    artifact_dir: Path,
    *,
    server: lifecycle_probe.StdinProcess,
    server_console: Path,
    fixture_timeout: float,
    screenshot_count: int,
    screenshot_interval: float,
    nickname: str = "SyncPilot",
) -> int:
    """Send GMX through open.mp stdin and capture the Windows pilot transition."""
    output_path = artifact_dir / "driver" / f"{GMX_SCENARIO}.json"
    console_path = artifact_dir / "driver" / f"{GMX_SCENARIO}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    returncode = 0
    screenshot_label = f"dist-sync-gmx-pilot-{int(time.time())}"
    start_offset = server_console.stat().st_size if server_console.exists() else 0

    with console_path.open("w", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                sync_pair_client.capture_observer(
                    f"{screenshot_label}-before",
                    1,
                    0.0,
                )
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    burst = pool.submit(
                        sync_pair_client.capture_observer,
                        screenshot_label,
                        screenshot_count,
                        screenshot_interval,
                    )
                    time.sleep(min(1.0, max(0.5, screenshot_interval * 4.0)))
                    server.send("gmx")
                    sent = {
                        "event": "windows_pilot_gmx_sent",
                        "scenario": GMX_SCENARIO,
                        "source": "open.mp_console",
                        "host_time": time.time(),
                    }
                    output.append(sent)
                    print(json.dumps(sent, sort_keys=True))
                    wait_for_gmx_server_restart(
                        server_console,
                        start_offset,
                        nickname,
                        fixture_timeout,
                        output,
                        server.process,
                    )
                    burst.result(
                        timeout=fixture_timeout
                        + screenshot_count * max(0.025, screenshot_interval)
                        + 30.0
                    )
                sync_pair_client.capture_observer(
                    f"{screenshot_label}-after",
                    1,
                    0.0,
                )
                output.append(
                    {
                        "event": "windows_pilot_gmx_capture_completed",
                        "scenario": GMX_SCENARIO,
                        "screenshot_label": screenshot_label,
                        "screenshot_count": screenshot_count,
                        "screenshot_interval": screenshot_interval,
                        "post_restart_screenshot": (
                            f"{screenshot_label}-after"
                        ),
                        "host_time": time.time(),
                    }
                )
            except Exception as error:
                returncode = 1
                output.append(
                    {
                        "event": "windows_pilot_gmx_driver_error",
                        "scenario": GMX_SCENARIO,
                        "error": f"{type(error).__name__}: {error}",
                        "host_time": time.time(),
                    }
                )
                traceback.print_exc()
    reloop.write_json(
        output_path,
        {
            "scenario": GMX_SCENARIO,
            "windows_role": "pilot",
            "command_source": "open.mp_console",
            "returncode": returncode,
            "events": output,
        },
    )
    return returncode


def collect_local_artifacts(
    artifact_dir: Path,
    server_snapshot: reloop.FileSnapshot,
    result_snapshot: reloop.FileSnapshot,
    local_snapshots: dict[str, reloop.FileSnapshot],
    local_role: str = "pilot",
) -> str:
    server_snapshot.capture_append(artifact_dir / "server.log")
    result_snapshot.capture_append(artifact_dir / "sync-pair-results.log")
    return sync_edge_probe.collect_logs(
        artifact_dir / local_role / "client",
        local_snapshots,
    )


def driver_request_ids(artifact_dir: Path) -> dict[str, int]:
    request_ids: dict[str, int] = {}
    for path in sorted((artifact_dir / "driver").glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        events = value if isinstance(value, list) else value.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            request_id = event.get("request_id")
            if (
                event.get("event") == "sync_pair_scenario_queued"
                and isinstance(request_id, int)
                and request_id > 0
            ):
                request_ids[path.stem] = request_id
                break
    return request_ids


def owned_request_ids(artifact_dir: Path) -> set[int]:
    return set(driver_request_ids(artifact_dir).values())


def cleanup_owned_request(
    request_path: Path,
    artifact_dir: Path,
) -> tuple[bool, str | None]:
    """Remove only a request ID proven to have been emitted by this run."""
    if not request_path.exists():
        return True, None
    try:
        raw = request_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        return False, f"read_failed:{type(error).__name__}:{error}"
    match = re.fullmatch(r"\s*(\d+)\s+([A-Za-z0-9_]+)\s*", raw)
    ids = owned_request_ids(artifact_dir)
    if not match or int(match.group(1)) not in ids:
        return False, "pending_request_not_owned"
    saved = artifact_dir / "cleanup" / "pending-sync-pair-request.txt"
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(request_path, saved)
    try:
        request_path.unlink()
    except OSError as error:
        return False, f"unlink_failed:{type(error).__name__}:{error}"
    return not request_path.exists(), None


def _contains_crash(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CRASH_MARKERS)


def request_trace(text: str, request_id: int | None) -> str:
    """Return only fixture blocks opened by this driver's request ID."""
    if request_id is None:
        return ""
    selected: list[str] = []
    active = False
    for line in text.splitlines():
        if "marker=ARTIFACT_BOUNDARY" in line:
            active = False
            continue
        accepted = re.search(
            r"marker=REQUEST_ACCEPTED\b[^\r\n]*\brequest=(\d+)\b",
            line,
        )
        if accepted:
            active = int(accepted.group(1)) == request_id
        if active:
            selected.append(line)
    return "\n".join(selected)


def _request_done(text: str, scenario: str, request_id: int | None) -> bool:
    if request_id is None:
        return False
    return bool(
        re.search(
            rf"marker=REQUEST_DONE\b[^\r\n]*\brequest={request_id}\b"
            rf"[^\r\n]*\bstatus=PASS\b"
            rf"[^\r\n]*\bscenario={re.escape(scenario)}\b",
            text,
        )
    )


def gmx_server_cycle_checks(server_text: str, nickname: str) -> tuple[bool, bool]:
    """Require both initial and post-GMX markers inside one artifact slice."""
    banner = "Bare open.mp Vehicle/Object Test Script"
    join_pattern = re.compile(
        rf"\[bare-rpctest\] RPC137 ServerJoin player=\d+ "
        rf"name={re.escape(nickname)}\b"
    )
    sections = server_text.split(
        "[distributed_sync] marker=ARTIFACT_BOUNDARY"
    )
    restart_seen = any(section.count(banner) >= 2 for section in sections)
    rejoin_seen = any(len(join_pattern.findall(section)) >= 2 for section in sections)
    return restart_seen, rejoin_seen


def scenario_checks(
    scenario: str,
    server_text: str,
    windows_logs: str,
    driver_returncodes: dict[str, int],
    driver_request_ids_by_scenario: dict[str, int],
    requested_probe_profile: str | None = None,
) -> dict[str, bool]:
    if scenario == UI_LATCH_SCENARIO:
        return {
            "driver_completed": driver_returncodes.get(scenario) == 0,
            "ui_latch_hooks_installed": bool(
                re.search(
                    r"ui_latches_hook: summary installed=9 requested=9\b",
                    windows_logs,
                )
            ),
            "scoreboard_show_seen": "kind=scoreboard_show " in windows_logs,
            "scoreboard_hide_seen": "kind=scoreboard_hide " in windows_logs,
            "chat_open_seen": "kind=chat_open " in windows_logs,
            "chat_close_seen": "kind=chat_close " in windows_logs,
            "three_chat_mode_edges_seen": windows_logs.count(
                "kind=chat_mode_toggle "
            )
            >= 3,
            "ui_latch_ring_not_overflowed": (
                "ui_latches_r5: overflow " not in windows_logs
            ),
        }

    if scenario == GMX_SCENARIO:
        server_restart_seen, windows_pilot_rejoined = gmx_server_cycle_checks(
            server_text,
            "SyncPilot",
        )
        checks = {
            "driver_completed": driver_returncodes.get(scenario) == 0,
            "server_restart_seen": server_restart_seen,
            "windows_pilot_rejoined": windows_pilot_rejoined,
        }
        if requested_probe_profile == "death-cleanup":
            checks["death_cleanup_gmx_seen"] = bool(
                re.search(
                    r"death_cleanup_r5:[^\r\n]*\bkind=gmx_reset\b",
                    windows_logs,
                )
            )
        else:
            initial_init = windows_logs.find("rpc-in id=139")
            restart = windows_logs.find("rpc-in id=40", initial_init + 1)
            post_restart_init = windows_logs.find("rpc-in id=139", restart + 1)
            checks.update(
                {
                    "initial_init_seen": initial_init >= 0,
                    "gmx_rpc40_seen": restart > initial_init,
                    "post_gmx_init_seen": post_restart_init > restart,
                }
            )
        return checks

    fixture_scenario = "m4" if scenario == "angles" else scenario
    request_id = driver_request_ids_by_scenario.get(scenario)
    trace = request_trace(server_text, request_id)
    checks = {
        "driver_completed": driver_returncodes.get(scenario) == 0,
        "request_id_recorded": request_id is not None,
        "request_acknowledged": _request_done(
            trace,
            fixture_scenario,
            request_id,
        ),
    }
    if scenario in WEAPON_IDS:
        weapon = WEAPON_IDS[scenario]
        checks["onfoot_setup_seen"] = bool(
            re.search(
                rf"marker=SCENARIO_START\b[^\r\n]*\bscenario=onfoot\b"
                rf"[^\r\n]*\bweapon={weapon}\b",
                trace,
            )
        )
        checks["matching_weapon_shot_seen"] = bool(
            re.search(
                rf"marker=WEAPON_SHOT\b[^\r\n]*\bweapon={weapon}\b"
                rf"[^\r\n]*\bexpected_weapon={weapon}\b",
                trace,
            )
        )
    elif scenario == "angles":
        checks["m4_setup_seen"] = bool(
            re.search(
                r"marker=SCENARIO_START\b[^\r\n]*\bscenario=onfoot\b"
                r"[^\r\n]*\bweapon=31\b",
                trace,
            )
        )
        facing_values = {
            match.group(1)
            for match in re.finditer(
                r"marker=PILOT_SYNC\b[^\r\n]*\bscenario=onfoot\b"
                r"[^\r\n]*\bweapon=31\b[^\r\n]*\bfacing=(-?\d+(?:\.\d+)?)",
                trace,
            )
        }
        checks["multiple_facing_samples_seen"] = len(facing_values) >= 2
    elif scenario == "jetpack":
        checks["jetpack_setup_seen"] = (
            "marker=SCENARIO_START" in trace
            and "scenario=jetpack" in trace
        )
        checks["jetpack_special_action_seen"] = bool(
            re.search(
                r"marker=PILOT_SYNC\b[^\r\n]*\bscenario=jetpack\b"
                r"[^\r\n]*\bspecial=2\b",
                trace,
            )
        )
    elif scenario == "pickup":
        checks["pickup_created_seen"] = "marker=PICKUP_CREATED" in trace
        checks["pickup_collected_seen"] = "marker=PICKUP_COLLECTED" in trace
    elif scenario == "death":
        checks["death_trigger_seen"] = "marker=DEATH_TRIGGER" in trace
        checks["player_death_seen"] = "marker=PLAYER_DEATH" in trace
    return checks


def build_verdict(
    *,
    windows_role: str = "observer",
    scenarios: list[str],
    server_text: str,
    windows_logs: str,
    local_logs: str,
    windows_manifest: dict[str, Any],
    driver_returncodes: dict[str, int],
    driver_request_ids_by_scenario: dict[str, int],
    dll_candidate: dict[str, Any] | None,
    probe_candidate: dict[str, Any] | None,
    requested_probe_profile: str | None,
    runner_error: str | None,
    cleanup_errors: list[str],
    local_hashes_unchanged: bool,
    windows_artifact_fetched: bool,
    windows_logs_fetched: bool,
    windows_screenshots_fetched: bool,
) -> dict[str, Any]:
    scenario_results: dict[str, Any] = {}
    scenarios_pass = True
    for scenario in scenarios:
        checks = scenario_checks(
            scenario,
            server_text,
            windows_logs,
            driver_returncodes,
            driver_request_ids_by_scenario,
            requested_probe_profile,
        )
        passed = all(checks.values())
        scenario_results[scenario] = {
            "checks": checks,
            "verdict": "SERVER_TRACE_PASS" if passed else "FAIL",
            "visual_parity": "TODO_VERIFY",
        }
        scenarios_pass = scenarios_pass and passed

    manifest_autopause = windows_manifest.get("autopause")
    manifest_flags = windows_manifest.get("probe_flags")
    expected_flags = expected_profile_flags(requested_probe_profile)
    if expected_flags is None:
        expected_flags = ()
    windows_hash = windows_manifest.get("samp_sha256")
    probe_hash = windows_manifest.get("samp_probe_sha256")
    dll_hash_matches = (
        dll_candidate is None or windows_hash == dll_candidate.get("sha256")
    )
    probe_hash_matches = (
        probe_candidate is None or probe_hash == probe_candidate.get("sha256")
    )
    profile_matches = (
        isinstance(manifest_flags, list)
        and sorted(manifest_flags) == sorted(expected_flags)
    )
    scenario_profile_valid = (
        UI_LATCH_SCENARIO not in scenarios
        or requested_probe_profile == "ui-latches-r5"
    )
    autopause_verified = bool(
        isinstance(manifest_autopause, dict)
        and manifest_autopause.get("disabled") is True
    )
    original_probe_identity_required = (
        GMX_SCENARIO in scenarios
        and requested_probe_profile == "death-cleanup"
    ) or UI_LATCH_SCENARIO in scenarios
    original_probe_identity_matches = (
        not original_probe_identity_required
        or windows_hash == ORIGINAL_R5_SHA256
    )
    windows_crash = _contains_crash(windows_logs)
    local_crash = _contains_crash(local_logs)
    hard_failure = any(
        (
            not scenarios_pass,
            bool(runner_error),
            bool(cleanup_errors),
            not local_hashes_unchanged,
            not windows_artifact_fetched,
            not windows_logs_fetched,
            not windows_screenshots_fetched,
            not windows_hash,
            not dll_hash_matches,
            not probe_hash_matches,
            not profile_matches,
            not scenario_profile_valid,
            not autopause_verified,
            not original_probe_identity_matches,
            windows_crash,
            local_crash,
        )
    )
    if windows_hash == ORIGINAL_R5_SHA256:
        windows_identity = "original_r5"
    elif dll_candidate and windows_hash == dll_candidate.get("sha256"):
        windows_identity = "explicit_candidate"
    elif windows_hash:
        windows_identity = "installed_non_original"
    else:
        windows_identity = "unknown"
    return {
        "verdict": "FAIL" if hard_failure else "TRACE_CAPTURED_VISUAL_UNVERIFIED",
        "visual_parity": "TODO_VERIFY",
        "visual_evidence": (
            "Screenshot artifacts were retained, but require manual review or "
            "a separately defined image-diff oracle"
        ),
        "topology": topology_for_role(windows_role),
        "windows_role": windows_role,
        "local_role": "observer" if windows_role == "pilot" else "pilot",
        "scenarios": scenario_results,
        "windows_identity": windows_identity,
        "windows_samp_sha256": windows_hash,
        "windows_probe_sha256": probe_hash,
        "requested_probe_profile": requested_probe_profile,
        "scenario_probe_profile_valid": scenario_profile_valid,
        "windows_probe_flags": manifest_flags,
        "windows_autopause_verified": autopause_verified,
        "original_probe_identity_required": original_probe_identity_required,
        "original_probe_identity_matches": original_probe_identity_matches,
        "explicit_dll_hash_matches_manifest": dll_hash_matches,
        "explicit_probe_hash_matches_manifest": probe_hash_matches,
        "probe_profile_matches_manifest": profile_matches,
        "windows_artifact_fetched": windows_artifact_fetched,
        "windows_logs_fetched": windows_logs_fetched,
        "windows_screenshots_fetched": windows_screenshots_fetched,
        "local_hashes_unchanged": local_hashes_unchanged,
        "windows_crash_marker": windows_crash,
        "local_crash_marker": local_crash,
        "driver_returncodes": driver_returncodes,
        "runner_error": runner_error,
        "cleanup_errors": cleanup_errors,
    }


def execute(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    validate_role_scenario(args.windows_role, args.scenario)
    validate_death_f4(args.death_f4, args.windows_role, args.scenario)
    validate_ui_latch_profile(args.scenario, args.windows_probe_profile)
    if args.scenario == GMX_SCENARIO and args.server_mode == "reuse":
        raise DistributedSyncError(
            "--scenario=gmx cannot use --server-mode=reuse because the "
            "runner must own open.mp console stdin"
        )
    settings = reloop.load_settings(args.config.resolve())
    local_client = settings.clients["original"]
    windows_role = args.windows_role
    local_role = "observer" if windows_role == "pilot" else "pilot"
    windows_nickname = "SyncPilot" if windows_role == "pilot" else "SyncObserver"
    local_nickname = "SyncObserver" if windows_role == "pilot" else "SyncPilot"
    windows_metadata_key = f"windows_{windows_role}"
    local_metadata_key = f"local_{local_role}"
    scenarios = expand_scenarios(args.scenario)
    artifact_dir = settings.artifacts_root / reloop.run_id(
        "distributed-sync", args.scenario
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)
    print(f"artifact: {artifact_dir}", flush=True)

    dll_candidate = (
        windows_edge.validate_x86_pe(args.deploy_windows_dll.expanduser().resolve())
        if args.deploy_windows_dll is not None
        else None
    )
    probe_candidate = (
        windows_edge.validate_x86_pe(
            args.deploy_windows_probe.expanduser().resolve()
        )
        if args.deploy_windows_probe is not None
        else None
    )
    expected_profile_flags(args.windows_probe_profile)
    layout = validate_local_layout(settings, local_client, windows_role)
    if not LAB_WRAPPER.is_file():
        raise DistributedSyncError(f"Windows lab wrapper is missing: {LAB_WRAPPER}")
    if not SAFE_HOST.fullmatch(args.windows_server_host):
        raise DistributedSyncError(
            f"invalid Windows-visible server host: {args.windows_server_host}"
        )
    fixture = settings.server_root / "filterscripts/sync_pair.amx"
    request_path = settings.server_root / "scriptfiles/sync_pair_request.txt"
    if not fixture.is_file():
        raise DistributedSyncError(f"sync-pair fixture is not compiled: {fixture}")
    if request_path.exists():
        raise DistributedSyncError(
            f"sync-pair request is already pending: {request_path}"
        )

    local_hashes_before = {
        "gta_exe": reloop.sha256(local_client.gta_exe),
        "samp_dll": reloop.sha256(local_client.samp_dll),
        "control_asi": optional_sha256(
            local_client.gta_root / reloop.CONTROL_ASI.name
        ),
        "asi": sync_edge_probe.file_hashes(local_client.gta_root),
    }
    metadata: dict[str, Any] = {
        "run_id": artifact_dir.name,
        "started_at": reloop.utc_timestamp(),
        "windows_role": windows_role,
        "local_role": local_role,
        "topology": topology_for_role(windows_role),
        "scenarios": scenarios,
        "death_f4": {
            "requested": args.death_f4,
            "input_action": "CLASS" if args.death_f4 else None,
            "phase": "before_death_request" if args.death_f4 else None,
            "settle_seconds": 0.75 if args.death_f4 else None,
        },
        "gmx": {
            "requested": args.scenario == GMX_SCENARIO,
            "source": (
                "open.mp_console"
                if args.scenario == GMX_SCENARIO
                else None
            ),
            "post_restart_screenshot": args.scenario == GMX_SCENARIO,
        },
        "ui_latches": {
            "requested": args.scenario == UI_LATCH_SCENARIO,
            "input_actions": (
                [key for _step, key in UI_LATCH_ACTIONS]
                if args.scenario == UI_LATCH_SCENARIO
                else []
            ),
            "pause_or_escape_automation": False,
        },
        "layout": layout,
        "server": {
            "local_host": settings.host,
            "windows_visible_host": args.windows_server_host,
            "port": settings.port,
            "mode": args.server_mode,
        },
        local_metadata_key: {
            "profile": "original",
            "nickname": local_nickname,
            "dll_sha256": reloop.sha256(local_client.samp_dll),
        },
        windows_metadata_key: {
            "nickname": windows_nickname,
            "favorite_index": args.windows_favorite_index,
            "dll_deploy_requested": dll_candidate is not None,
            "dll_candidate": dll_candidate,
            "probe_deploy_requested": probe_candidate is not None,
            "probe_candidate": probe_candidate,
            "probe_profile_requested": args.windows_probe_profile,
        },
        "local_hashes_before": local_hashes_before,
        "visual_parity": "TODO_VERIFY",
    }
    reloop.write_json(artifact_dir / "metadata.json", metadata)

    server_console = artifact_dir / "server.console.log"
    server_log = settings.server_root / "log.txt"
    result_file = settings.server_root / "scriptfiles/sync_pair_results.log"
    server_snapshot = reloop.FileSnapshot.take(server_log)
    result_snapshot = reloop.FileSnapshot.take(result_file)
    local_snapshots = {
        name: reloop.FileSnapshot.take(local_client.gta_root / name)
        for name in reloop.CLIENT_LOG_NAMES
    }
    local_pre_pids = reloop.prefix_pids(local_client.prefix)
    server: reloop.ManagedProcess | lifecycle_probe.StdinProcess | None = None
    local_process: reloop.ManagedProcess | None = None
    windows_start_attempted = False
    windows_run_id: str | None = None
    profile_changed = False
    driver_returncodes: dict[str, int] = {}
    runner_exception: BaseException | None = None
    runner_error: str | None = None
    cleanup_errors: list[str] = []
    windows_fetch_root = artifact_dir / "windows"
    windows_receipts: dict[str, Any] = {}
    windows_preflight: dict[str, Any] | None = None
    windows_post_setup: dict[str, Any] | None = None

    try:
        reloop.replace_existing_client(
            local_client, args.local_client_mode, settings.shutdown_timeout_s
        )
        if (
            local_role == "pilot"
            and not sync_edge_probe.tcp_port_available("127.0.0.1", CONTROL_PORT)
        ):
            raise DistributedSyncError(
                f"localhost control port {CONTROL_PORT} is occupied"
            )
        reused_server = reloop.replace_existing_server(settings, args.server_mode)
        if not reused_server:
            if args.scenario == GMX_SCENARIO:
                server = lifecycle_probe._start_server(settings, server_console)
            else:
                server = reloop.start_process(
                    [str(settings.server_executable)],
                    settings.server_root,
                    server_console,
                    "open.mp",
                )
            if not reloop.wait_for_text(
                server_console,
                reloop.SERVER_READY_PATTERN,
                settings.server_ready_timeout_s,
                server.process,
            ):
                raise DistributedSyncError(
                    "open.mp did not become ready; see server.console.log"
                )

        first_ping = windows_edge.run_lab(
            artifact_dir,
            "preflight-ping",
            ["ping"],
            timeout=args.lab_timeout,
        )
        if args.windows_client_mode == "replace":
            windows_edge.run_lab(
                artifact_dir,
                "preflight-stop",
                ["stop"],
                timeout=args.lab_timeout,
            )
            idle_ping = windows_edge.run_lab(
                artifact_dir,
                "preflight-idle-ping",
                ["ping"],
                timeout=args.lab_timeout,
            )
        else:
            idle_ping = first_ping
        windows_preflight = parse_windows_preflight(idle_ping.stdout)
        validate_windows_idle(windows_preflight)
        if args.windows_probe_profile is None:
            validate_probe_state(windows_preflight, None)

        label = f"dist-sync-{artifact_dir.name[-24:]}"
        for action_label, action in windows_mutation_plan(
            dll_candidate,
            probe_candidate,
            args.windows_probe_profile,
            label,
        ):
            if action_label == "probe-profile":
                # The remote command can time out after applying the flag
                # change but before returning its receipt. Mark it dirty
                # before execution so finally always attempts passive reset.
                profile_changed = True
            receipt = windows_edge.run_lab(
                artifact_dir,
                action_label,
                action,
                timeout=args.lab_timeout,
            )
            if action_label == "dll-deploy":
                windows_receipts[action_label] = verify_deploy_receipt(
                    receipt.stdout, dll_candidate, kind="DLL"  # type: ignore[arg-type]
                )
            elif action_label == "probe-deploy":
                windows_receipts[action_label] = verify_deploy_receipt(
                    receipt.stdout, probe_candidate, kind="probe"  # type: ignore[arg-type]
                )
            elif action_label == "probe-profile":
                windows_receipts[action_label] = verify_profile_receipt(
                    receipt.stdout, args.windows_probe_profile  # type: ignore[arg-type]
                )

        post_setup_ping = windows_edge.run_lab(
            artifact_dir,
            "post-setup-ping",
            ["ping"],
            timeout=args.lab_timeout,
        )
        windows_post_setup = parse_windows_preflight(post_setup_ping.stdout)
        validate_windows_idle(windows_post_setup)
        validate_probe_state(
            windows_post_setup,
            args.windows_probe_profile,
        )
        if (
            args.scenario == GMX_SCENARIO
            and args.windows_probe_profile == "death-cleanup"
            and windows_post_setup["samp_sha256"] != ORIGINAL_R5_SHA256
        ):
            raise DistributedSyncError(
                "GMX with the R5 death-cleanup probe requires the documented "
                "Original R5 samp.dll on Windows"
            )
        if (
            args.scenario == UI_LATCH_SCENARIO
            and windows_post_setup["samp_sha256"] != ORIGINAL_R5_SHA256
        ):
            raise DistributedSyncError(
                "ui_latches with the R5 UI-latch probe requires the "
                "documented Original R5 samp.dll on Windows"
            )
        if (
            dll_candidate is not None
            and windows_post_setup["samp_sha256"] != dll_candidate["sha256"]
        ):
            raise DistributedSyncError(
                "Windows installed samp.dll hash differs from explicit candidate"
            )
        if (
            probe_candidate is not None
            and windows_post_setup["samp_probe_sha256"]
            != probe_candidate["sha256"]
        ):
            raise DistributedSyncError(
                "Windows installed samp_probe.asi hash differs from explicit candidate"
            )

        local_command: list[str] | None = None
        local_env: dict[str, str] | None = None
        local_api_verified = False
        if local_role == "pilot":
            local_command, local_env = reloop.direct_client_launch(
                settings, local_client, artifact_dir / f"{local_role}-launch"
            )
            local_command[-1] = f"-n{local_nickname}"
            local_process = reloop.start_process(
                local_command,
                local_client.gta_root,
                artifact_dir / f"{local_role}-launcher.log",
                local_nickname,
                env=local_env,
            )
            local_api = wait_for_api(timeout=args.client_ready_timeout)
            local_api.close()
            local_api_verified = True

        windows_start_attempted = True
        start_result = windows_edge.run_lab(
            artifact_dir,
            f"{windows_role}-start",
            [
                "start",
                f"dist_sync_{args.scenario}_{windows_role}",
                "samp",
                args.windows_server_host,
                str(settings.port),
                windows_nickname,
                str(args.windows_favorite_index),
            ],
            timeout=args.windows_start_timeout,
        )
        windows_run_id = windows_edge.extract_run_id(start_result.stdout)
        if windows_run_id is None:
            discovery = windows_edge.run_lab(
                artifact_dir,
                f"{windows_role}-run-id-discovery",
                ["collect"],
                timeout=args.windows_start_timeout,
            )
            windows_run_id = windows_edge.extract_run_id(discovery.stdout)
        if windows_run_id is None:
            raise DistributedSyncError(
                f"Windows {windows_role} started without a recoverable run_id"
            )

        if local_role == "observer":
            local_command, local_env = reloop.direct_client_launch(
                settings, local_client, artifact_dir / f"{local_role}-launch"
            )
            local_command[-1] = f"-n{local_nickname}"
            local_process = reloop.start_process(
                local_command,
                local_client.gta_root,
                artifact_dir / f"{local_role}-launcher.log",
                local_nickname,
                env=local_env,
            )
        assert local_command is not None
        reloop.write_json(
            artifact_dir / "launch-order.json",
            {
                "windows_started_first": windows_role == "pilot",
                f"windows_{windows_role}_started_first": windows_role == "pilot",
                f"local_{local_role}_started_first": windows_role == "observer",
                "windows_run_id": windows_run_id,
                f"{local_metadata_key}_command": shlex.join(local_command),
                f"{local_metadata_key}_api_verified": local_api_verified,
                f"{local_metadata_key}_api_required": local_role == "pilot",
                "local_replacement_launched": False,
            },
        )
        sync_edge_probe.wait_for_pair(
            server_console,
            server_log,
            server_snapshot,
            args.pair_ready_timeout,
        )

        for index, scenario in enumerate(scenarios):
            if index:
                time.sleep(args.between)
            if windows_role == "pilot":
                if scenario == GMX_SCENARIO:
                    if not isinstance(server, lifecycle_probe.StdinProcess):
                        raise DistributedSyncError(
                            "GMX requires a runner-owned open.mp stdin process"
                        )
                    returncode = run_windows_gmx_driver(
                        artifact_dir,
                        server=server,
                        server_console=server_console,
                        fixture_timeout=args.fixture_timeout,
                        screenshot_count=args.screenshot_count,
                        screenshot_interval=args.screenshot_interval,
                        nickname=windows_nickname,
                    )
                elif scenario == UI_LATCH_SCENARIO:
                    returncode = run_windows_ui_latches_driver(
                        artifact_dir,
                        lab_timeout=args.lab_timeout,
                    )
                else:
                    returncode = run_windows_death_driver(
                        artifact_dir,
                        request_path=request_path,
                        results_path=result_file,
                        server_log=server_log,
                        fixture_timeout=args.fixture_timeout,
                        screenshot_count=args.screenshot_count,
                        screenshot_interval=args.screenshot_interval,
                        death_f4=args.death_f4,
                        lab_timeout=args.lab_timeout,
                    )
            else:
                returncode = run_driver(
                    scenario,
                    artifact_dir,
                    fixture_timeout=args.fixture_timeout,
                    action_seconds=args.action_seconds,
                    screenshot_count=args.screenshot_count,
                    screenshot_interval=args.screenshot_interval,
                )
            driver_returncodes[scenario] = returncode
            if returncode:
                raise DistributedSyncError(
                    f"{scenario} pilot driver failed with exit code {returncode}"
                )
    except BaseException as error:
        runner_exception = error
        runner_error = f"{type(error).__name__}: {error}"
    finally:
        try:
            collect_local_artifacts(
                artifact_dir,
                server_snapshot,
                result_snapshot,
                local_snapshots,
                local_role,
            )
        except Exception as error:
            cleanup_errors.append(
                f"pre_teardown_local_capture:{type(error).__name__}:{error}"
            )

        if windows_start_attempted:
            try:
                collection = windows_edge.run_lab(
                    artifact_dir,
                    "final-collect",
                    ["collect"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if collection.returncode:
                    cleanup_errors.append(
                        f"windows_collect:exit={collection.returncode}"
                    )
                windows_run_id = windows_run_id or windows_edge.extract_run_id(
                    collection.stdout
                )
            except Exception as error:
                cleanup_errors.append(
                    f"windows_collect:{type(error).__name__}:{error}"
                )
            try:
                stopped = windows_edge.run_lab(
                    artifact_dir,
                    "final-stop",
                    ["stop"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if stopped.returncode:
                    cleanup_errors.append(
                        f"windows_stop:exit={stopped.returncode}"
                    )
            except Exception as error:
                cleanup_errors.append(
                    f"windows_stop:{type(error).__name__}:{error}"
                )
            try:
                final_ping = windows_edge.run_lab(
                    artifact_dir,
                    "final-idle-ping",
                    ["ping"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                final_state = parse_windows_preflight(final_ping.stdout)
                validate_windows_idle(final_state)
            except Exception as error:
                cleanup_errors.append(
                    f"windows_idle:{type(error).__name__}:{error}"
                )

        if profile_changed:
            try:
                reset = windows_edge.run_lab(
                    artifact_dir,
                    "probe-profile-reset",
                    ["probe-profile", "passive"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if reset.returncode:
                    raise DistributedSyncError(
                        f"passive profile reset exited {reset.returncode}"
                    )
                verify_profile_receipt(reset.stdout, "passive")
                reset_ping = windows_edge.run_lab(
                    artifact_dir,
                    "probe-profile-reset-ping",
                    ["ping"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if reset_ping.returncode:
                    raise DistributedSyncError(
                        f"post-reset ping exited {reset_ping.returncode}"
                    )
                reset_state = parse_windows_preflight(reset_ping.stdout)
                validate_windows_idle(reset_state)
                validate_probe_state(reset_state, "passive")
                profile_changed = False
            except Exception as error:
                cleanup_errors.append(
                    f"probe_profile_reset:{type(error).__name__}:{error}"
                )

        if local_process is not None:
            try:
                local_process.stop(settings.shutdown_timeout_s)
            except Exception as error:
                cleanup_errors.append(
                    f"local_{local_role}_stop:{type(error).__name__}:{error}"
                )
        try:
            survivors = reloop.terminate_pids(
                reloop.prefix_pids(local_client.prefix) - local_pre_pids,
                settings.shutdown_timeout_s,
            )
            if survivors:
                cleanup_errors.append(
                    f"local_{local_role}_prefix_stop:"
                    f"surviving_pids={sorted(survivors)}"
                )
        except Exception as error:
            cleanup_errors.append(
                f"local_{local_role}_prefix_stop:{type(error).__name__}:{error}"
            )
        if server is not None:
            try:
                server.stop(settings.shutdown_timeout_s)
            except Exception as error:
                cleanup_errors.append(
                    f"server_stop:{type(error).__name__}:{error}"
                )

        request_clean, request_error = cleanup_owned_request(
            request_path, artifact_dir
        )
        if not request_clean:
            cleanup_errors.append(f"sync_pair_request_cleanup:{request_error}")

        windows_artifact_fetched = False
        if windows_run_id is not None:
            try:
                fetched = windows_edge.run_lab(
                    artifact_dir,
                    "final-fetch",
                    ["fetch-run", windows_run_id, str(windows_fetch_root)],
                    timeout=args.fetch_timeout,
                    check=False,
                )
                windows_artifact_fetched = (
                    fetched.returncode == 0
                    and any(windows_fetch_root.rglob("manifest.json"))
                )
                if not windows_artifact_fetched:
                    cleanup_errors.append(
                        f"windows_fetch:exit={fetched.returncode}:manifest=missing"
                    )
            except Exception as error:
                cleanup_errors.append(
                    f"windows_fetch:{type(error).__name__}:{error}"
                )
        elif windows_start_attempted:
            cleanup_errors.append("windows_fetch:run_id_unavailable")

        try:
            local_logs = collect_local_artifacts(
                artifact_dir,
                server_snapshot,
                result_snapshot,
                local_snapshots,
                local_role,
            )
        except Exception as error:
            local_logs = ""
            cleanup_errors.append(
                f"post_teardown_local_capture:{type(error).__name__}:{error}"
            )

        local_hashes_after = {
            "gta_exe": reloop.sha256(local_client.gta_exe),
            "samp_dll": reloop.sha256(local_client.samp_dll),
            "control_asi": optional_sha256(
                local_client.gta_root / reloop.CONTROL_ASI.name
            ),
            "asi": sync_edge_probe.file_hashes(local_client.gta_root),
        }
        local_hashes_unchanged = local_hashes_after == local_hashes_before
        manifest_path, windows_manifest = windows_edge.find_windows_manifest(
            windows_fetch_root, windows_run_id
        )
        windows_logs = windows_edge.collect_windows_logs(windows_fetch_root)
        windows_logs_fetched = bool(
            windows_fetch_root.is_dir()
            and any(windows_fetch_root.rglob("*.log"))
        )
        windows_screenshots_fetched = bool(
            windows_fetch_root.is_dir()
            and any(windows_fetch_root.rglob("*.png"))
        )
        server_text = ""
        for path in (
            server_console,
            artifact_dir / "server.log",
            artifact_dir / "sync-pair-results.log",
        ):
            if path.is_file():
                server_text += (
                    f"[distributed_sync] marker=ARTIFACT_BOUNDARY file={path.name}\n"
                )
                server_text += path.read_text(
                    encoding="utf-8", errors="replace"
                ) + "\n"
        verdict = build_verdict(
            windows_role=windows_role,
            scenarios=scenarios,
            server_text=server_text,
            windows_logs=windows_logs,
            local_logs=local_logs,
            windows_manifest=windows_manifest,
            driver_returncodes=driver_returncodes,
            driver_request_ids_by_scenario=driver_request_ids(artifact_dir),
            dll_candidate=dll_candidate,
            probe_candidate=probe_candidate,
            requested_probe_profile=args.windows_probe_profile,
            runner_error=runner_error,
            cleanup_errors=cleanup_errors,
            local_hashes_unchanged=local_hashes_unchanged,
            windows_artifact_fetched=windows_artifact_fetched,
            windows_logs_fetched=windows_logs_fetched,
            windows_screenshots_fetched=windows_screenshots_fetched,
        )
        metadata.update(
            {
                "finished_at": reloop.utc_timestamp(),
                "windows_preflight": windows_preflight,
                "windows_post_setup": windows_post_setup,
                "windows_receipts": windows_receipts,
                windows_metadata_key: {
                    **metadata[windows_metadata_key],
                    "run_id": windows_run_id,
                    "manifest_path": (
                        str(manifest_path) if manifest_path else None
                    ),
                    "installed_samp_sha256": windows_manifest.get("samp_sha256"),
                    "installed_probe_sha256": windows_manifest.get(
                        "samp_probe_sha256"
                    ),
                },
                "local_hashes_after": local_hashes_after,
                "runner_error": runner_error,
                "cleanup_errors": cleanup_errors,
            }
        )
        reloop.write_json(artifact_dir / "metadata.json", metadata)
        reloop.write_json(artifact_dir / "verdict.json", verdict)

    print(f"verdict: {verdict['verdict']}", flush=True)
    if runner_exception is not None:
        raise runner_exception.with_traceback(runner_exception.__traceback__)
    if cleanup_errors:
        raise DistributedSyncError("; ".join(cleanup_errors))
    return artifact_dir, verdict


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=reloop.DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--scenario",
        choices=(*SCENARIOS, GMX_SCENARIO, UI_LATCH_SCENARIO, "all"),
        default="all",
    )
    parser.add_argument(
        "--server-mode",
        choices=("fail", "replace", "reuse"),
        default="replace",
    )
    parser.add_argument(
        "--local-client-mode",
        choices=("fail", "replace"),
        default="replace",
    )
    parser.add_argument(
        "--windows-client-mode",
        choices=("fail", "replace"),
        default="replace",
    )
    parser.add_argument(
        "--windows-role",
        choices=WINDOWS_ROLES,
        default="observer",
        help=(
            "role assigned by nickname to Windows; pilot is restricted to "
            "--scenario=death, --scenario=gmx, or --scenario=ui_latches so "
            "Windows receives the state-machine/UI transition"
        ),
    )
    parser.add_argument(
        "--death-f4",
        action="store_true",
        help=(
            "send the allowlisted Windows CLASS/F4 action before the death "
            "request; valid only with --scenario=death --windows-role=pilot"
        ),
    )
    parser.add_argument("--windows-server-host", default="192.168.3.181")
    parser.add_argument("--windows-favorite-index", type=int, default=3)
    parser.add_argument(
        "--deploy-windows-dll",
        type=Path,
        help=(
            "explicitly validate and deploy this x86 samp.dll; omitted means "
            "the runner never changes the Windows DLL"
        ),
    )
    parser.add_argument(
        "--deploy-windows-probe",
        type=Path,
        help=(
            "explicitly deploy this x86 samp_probe.asi; omitted means the "
            "runner never changes the Windows probe"
        ),
    )
    parser.add_argument(
        "--windows-probe-profile",
        choices=tuple(PROBE_PROFILE_FLAGS),
        help=(
            "explicit managed profile for this run; omitted leaves profile "
            "files untouched and requires no pre-existing probe flags"
        ),
    )
    parser.add_argument("--client-ready-timeout", type=float, default=60.0)
    parser.add_argument("--pair-ready-timeout", type=float, default=90.0)
    parser.add_argument("--fixture-timeout", type=float, default=60.0)
    parser.add_argument("--action-seconds", type=float, default=4.0)
    parser.add_argument("--between", type=float, default=1.0)
    parser.add_argument("--screenshot-count", type=int, default=40)
    parser.add_argument("--screenshot-interval", type=float, default=0.05)
    parser.add_argument("--windows-start-timeout", type=float, default=45.0)
    parser.add_argument("--lab-timeout", type=float, default=45.0)
    parser.add_argument("--fetch-timeout", type=float, default=120.0)
    args = parser.parse_args()

    for field in (
        "client_ready_timeout",
        "pair_ready_timeout",
        "fixture_timeout",
        "action_seconds",
        "windows_start_timeout",
        "lab_timeout",
        "fetch_timeout",
    ):
        if getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    if args.between < 0:
        parser.error("--between must not be negative")
    if not 1 <= args.screenshot_count <= 120:
        parser.error("--screenshot-count must be between 1 and 120")
    if not 0.025 <= args.screenshot_interval <= 10.0:
        parser.error("--screenshot-interval must be between 0.025 and 10 seconds")
    if not 0 <= args.windows_favorite_index <= 100:
        parser.error("--windows-favorite-index must be between 0 and 100")
    if args.windows_role == "pilot" and args.scenario not in (
        "death",
        GMX_SCENARIO,
        UI_LATCH_SCENARIO,
    ):
        parser.error(
            "--windows-role=pilot requires --scenario=death, "
            "--scenario=gmx, or --scenario=ui_latches"
        )
    if (
        args.scenario in (GMX_SCENARIO, UI_LATCH_SCENARIO)
        and args.windows_role != "pilot"
    ):
        parser.error(
            f"--scenario={args.scenario} requires --windows-role=pilot"
        )
    if args.scenario == GMX_SCENARIO and args.server_mode == "reuse":
        parser.error("--scenario=gmx cannot use --server-mode=reuse")
    if args.death_f4 and not (
        args.scenario == "death" and args.windows_role == "pilot"
    ):
        parser.error(
            "--death-f4 requires --scenario=death and --windows-role=pilot"
        )
    if (
        args.scenario == UI_LATCH_SCENARIO
        and args.windows_probe_profile != "ui-latches-r5"
    ):
        parser.error(
            "--scenario=ui_latches requires "
            "--windows-probe-profile=ui-latches-r5"
        )

    try:
        _artifact, verdict = execute(args)
    except (
        DistributedSyncError,
        windows_edge.WindowsSyncEdgeError,
        sync_edge_probe.SyncEdgeError,
        reloop.ReLoopError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Distributed sync runner failed: {error}", file=sys.stderr)
        return 2
    except Exception:
        traceback.print_exc()
        return 2
    return 1 if verdict["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
