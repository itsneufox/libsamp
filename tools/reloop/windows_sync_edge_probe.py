#!/usr/bin/env python3
"""Run edge-state sync probes across one local and one Windows machine.

By default the configured local original-R5 client is ``SyncPilot`` and the
native-Windows lab client is ``SyncObserver``.  The explicit
``--windows-role=pilot`` mode is restricted to ``passenger_g``: Windows becomes
``SyncPilot``, receives the fixed lab-side VK_G action, and the sole local
original-R5 prefix becomes ``SyncObserver``.

No Windows DLL is deployed unless ``--deploy-windows-dll PATH`` is supplied.
Even a successful run proves trace/application coverage only; screenshot
bursts remain visual evidence that must be reviewed or compared separately.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import shutil
import struct
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
import sync_edge_probe  # noqa: E402
import sync_pair_client  # noqa: E402
from control_client import VK_F8, wait_for_api  # noqa: E402


EDGE_SCENARIOS = sync_edge_probe.EDGE_SCENARIOS
WINDOWS_EDGE_SCENARIOS = sync_edge_probe.SUPPORTED_EDGE_SCENARIOS
CONTROL_PORT = sync_edge_probe.CONTROL_PORT
AUTOPAUSE_INI = sync_edge_probe.AUTOPAUSE_INI
LAB_WRAPPER = REPO_ROOT / "tools/windows/remote_lab/samp_lab.sh"
ORIGINAL_R5_SHA256 = (
    "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2"
)
SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
WINDOWS_ROLES = ("observer", "pilot")


class WindowsSyncEdgeError(RuntimeError):
    """Expected operator-facing distributed probe failure."""


def validate_role_scenario(windows_role: str, scenario: str) -> None:
    """Keep the role reversal narrow so existing edge runs cannot change roles."""
    if windows_role not in WINDOWS_ROLES:
        raise WindowsSyncEdgeError(f"unsupported Windows role: {windows_role}")
    if windows_role == "pilot" and scenario != sync_edge_probe.PASSENGER_G_SCENARIO:
        raise WindowsSyncEdgeError(
            "--windows-role=pilot is only supported with --scenario=passenger_g"
        )


def topology_for_role(windows_role: str) -> str:
    if windows_role == "pilot":
        return "native_windows_pilot+local_original_observer"
    return "local_original_pilot+native_windows_observer"


def validate_x86_pe(path: Path) -> dict[str, Any]:
    """Validate enough of a PE header to reject a wrong-architecture DLL."""
    if not path.is_file():
        raise WindowsSyncEdgeError(f"Windows DLL candidate does not exist: {path}")
    size = path.stat().st_size
    if size < 0x40:
        raise WindowsSyncEdgeError(f"Windows DLL candidate is too small: {path}")
    with path.open("rb") as handle:
        dos = handle.read(0x40)
        if dos[:2] != b"MZ":
            raise WindowsSyncEdgeError(f"Windows DLL candidate has no MZ header: {path}")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        if pe_offset < 0x40 or pe_offset > size - 6:
            raise WindowsSyncEdgeError(
                f"Windows DLL candidate has an invalid PE offset: {path}"
            )
        handle.seek(pe_offset)
        header = handle.read(6)
    if header[:4] != b"PE\0\0":
        raise WindowsSyncEdgeError(f"Windows DLL candidate has no PE signature: {path}")
    machine = struct.unpack_from("<H", header, 4)[0]
    if machine != 0x014C:
        raise WindowsSyncEdgeError(
            f"Windows DLL candidate is not x86 (machine=0x{machine:04X}): {path}"
        )
    return {
        "path": str(path),
        "size": size,
        "machine": "0x014C",
        "sha256": reloop.sha256(path),
    }


def _json_value(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        # The SSH wrapper can prepend host diagnostics to PowerShell's
        # pretty-printed, multi-line JSON document.  Decode the first complete
        # object/array after that banner instead of assuming one-line JSON.
        decoder = json.JSONDecoder()
        for offset, character in enumerate(stripped):
            if character not in "[{":
                continue
            try:
                value, _end = decoder.raw_decode(stripped, offset)
                return value
            except json.JSONDecodeError:
                continue
    return None


def _find_key(value: Any, key: str) -> Any | None:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _find_key(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_key(nested, key)
            if found is not None:
                return found
    return None


def extract_run_id(text: str) -> str | None:
    value = _find_key(_json_value(text), "run_id")
    if not isinstance(value, str) or not SAFE_LABEL.fullmatch(value):
        return None
    return value


def extract_processes(text: str) -> list[Any] | None:
    value = _find_key(_json_value(text), "processes")
    return value if isinstance(value, list) else None


def run_lab(
    artifact_dir: Path,
    label: str,
    arguments: list[str],
    *,
    timeout: float,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one allowlisted Windows-lab wrapper command and retain its output."""
    log_path = artifact_dir / "windows-control" / f"{label}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [str(LAB_WRAPPER), *arguments]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = completed.stdout or ""
    except subprocess.TimeoutExpired as error:
        output_value = error.stdout or ""
        if isinstance(output_value, bytes):
            output = output_value.decode("utf-8", errors="replace")
        else:
            output = output_value
        log_path.write_text(
            f"command={shlex.join(command)}\n"
            f"timeout={timeout}\n"
            f"{output}",
            encoding="utf-8",
        )
        raise WindowsSyncEdgeError(
            f"Windows lab command timed out after {timeout:.1f}s: {arguments[0]}"
        ) from error
    log_path.write_text(
        f"command={shlex.join(command)}\n"
        f"returncode={completed.returncode}\n"
        f"{output}",
        encoding="utf-8",
    )
    if check and completed.returncode:
        raise WindowsSyncEdgeError(
            f"Windows lab command failed with exit code {completed.returncode}: "
            f"{arguments[0]}; see {log_path}"
        )
    return completed


def validate_layout(
    settings: reloop.Settings,
    local_client: reloop.ClientProfile,
    windows_role: str = "observer",
) -> dict[str, Any]:
    local_role = "observer" if windows_role == "pilot" else "pilot"
    if local_client.name != "original":
        raise WindowsSyncEdgeError("the local client must be the original profile")
    if not local_client.samp_exe.is_file() or not local_client.samp_dll.is_file():
        raise WindowsSyncEdgeError(
            f"original GTA/SA-MP layout is incomplete: {local_client.gta_root}"
        )
    if reloop.sha256(local_client.samp_dll) != ORIGINAL_R5_SHA256:
        raise WindowsSyncEdgeError(
            "configured local original profile does not contain the expected R5 DLL"
        )
    installed_control = local_client.gta_root / reloop.CONTROL_ASI.name
    if local_role == "pilot" and not installed_control.is_file():
        raise WindowsSyncEdgeError(
            f"local original control ASI is missing: {installed_control}"
        )
    autopause_path = local_client.gta_root / AUTOPAUSE_INI
    if not sync_edge_probe.autopause_disabled(autopause_path):
        raise WindowsSyncEdgeError(
            f"local original requires [game] autoPause = 0 in {autopause_path}"
        )
    replacement = settings.clients.get("replacement")
    replacement_pids = reloop.prefix_pids(replacement.prefix) if replacement else set()
    if replacement_pids:
        raise WindowsSyncEdgeError(
            "the local replacement prefix is active; this runner permits exactly "
            f"one local prefix (pids={sorted(replacement_pids)})"
        )
    layout = {
        "local_role": local_role,
        "local_profile": local_client.name,
        "local_prefix": str(local_client.prefix),
        "local_dll_sha256": reloop.sha256(local_client.samp_dll),
        "local_control_sha256": (
            reloop.sha256(installed_control)
            if installed_control.is_file()
            else None
        ),
        "local_control_required": local_role == "pilot",
        "built_control_sha256": (
            reloop.sha256(reloop.CONTROL_ASI)
            if reloop.CONTROL_ASI.is_file()
            else None
        ),
        "local_autopause": True,
        "local_replacement_inactive": True,
        "topology": topology_for_role(windows_role),
    }
    # Preserve the established default metadata keys while giving the swapped
    # run truthful observer-prefixed aliases.
    for field in ("profile", "prefix", "dll_sha256", "control_sha256", "autopause"):
        layout[f"{local_role}_{field}"] = layout[f"local_{field}"]
    return layout


def run_driver(
    scenario: str,
    artifact_dir: Path,
    *,
    fixture_timeout: float,
    action_seconds: float,
    screenshot_count: int,
    screenshot_interval: float,
    steer_during_capture: str | None,
) -> int:
    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    screenshot_label = f"dist-edge-{scenario}-{int(time.time())}"
    command = [
        sys.executable,
        str(SCRIPT_DIR / "sync_pair_client.py"),
        scenario,
        "--output",
        str(output_path),
        "--action-seconds",
        str(action_seconds),
        "--observer-screenshot-label",
        screenshot_label,
        "--observer-screenshot-count",
        str(screenshot_count),
        "--observer-screenshot-interval",
        str(screenshot_interval),
        "--sync-pair-request-timeout",
        str(fixture_timeout),
    ]
    if steer_during_capture is not None:
        command.extend(["--steer-during-capture", steer_during_capture])
    screenshot_seconds = screenshot_count * max(0.025, screenshot_interval)
    with console_path.open("wb") as handle:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=fixture_timeout + action_seconds + screenshot_seconds + 60.0,
            check=False,
        )
    return completed.returncode


def run_windows_pilot_driver(
    scenario: str,
    artifact_dir: Path,
    *,
    request_path: Path,
    results_path: Path,
    fixture_timeout: float,
    action_seconds: float,
    lab_timeout: float,
) -> int:
    """Queue passenger_g, inject Windows VK_G, and wait for physical seat 1."""
    if scenario != sync_edge_probe.PASSENGER_G_SCENARIO:
        raise WindowsSyncEdgeError(
            "the Windows-pilot driver only supports passenger_g"
        )

    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    returncode = 0
    with console_path.open("w", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                request_id = sync_pair_client.queue_sync_pair_scenario(
                    scenario,
                    request_path,
                    results_path,
                    fixture_timeout,
                    output,
                )
                # EDGE_SETUP has already proved that the Windows SyncPilot is
                # on foot, within R5's <4-unit gate, and has the vehicle
                # streamed. This fixed allowlisted action is the only input.
                run_lab(
                    artifact_dir,
                    "pilot-passenger-input",
                    [
                        "key",
                        "PASSENGER",
                        f"dist-edge-passenger-g-{int(time.time())}",
                    ],
                    timeout=lab_timeout,
                )
                sync_pair_client.wait_for_sync_pair_result(
                    "PASSENGER_ENTRY_RESULT",
                    scenario,
                    request_id,
                    results_path,
                    fixture_timeout,
                    output,
                )
                time.sleep(max(action_seconds, 1.0))
            except Exception as error:
                returncode = 1
                output.append(
                    {
                        "event": "windows_pilot_driver_error",
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
            "input_action": "PASSENGER",
            "returncode": returncode,
            "events": output,
        },
    )
    return returncode


def capture_local(
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


def capture_host_observer_screenshot(
    artifact_dir: Path,
    scenario: str,
    local_client: reloop.ClientProfile,
) -> dict[str, Any]:
    """Capture the host Original-R5 observer after verified passenger entry."""
    destination = (
        artifact_dir
        / "observer"
        / "screenshots"
        / f"{scenario}-after-entry.png"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok, backend = reloop.take_screenshot(destination)
    if ok:
        return {
            "captured": True,
            "backend": backend,
            "path": str(destination),
        }

    # Wine exposes the window through XWayland even when GNOME denies its
    # whole-desktop screenshot API. Capture that one window without changing
    # focus or injecting input.
    x11_backend = "x11-window:unavailable"
    if shutil.which("xwininfo") and shutil.which("ffmpeg"):
        try:
            window_info = subprocess.run(
                ["xwininfo", "-name", "GTA: San Andreas"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=3.0,
            )
            window_match = re.search(
                r"Window id:\s+(0x[0-9A-Fa-f]+)",
                window_info.stdout,
            )
            if window_info.returncode == 0 and window_match:
                window_id = window_match.group(1)
                capture = subprocess.run(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-f",
                        "x11grab",
                        "-window_id",
                        window_id,
                        "-i",
                        os.environ.get("DISPLAY", ":0"),
                        "-frames:v",
                        "1",
                        "-update",
                        "1",
                        "-y",
                        str(destination),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5.0,
                )
                if (
                    capture.returncode == 0
                    and destination.is_file()
                    and destination.stat().st_size > 8
                ):
                    return {
                        "captured": True,
                        "backend": (
                            f"x11-window:{window_id} (desktop={backend})"
                        ),
                        "path": str(destination),
                    }
                x11_backend = f"x11-window:{window_id}:exit={capture.returncode}"
            else:
                x11_backend = (
                    f"x11-window:not-found:exit={window_info.returncode}"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            x11_backend = f"x11-window:{type(error).__name__}"

    # GNOME's desktop screenshot API can be denied or block under an
    # unattended Wayland session even though the game is healthy. Fall back to
    # Original R5's own renderer only after the request-scoped
    # PASSENGER_ENTRY_RESULT has already passed. The preferred command sets
    # R5's screenshot request flag only after strict PE and byte guards; F8 is
    # retained for an older control ASI. Neither path can trigger or help the
    # Windows pilot's earlier VK_G action.
    screenshot_dirs = [
        local_client.gta_root,
        local_client.gta_root / "SAMP",
        local_client.gta_root / "SAMP" / "screens",
        local_client.gta_root / "SAMP" / "Screenshots",
    ]
    prefix = getattr(local_client, "prefix", None)
    users_root = Path(prefix) / "drive_c" / "users" if prefix is not None else None
    if users_root is not None and users_root.is_dir():
        for user_root in users_root.iterdir():
            user_samp = (
                user_root
                / "Documents"
                / "GTA San Andreas User Files"
                / "SAMP"
            )
            screenshot_dirs.extend((user_samp, user_samp / "screens"))

    def screenshot_files() -> dict[Path, tuple[int, int]]:
        files: dict[Path, tuple[int, int]] = {}
        for directory in screenshot_dirs:
            if not directory.is_dir():
                continue
            for pattern in ("sa-mp-*.png", "samp-*.png"):
                for path in directory.glob(pattern):
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    files[path] = (stat.st_mtime_ns, stat.st_size)
        return files

    before = screenshot_files()
    newest: Path | None = None
    client_backend = "original-r5-f8"
    direct_request_error: str | None = None

    def wait_for_new_screenshot(timeout: float) -> Path | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = screenshot_files()
            changed = [
                path
                for path, identity in current.items()
                if identity[1] > 8 and before.get(path) != identity
            ]
            if changed:
                return max(changed, key=lambda path: current[path][0])
            time.sleep(0.1)
        return None

    try:
        control = wait_for_api(timeout=5.0)
        try:
            try:
                control.command("samp_screenshot")
                client_backend = "original-r5-request-flag"
                newest = wait_for_new_screenshot(3.0)
            except RuntimeError as error:
                # Older control-ASI builds do not expose the identity-guarded
                # request flag. Retain normal input as a compatibility
                # fallback while the runner is upgraded.
                direct_request_error = type(error).__name__
            if newest is None:
                client_backend = "original-r5-f8"
                control.command("focus")
                time.sleep(0.25)
                # Keep F8 down across several render/Input frames. A 35 ms
                # synthetic tap can be missed directly after the focus
                # transition even though the control command itself succeeds.
                control.key(VK_F8, "down")
                time.sleep(0.15)
                control.key(VK_F8, "up")
                newest = wait_for_new_screenshot(2.0)
                if newest is None:
                    # R5 normally consumes DirectInput, but keep the
                    # equivalent window-message edge as a final bounded
                    # fallback.
                    control.command("window_key", vk=VK_F8)
                    newest = wait_for_new_screenshot(3.0)
        finally:
            control.close()
    except (OSError, TimeoutError, ConnectionError, RuntimeError, json.JSONDecodeError) as error:
        return {
            "captured": False,
            "backend": (
                f"{backend}; {x11_backend}; "
                f"original-r5-f8:{type(error).__name__}"
            ),
            "path": str(destination),
        }

    if newest is not None:
        try:
            shutil.copy2(newest, destination)
        except OSError as error:
            return {
                "captured": False,
                "backend": (
                    f"{backend}; {x11_backend}; "
                    f"original-r5-f8-copy:{type(error).__name__}"
                ),
                "path": str(destination),
            }
        return {
            "captured": destination.is_file(),
            "backend": (
                f"{client_backend} (desktop={backend}; x11={x11_backend}; "
                f"direct_error={direct_request_error})"
            ),
            "path": str(destination),
            "source": str(newest),
        }
    return {
        "captured": False,
        "backend": (
            f"{backend}; {x11_backend}; original-r5-f8:no-new-file"
        ),
        "path": str(destination),
    }


def find_windows_manifest(root: Path, run_id: str | None) -> tuple[Path | None, dict[str, Any]]:
    candidates = sorted(root.rglob("manifest.json")) if root.is_dir() else []
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if run_id is None or value.get("run_id") == run_id:
            return path, value
    return None, {}


def collect_windows_logs(root: Path) -> str:
    if not root.is_dir():
        return ""
    # The lab fetch also contains complete GTA-root log archives.  Those can
    # span many older runs (and therefore contain unrelated historical crash
    # markers).  The collector writes the bytes added during this run into
    # latest_log_bytes; only those slices are valid parity evidence.
    paths = sorted(root.rglob("latest_log_bytes/*.log"))
    if not paths:
        paths = sorted(root.rglob("*.log"))
    chunks: list[str] = []
    for path in paths:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def build_verdict(
    *,
    scenarios: list[str],
    server_text: str,
    windows_logs: str,
    local_logs: str = "",
    windows_manifest: dict[str, Any],
    driver_returncodes: dict[str, int],
    candidate: dict[str, Any] | None,
    runner_error: str | None,
    cleanup_errors: list[str],
    local_hashes_unchanged: bool,
    windows_artifact_fetched: bool,
    windows_role: str = "observer",
    host_observer_screenshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_role_scenario(
        windows_role,
        scenarios[0] if len(scenarios) == 1 else "all",
    )
    windows_hash = windows_manifest.get("samp_sha256")
    windows_is_original = windows_hash == ORIGINAL_R5_SHA256
    if windows_is_original:
        windows_identity = "original_r5"
    elif candidate and windows_hash == candidate.get("sha256"):
        windows_identity = "explicit_candidate"
    elif windows_hash:
        windows_identity = "installed_non_original"
    else:
        windows_identity = "unknown"

    if windows_role == "pilot":
        observer_logs = local_logs
        observer_is_replacement = False
        pilot_identity = windows_identity
        observer_identity = "original_r5"
        visual_evidence = (
            "The Windows input action captured the pilot after VK_G; the host "
            "Original-R5 observer screenshot and logs were also retained, but "
            "the image still requires manual or frame-diff review"
        )
    else:
        observer_logs = windows_logs
        observer_is_replacement = not windows_is_original
        pilot_identity = "original_r5"
        observer_identity = windows_identity
        visual_evidence = (
            "Windows observer screenshot bursts were captured; motion quality "
            "requires manual or frame-diff review"
        )

    verdict = sync_edge_probe.evaluate_evidence(
        scenarios,
        server_text,
        observer_logs,
        observer_is_replacement,
        driver_returncodes,
    )
    candidate_hash_matches = (
        True
        if candidate is None
        else windows_hash == candidate.get("sha256")
    )
    windows_crash_marker = sync_edge_probe._contains_crash(windows_logs)
    local_crash_marker = sync_edge_probe._contains_crash(local_logs)
    windows_pilot_is_replacement = (
        windows_role != "pilot"
        or bool(windows_hash and not windows_is_original)
    )
    host_observer_screenshot_captured = bool(
        host_observer_screenshot
        and host_observer_screenshot.get("captured")
    )
    host_observer_screenshot_requirement_met = (
        windows_role != "pilot" or host_observer_screenshot_captured
    )
    verdict.update(
        {
            "topology": topology_for_role(windows_role),
            "windows_role": windows_role,
            "local_role": "observer" if windows_role == "pilot" else "pilot",
            "pilot_identity": pilot_identity,
            "observer_identity": observer_identity,
            "windows_identity": windows_identity,
            "windows_samp_sha256": windows_hash,
            "windows_pilot_is_replacement": windows_pilot_is_replacement,
            "host_observer_screenshot": host_observer_screenshot,
            "host_observer_screenshot_captured": host_observer_screenshot_captured,
            "host_observer_screenshot_requirement_met": (
                host_observer_screenshot_requirement_met
            ),
            "explicit_candidate_hash_matches_manifest": candidate_hash_matches,
            "windows_artifact_fetched": windows_artifact_fetched,
            "local_hashes_unchanged": local_hashes_unchanged,
            "windows_crash_marker": windows_crash_marker,
            "local_crash_marker": local_crash_marker,
            "pilot_crash_marker": (
                windows_crash_marker
                if windows_role == "pilot"
                else local_crash_marker
            ),
            "runner_error": runner_error,
            "cleanup_errors": cleanup_errors,
            "visual_parity": "TODO_VERIFY",
            "visual_evidence": visual_evidence,
        }
    )
    if (
        runner_error
        or cleanup_errors
        or not local_hashes_unchanged
        or not windows_artifact_fetched
        or not candidate_hash_matches
        or not windows_hash
        or not windows_pilot_is_replacement
        or not host_observer_screenshot_requirement_met
        or windows_crash_marker
        or local_crash_marker
    ):
        verdict["verdict"] = "FAIL"
    return verdict


def execute(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    validate_role_scenario(args.windows_role, args.scenario)
    settings = reloop.load_settings(args.config.resolve())
    local_client = settings.clients["original"]
    windows_role = args.windows_role
    local_role = "observer" if windows_role == "pilot" else "pilot"
    windows_nickname = "SyncPilot" if windows_role == "pilot" else "SyncObserver"
    local_nickname = "SyncObserver" if windows_role == "pilot" else "SyncPilot"
    windows_metadata_key = f"windows_{windows_role}"
    local_metadata_key = f"local_{local_role}"
    scenarios = list(EDGE_SCENARIOS if args.scenario == "all" else (args.scenario,))
    artifact_dir = settings.artifacts_root / reloop.run_id(
        "windows-sync-edge", args.scenario
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)
    print(f"artifact: {artifact_dir}", flush=True)

    layout = validate_layout(settings, local_client, windows_role)
    if not LAB_WRAPPER.is_file():
        raise WindowsSyncEdgeError(f"Windows lab wrapper is missing: {LAB_WRAPPER}")
    if not SAFE_HOST.fullmatch(args.windows_server_host):
        raise WindowsSyncEdgeError(
            f"invalid Windows-visible server host: {args.windows_server_host}"
        )
    fixture = settings.server_root / "filterscripts/sync_pair.amx"
    if not fixture.is_file():
        raise WindowsSyncEdgeError(f"sync-pair fixture is not compiled: {fixture}")
    request_path = settings.server_root / "scriptfiles/sync_pair_request.txt"
    if request_path.exists():
        raise WindowsSyncEdgeError(f"sync-pair request is already pending: {request_path}")

    candidate: dict[str, Any] | None = None
    if args.deploy_windows_dll is not None:
        candidate_path = args.deploy_windows_dll.expanduser().resolve()
        candidate = validate_x86_pe(candidate_path)

    local_hashes_before = {
        "samp_dll": reloop.sha256(local_client.samp_dll),
        "asi": sync_edge_probe.file_hashes(local_client.gta_root),
    }
    metadata: dict[str, Any] = {
        "run_id": artifact_dir.name,
        "started_at": reloop.utc_timestamp(),
        "scenarios": scenarios,
        "windows_role": windows_role,
        "local_role": local_role,
        "topology": topology_for_role(windows_role),
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
            "deploy_requested": candidate is not None,
            "candidate": candidate,
        },
        "local_hashes_before": local_hashes_before,
        "visual_parity": "TODO_VERIFY",
    }
    reloop.write_json(artifact_dir / "metadata.json", metadata)

    server: reloop.ManagedProcess | None = None
    local_process: reloop.ManagedProcess | None = None
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
    windows_start_attempted = False
    windows_run_id: str | None = None
    driver_returncodes: dict[str, int] = {}
    runner_exception: BaseException | None = None
    runner_error: str | None = None
    cleanup_errors: list[str] = []
    windows_fetch_root = artifact_dir / "windows"
    host_observer_screenshot: dict[str, Any] | None = None

    try:
        reloop.replace_existing_client(
            local_client, args.local_client_mode, settings.shutdown_timeout_s
        )
        if (
            local_role == "pilot"
            and not sync_edge_probe.tcp_port_available("127.0.0.1", CONTROL_PORT)
        ):
            raise WindowsSyncEdgeError(
                f"localhost control port {CONTROL_PORT} is already occupied"
            )
        reused_server = reloop.replace_existing_server(settings, args.server_mode)
        if not reused_server:
            server = reloop.start_process(
                [str(settings.server_executable)],
                settings.server_root,
                server_console,
                "open.mp",
            )
            ready = reloop.wait_for_text(
                server_console,
                reloop.SERVER_READY_PATTERN,
                settings.server_ready_timeout_s,
                server.process,
            )
            if not ready:
                raise WindowsSyncEdgeError(
                    "open.mp did not become ready; see server.console.log"
                )

        ping_result = run_lab(
            artifact_dir,
            "preflight-ping",
            ["ping"],
            timeout=args.lab_timeout,
        )
        if args.windows_client_mode == "replace":
            run_lab(
                artifact_dir,
                "preflight-stop",
                ["stop"],
                timeout=args.lab_timeout,
            )
        else:
            active_processes = extract_processes(ping_result.stdout)
            if active_processes is None:
                raise WindowsSyncEdgeError(
                    "could not verify that the Windows lab is idle in fail mode"
                )
            if active_processes:
                raise WindowsSyncEdgeError(
                    "Windows GTA/SA-MP is already active and "
                    "--windows-client-mode=fail was requested"
                )
        if candidate is not None:
            candidate_path = Path(candidate["path"])
            run_lab(
                artifact_dir,
                "candidate-validate",
                ["validate", str(candidate_path)],
                timeout=args.lab_timeout,
            )
            deploy_label = f"dist-edge-{artifact_dir.name[-24:]}"
            run_lab(
                artifact_dir,
                "candidate-deploy",
                ["deploy", str(candidate_path), deploy_label],
                timeout=args.lab_timeout,
            )

        windows_start_attempted = True
        start_result = run_lab(
            artifact_dir,
            f"{windows_role}-start",
            [
                "start",
                f"dist_edge_{args.scenario}_{windows_role}",
                "samp",
                args.windows_server_host,
                str(settings.port),
                windows_nickname,
                str(args.windows_favorite_index),
            ],
            timeout=args.windows_start_timeout,
        )
        windows_run_id = extract_run_id(start_result.stdout)
        if windows_run_id is None:
            # A slow interactive launch can outlive the queue submitter's
            # normal wait.  The following collection executes after the start
            # command in the same FIFO and returns the authoritative run ID.
            discovery = run_lab(
                artifact_dir,
                f"{windows_role}-run-id-discovery",
                ["collect"],
                timeout=args.windows_start_timeout,
            )
            windows_run_id = extract_run_id(discovery.stdout)
        if windows_run_id is None:
            raise WindowsSyncEdgeError(
                f"Windows {windows_role} started without a recoverable run_id"
            )
        metadata[windows_metadata_key]["run_id"] = windows_run_id
        reloop.write_json(artifact_dir / "metadata.json", metadata)

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
        local_api_verified = False
        if local_role == "pilot":
            local_api = wait_for_api(timeout=args.client_ready_timeout)
            local_api.close()
            local_api_verified = True
        reloop.write_json(
            artifact_dir / "launch-order.json",
            {
                "windows_started_first": True,
                f"windows_{windows_role}_started_first": True,
                "windows_run_id": windows_run_id,
                local_metadata_key: shlex.join(local_command),
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

        for scenario in scenarios:
            if windows_role == "pilot":
                returncode = run_windows_pilot_driver(
                    scenario,
                    artifact_dir,
                    request_path=request_path,
                    results_path=result_file,
                    fixture_timeout=args.fixture_timeout,
                    action_seconds=args.action_seconds,
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
                    steer_during_capture=args.steer_during_capture,
                )
            driver_returncodes[scenario] = returncode
            if returncode:
                raise WindowsSyncEdgeError(
                    f"{scenario} pilot driver failed with exit code {returncode}"
                )
            if windows_role == "pilot":
                host_observer_screenshot = capture_host_observer_screenshot(
                    artifact_dir,
                    scenario,
                    local_client,
                )
                if not host_observer_screenshot["captured"]:
                    raise WindowsSyncEdgeError(
                        "could not capture the host Original-R5 observer after "
                        f"passenger entry: {host_observer_screenshot['backend']}"
                    )
            time.sleep(args.between)
    except BaseException as error:
        runner_exception = error
        runner_error = f"{type(error).__name__}: {error}"
    finally:
        try:
            capture_local(
                artifact_dir,
                server_snapshot,
                result_snapshot,
                local_snapshots,
                local_role,
            )
        except Exception as error:
            cleanup_errors.append(
                f"pre_teardown_local_capture: {type(error).__name__}: {error}"
            )

        if windows_start_attempted:
            try:
                collection = run_lab(
                    artifact_dir,
                    "final-collect",
                    ["collect"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if collection.returncode:
                    cleanup_errors.append(
                        f"windows_collect: exit={collection.returncode}"
                    )
                windows_run_id = windows_run_id or extract_run_id(collection.stdout)
            except Exception as error:
                cleanup_errors.append(
                    f"windows_collect: {type(error).__name__}: {error}"
                )
            try:
                stopped = run_lab(
                    artifact_dir,
                    "final-stop",
                    ["stop"],
                    timeout=args.lab_timeout,
                    check=False,
                )
                if stopped.returncode:
                    cleanup_errors.append(f"windows_stop: exit={stopped.returncode}")
                windows_run_id = windows_run_id or extract_run_id(stopped.stdout)
            except Exception as error:
                cleanup_errors.append(
                    f"windows_stop: {type(error).__name__}: {error}"
                )

        if local_process is not None:
            try:
                local_process.stop(settings.shutdown_timeout_s)
            except Exception as error:
                cleanup_errors.append(
                    f"{local_role}_stop: {type(error).__name__}: {error}"
                )
            try:
                survivors = reloop.terminate_pids(
                    reloop.prefix_pids(local_client.prefix) - local_pre_pids,
                    settings.shutdown_timeout_s,
                )
                if survivors:
                    cleanup_errors.append(
                        f"{local_role}_prefix_stop: surviving_pids={sorted(survivors)}"
                    )
            except Exception as error:
                cleanup_errors.append(
                    f"{local_role}_prefix_stop: {type(error).__name__}: {error}"
                )
        if server is not None:
            try:
                server.stop(settings.shutdown_timeout_s)
            except Exception as error:
                cleanup_errors.append(
                    f"server_stop: {type(error).__name__}: {error}"
                )

        windows_artifact_fetched = False
        if windows_run_id is not None:
            try:
                fetched = run_lab(
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
                        f"windows_fetch: exit={fetched.returncode} manifest=missing"
                    )
            except Exception as error:
                cleanup_errors.append(
                    f"windows_fetch: {type(error).__name__}: {error}"
                )
        elif windows_start_attempted:
            cleanup_errors.append("windows_fetch: run_id unavailable")

        try:
            local_logs = capture_local(
                artifact_dir,
                server_snapshot,
                result_snapshot,
                local_snapshots,
                local_role,
            )
        except Exception as error:
            local_logs = ""
            cleanup_errors.append(
                f"post_teardown_local_capture: {type(error).__name__}: {error}"
            )

        local_hashes_after = {
            "samp_dll": reloop.sha256(local_client.samp_dll),
            "asi": sync_edge_probe.file_hashes(local_client.gta_root),
        }
        local_hashes_unchanged = local_hashes_after == local_hashes_before
        manifest_path, windows_manifest = find_windows_manifest(
            windows_fetch_root, windows_run_id
        )
        windows_logs = collect_windows_logs(windows_fetch_root)
        server_text = ""
        for path in (server_console, artifact_dir / "server.log"):
            if path.is_file():
                server_text += path.read_text(
                    encoding="utf-8", errors="replace"
                ) + "\n"
        verdict = build_verdict(
            scenarios=scenarios,
            server_text=server_text,
            windows_logs=windows_logs,
            local_logs=local_logs,
            windows_manifest=windows_manifest,
            driver_returncodes=driver_returncodes,
            candidate=candidate,
            runner_error=runner_error,
            cleanup_errors=cleanup_errors,
            local_hashes_unchanged=local_hashes_unchanged,
            windows_artifact_fetched=windows_artifact_fetched,
            windows_role=windows_role,
            host_observer_screenshot=host_observer_screenshot,
        )
        metadata.update(
            {
                "finished_at": reloop.utc_timestamp(),
                windows_metadata_key: {
                    **metadata[windows_metadata_key],
                    "run_id": windows_run_id,
                    "manifest_path": str(manifest_path) if manifest_path else None,
                    "installed_samp_sha256": windows_manifest.get("samp_sha256"),
                },
                "local_hashes_after": local_hashes_after,
                "host_observer_screenshot": host_observer_screenshot,
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
        raise WindowsSyncEdgeError("; ".join(cleanup_errors))
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
        choices=(*WINDOWS_EDGE_SCENARIOS, "all"),
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
            "role assigned by nickname to the Windows client; pilot is an "
            "explicit passenger_g-only replacement-client probe"
        ),
    )
    parser.add_argument("--windows-server-host", default="192.168.3.181")
    parser.add_argument("--windows-favorite-index", type=int, default=3)
    parser.add_argument(
        "--deploy-windows-dll",
        type=Path,
        help=(
            "explicitly validate and deploy this x86 samp.dll to Windows; "
            "omitting the flag never deploys a DLL"
        ),
    )
    parser.add_argument("--client-ready-timeout", type=float, default=60.0)
    parser.add_argument("--pair-ready-timeout", type=float, default=90.0)
    parser.add_argument("--fixture-timeout", type=float, default=60.0)
    parser.add_argument("--action-seconds", type=float, default=4.0)
    parser.add_argument("--between", type=float, default=1.0)
    parser.add_argument("--screenshot-count", type=int, default=120)
    parser.add_argument("--screenshot-interval", type=float, default=0.025)
    parser.add_argument(
        "--steer-during-capture",
        choices=("left", "right"),
        help=(
            "hold steering together with throttle during the car/trailer "
            "screenshot burst"
        ),
    )
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
    if args.windows_role == "pilot" and args.scenario != "passenger_g":
        parser.error(
            "--windows-role=pilot requires --scenario=passenger_g"
        )
    if args.windows_role == "pilot" and args.steer_during_capture is not None:
        parser.error(
            "--steer-during-capture is not valid with --windows-role=pilot"
        )

    try:
        _artifact, verdict = execute(args)
    except (
        WindowsSyncEdgeError,
        reloop.ReLoopError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Windows sync-edge probe failed: {error}", file=sys.stderr)
        return 2
    return 1 if verdict["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
