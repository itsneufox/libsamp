#!/usr/bin/env python3
"""Run the Packet 209/210/211 two-prefix sync fixture and collect evidence.

The pilot is launched first and must own reloop_control's fixed localhost
endpoint before the observer starts.  The runner deliberately does not install,
disable, rename, or replace ASIs in either prefix; their hashes are recorded
before and after the run so an interrupted probe cannot leave a prefix altered.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import reloop  # noqa: E402
from control_client import wait_for_api  # noqa: E402


EDGE_SCENARIOS = ("passenger", "unoccupied", "trailer")
PASSENGER_G_SCENARIO = "passenger_g"
SUPPORTED_EDGE_SCENARIOS = (*EDGE_SCENARIOS, PASSENGER_G_SCENARIO)
CONTROL_PORT = 18737
AUTOPAUSE_INI = "III.VC.SA.WindowedMode.ini"
CRASH_MARKERS = ("exception_filter", "unhandled page fault")


@dataclasses.dataclass(frozen=True)
class EdgeEvidence:
    packet_id: int
    runtime_pattern: str
    server_marker: str


EVIDENCE = {
    "passenger": EdgeEvidence(
        211,
        r"remote_passenger: apply[^\r\n]*\bseated=1\b[^\r\n]*\bseat_read=1\b",
        "scenario=passenger",
    ),
    "passenger_g": EdgeEvidence(
        211,
        r"remote_passenger: apply[^\r\n]*\bseated=1\b[^\r\n]*\bseat_read=1\b",
        "marker=PASSENGER_ENTRY_RESULT",
    ),
    "unoccupied": EdgeEvidence(
        209,
        r"remote_unoccupied: apply[^\r\n]*\breadback=1\b",
        "marker=UNOCCUPIED_UPDATE",
    ),
    "trailer": EdgeEvidence(
        210,
        r"remote_trailer: apply[^\r\n]*\battached=1\b[^\r\n]*\breadback=1\b",
        "marker=TRAILER_UPDATE",
    ),
}


class SyncEdgeError(RuntimeError):
    """Expected operator-facing edge-probe failure."""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_hashes(root: Path) -> dict[str, str | None]:
    """Snapshot every top-level ASI by relative name without changing it."""
    return {
        path.name: reloop.sha256(path)
        for path in sorted(root.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() == ".asi"
    }


def autopause_disabled(path: Path) -> bool:
    """Return whether [game] explicitly contains autoPause=0."""
    if not path.is_file():
        return False
    section = ""
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section != "game" or "=" not in line:
            continue
        key, value = (part.strip().lower() for part in line.split("=", 1))
        value = value.split(";", 1)[0].split("#", 1)[0].strip()
        if key == "autopause":
            return value == "0"
    return False


def tcp_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def appended_text(path: Path, snapshot: reloop.FileSnapshot) -> str:
    if not path.is_file():
        return ""
    current = path.stat()
    offset = (
        snapshot.size
        if current.st_ino == snapshot.inode and current.st_size >= snapshot.size
        else 0
    )
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read().decode("utf-8", errors="replace")


def wait_for_pair(
    console_path: Path,
    server_log: Path,
    server_snapshot: reloop.FileSnapshot,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        console = (
            console_path.read_text(encoding="utf-8", errors="replace")
            if console_path.is_file()
            else ""
        )
        text = console + "\n" + appended_text(server_log, server_snapshot)
        if "marker=PAIR_READY" in text:
            return
        # GE-Proton's wine launcher can exit successfully after handing the
        # game to the prefix wineserver.  Its Popen lifetime is therefore not
        # the GTA process lifetime; prefix cleanup and client/server traces are
        # the authoritative liveness signals.
        time.sleep(0.25)
    raise SyncEdgeError(
        f"SyncPilot and SyncObserver did not reach PAIR_READY in {timeout_seconds:.1f}s"
    )


def _contains_crash(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in CRASH_MARKERS)


def evaluate_evidence(
    scenarios: list[str],
    server_text: str,
    observer_logs: str,
    observer_is_replacement: bool,
    driver_returncodes: dict[str, int],
) -> dict[str, Any]:
    """Reduce trace artifacts conservatively; this never claims visual parity."""
    results: dict[str, Any] = {}
    hard_failure = _contains_crash(observer_logs)
    for scenario in scenarios:
        contract = EVIDENCE[scenario]
        checks = {
            "driver_completed": driver_returncodes.get(scenario) == 0,
            "server_scenario_seen": contract.server_marker in server_text,
        }
        if scenario in {"passenger", PASSENGER_G_SCENARIO}:
            checks["server_passenger_state_seen"] = bool(
                re.search(
                    rf"marker=PILOT_SYNC scenario={scenario}\b.*\bstate=3\b",
                    server_text,
                )
            )
        if scenario == PASSENGER_G_SCENARIO:
            request_match = re.search(
                r"marker=PASSENGER_ENTER_REQUEST\b[^\r\n]*"
                r"\bstatus=ACTION\b[^\r\n]*\bscenario=passenger_g\b"
                r"[^\r\n]*\brpc=26\b[^\r\n]*\bvehicle=(\d+)\b"
                r"[^\r\n]*\bexpected_vehicle=(\d+)\b"
                r"[^\r\n]*\bis_passenger=1\b",
                server_text,
            )
            result_match = re.search(
                r"marker=PASSENGER_ENTRY_RESULT\b[^\r\n]*"
                r"\bstatus=PASS\b[^\r\n]*\bscenario=passenger_g\b"
                r"[^\r\n]*\brpc=26\b[^\r\n]*\benter_seen=1\b"
                r"[^\r\n]*\benter_vehicle=(\d+)\b"
                r"[^\r\n]*\bis_passenger=1\b[^\r\n]*\bvehicle=(\d+)\b"
                r"[^\r\n]*\bseat=1\b[^\r\n]*\bstate=3\b",
                server_text,
            )
            checks["server_rpc26_passenger_request_seen"] = bool(request_match)
            checks["server_passenger_entry_verified"] = bool(result_match)
            checks["server_passenger_vehicle_verified"] = bool(
                request_match
                and result_match
                and request_match.group(1) == request_match.group(2)
                and request_match.group(1) == result_match.group(1)
                and request_match.group(1) == result_match.group(2)
            )
        if observer_is_replacement:
            checks["observer_packet_decoded"] = (
                f"packet-state id={contract.packet_id} " in observer_logs
            )
            checks["observer_runtime_apply_seen"] = bool(
                re.search(contract.runtime_pattern, observer_logs)
            )
            checks["observer_edge_consumed"] = bool(
                re.search(
                    rf"remote_edge: consume[^\r\n]*\bpacket={contract.packet_id}\b"
                    rf"[^\r\n]*\bresult=applied\b",
                    observer_logs,
                )
            )
        results[scenario] = {
            "packet_id": contract.packet_id,
            "checks": checks,
            "verdict": "TRACE_PASS" if all(checks.values()) else "FAIL",
        }
        hard_failure = hard_failure or not all(checks.values())

    if hard_failure:
        verdict = "FAIL"
    elif observer_is_replacement:
        verdict = "TRACE_PASS_VISUAL_UNVERIFIED"
    else:
        verdict = "SERVER_TRACE_PASS_OBSERVER_INTERNALS_UNAVAILABLE"
    return {
        "verdict": verdict,
        "visual_parity": "TODO_VERIFY",
        "scenarios": results,
        "observer_crash_marker": _contains_crash(observer_logs),
    }


def collect_logs(
    destination: Path,
    snapshots: dict[str, reloop.FileSnapshot],
    capture_errors: list[str] | None = None,
) -> str:
    combined = ""
    for name, snapshot in snapshots.items():
        target = destination / name
        try:
            if snapshot.capture_append(target):
                combined += target.read_text(encoding="utf-8", errors="replace") + "\n"
        except Exception as error:
            if capture_errors is None:
                raise
            capture_errors.append(f"{name}: {type(error).__name__}: {error}")
    return combined


def finalize_artifact(
    *,
    artifact_dir: Path,
    metadata: dict[str, Any],
    scenarios: list[str],
    server_console: Path,
    server_snapshot: reloop.FileSnapshot,
    result_snapshot: reloop.FileSnapshot,
    pilot_snapshots: dict[str, reloop.FileSnapshot],
    observer_snapshots: dict[str, reloop.FileSnapshot],
    pilot: reloop.ClientProfile,
    observer: reloop.ClientProfile,
    asi_before: dict[str, dict[str, str | None]],
    driver_returncodes: dict[str, int],
    runner_error: str | None,
    teardown_errors: list[str],
    capture_complete: bool,
) -> dict[str, Any]:
    """Write a self-contained checkpoint before and after process teardown."""
    capture_errors: list[str] = []

    for label, snapshot, destination in (
        ("server.log", server_snapshot, artifact_dir / "server.log"),
        (
            "sync-pair-results.log",
            result_snapshot,
            artifact_dir / "sync-pair-results.log",
        ),
    ):
        try:
            snapshot.capture_append(destination)
        except Exception as error:
            capture_errors.append(f"{label}: {type(error).__name__}: {error}")

    pilot_logs = collect_logs(
        artifact_dir / "pilot" / "client",
        pilot_snapshots,
        capture_errors,
    )
    observer_logs = collect_logs(
        artifact_dir / "observer" / "client",
        observer_snapshots,
        capture_errors,
    )
    console_text = (
        server_console.read_text(encoding="utf-8", errors="replace")
        if server_console.is_file()
        else ""
    )
    captured_server = artifact_dir / "server.log"
    server_append = (
        captured_server.read_text(encoding="utf-8", errors="replace")
        if captured_server.is_file()
        else ""
    )
    verdict = evaluate_evidence(
        scenarios,
        console_text + "\n" + server_append,
        observer_logs,
        observer.name == "replacement",
        driver_returncodes,
    )
    verdict.update(
        {
            "finished_at": reloop.utc_timestamp(),
            "artifact_complete": capture_complete,
            "runner_error": runner_error,
            "teardown_errors": list(teardown_errors),
            "capture_errors": capture_errors,
            "pilot_crash_marker": _contains_crash(pilot_logs),
            "driver_returncodes": driver_returncodes,
        }
    )
    if runner_error or teardown_errors or capture_errors or verdict["pilot_crash_marker"]:
        verdict["verdict"] = "FAIL"
    elif not capture_complete:
        verdict["verdict"] = "INCOMPLETE_TEARDOWN"

    asi_after = {
        "pilot": file_hashes(pilot.gta_root),
        "observer": file_hashes(observer.gta_root),
    }
    verdict["asi_hashes_unchanged"] = asi_after == asi_before
    if not verdict["asi_hashes_unchanged"]:
        verdict["verdict"] = "FAIL"
    metadata["asi_hashes_after"] = asi_after
    metadata["artifact_complete"] = capture_complete
    write_json(artifact_dir / "metadata.json", metadata)
    write_json(artifact_dir / "verdict.json", verdict)
    return verdict


def validate_layout(
    settings: reloop.Settings,
    pilot: reloop.ClientProfile,
    observer: reloop.ClientProfile,
) -> dict[str, Any]:
    if pilot.name == observer.name or pilot.prefix.resolve() == observer.prefix.resolve():
        raise SyncEdgeError("pilot and observer must use distinct prefixes")
    if not reloop.CONTROL_ASI.is_file():
        raise SyncEdgeError(f"control helper is not built: {reloop.CONTROL_ASI}")
    installed_control = pilot.gta_root / reloop.CONTROL_ASI.name
    expected_hash = reloop.sha256(reloop.CONTROL_ASI)
    actual_hash = reloop.sha256(installed_control)
    if actual_hash is None:
        raise SyncEdgeError(
            f"pilot control ASI is missing; install it before the probe: {installed_control}"
        )
    for profile in (pilot, observer):
        if not profile.samp_exe.is_file() or not profile.samp_dll.is_file():
            raise SyncEdgeError(f"{profile.name} GTA/SA-MP layout is incomplete")
        ini = profile.gta_root / AUTOPAUSE_INI
        if not autopause_disabled(ini):
            raise SyncEdgeError(f"{profile.name} requires [game] autoPause = 0 in {ini}")
    return {
        "pilot_control_path": str(installed_control),
        "pilot_control_sha256": actual_hash,
        "built_control_sha256": expected_hash,
        "pilot_control_matches_current_build": actual_hash == expected_hash,
        "pilot_autopause": True,
        "observer_autopause": True,
        "control_strategy": (
            "pilot launched and API-verified before observer; no ASI file is modified"
        ),
    }


def run_driver(
    scenario: str,
    artifact_dir: Path,
    timeout_seconds: float,
    action_seconds: float,
) -> tuple[int, Path]:
    output_path = artifact_dir / "driver" / f"{scenario}.json"
    console_path = artifact_dir / "driver" / f"{scenario}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(SCRIPT_DIR / "sync_pair_client.py"),
        scenario,
        "--output",
        str(output_path),
        "--action-seconds",
        str(action_seconds),
        "--sync-pair-request-timeout",
        str(timeout_seconds),
    ]
    with console_path.open("wb") as handle:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds + action_seconds + 20.0,
            check=False,
        )
    return completed.returncode, console_path


def execute(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    settings = reloop.load_settings(args.config.resolve())
    pilot = settings.clients[args.pilot]
    observer = settings.clients[args.observer]
    scenarios = list(EDGE_SCENARIOS if args.scenario == "all" else (args.scenario,))
    artifact_dir = settings.artifacts_root / reloop.run_id("sync-edge", args.scenario)
    artifact_dir.mkdir(parents=True, exist_ok=False)
    # Automation normally block-buffers stdout.  Publish and flush the path
    # before client startup/teardown so a long Wine shutdown is not mistaken
    # for a runner that failed to create an artifact.
    print(f"artifact: {artifact_dir}", flush=True)

    layout = validate_layout(settings, pilot, observer)
    asi_before = {
        "pilot": file_hashes(pilot.gta_root),
        "observer": file_hashes(observer.gta_root),
    }
    metadata = {
        "run_id": artifact_dir.name,
        "started_at": reloop.utc_timestamp(),
        "pilot": pilot.name,
        "pilot_prefix": str(pilot.prefix),
        "pilot_nickname": "SyncPilot",
        "pilot_dll_sha256": reloop.sha256(pilot.samp_dll),
        "observer": observer.name,
        "observer_prefix": str(observer.prefix),
        "observer_nickname": "SyncObserver",
        "observer_dll_sha256": reloop.sha256(observer.samp_dll),
        "scenarios": scenarios,
        "host": settings.host,
        "port": settings.port,
        "server_mode": args.server_mode,
        "client_mode": args.client_mode,
        "layout": layout,
        "asi_hashes_before": asi_before,
    }
    write_json(artifact_dir / "metadata.json", metadata)

    request_path = settings.server_root / "scriptfiles/sync_pair_request.txt"
    if request_path.exists():
        raise SyncEdgeError(f"sync-pair request is already pending: {request_path}")
    fixture = settings.server_root / "filterscripts/sync_pair.amx"
    if not fixture.is_file():
        raise SyncEdgeError(f"sync-pair fixture is not compiled: {fixture}")

    reloop.replace_existing_client(pilot, args.client_mode, settings.shutdown_timeout_s)
    reloop.replace_existing_client(observer, args.client_mode, settings.shutdown_timeout_s)
    if not tcp_port_available("127.0.0.1", CONTROL_PORT):
        raise SyncEdgeError(
            f"localhost control port {CONTROL_PORT} is already occupied after "
            "client preflight; refusing to risk driving the wrong client"
        )
    reused_server = reloop.replace_existing_server(settings, args.server_mode)

    server_log = settings.server_root / "log.txt"
    result_file = settings.server_root / "scriptfiles/sync_pair_results.log"
    server_snapshot = reloop.FileSnapshot.take(server_log)
    result_snapshot = reloop.FileSnapshot.take(result_file)
    pilot_snapshots = {
        name: reloop.FileSnapshot.take(pilot.gta_root / name)
        for name in reloop.CLIENT_LOG_NAMES
    }
    observer_snapshots = {
        name: reloop.FileSnapshot.take(observer.gta_root / name)
        for name in reloop.CLIENT_LOG_NAMES
    }
    pilot_pre_pids = reloop.prefix_pids(pilot.prefix)
    observer_pre_pids = reloop.prefix_pids(observer.prefix)

    server: reloop.ManagedProcess | None = None
    pilot_process: reloop.ManagedProcess | None = None
    observer_process: reloop.ManagedProcess | None = None
    driver_returncodes: dict[str, int] = {}
    server_console = artifact_dir / "server.console.log"
    runner_exception: BaseException | None = None
    runner_error: str | None = None
    teardown_errors: list[str] = []
    verdict: dict[str, Any]
    try:
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
                raise SyncEdgeError("open.mp did not become ready; see server.console.log")

        pilot_command, pilot_env = reloop.direct_client_launch(
            settings, pilot, artifact_dir / "pilot-launch"
        )
        pilot_command[-1] = "-nSyncPilot"
        pilot_process = reloop.start_process(
            pilot_command,
            pilot.gta_root,
            artifact_dir / "pilot-launcher.log",
            "SyncPilot",
            env=pilot_env,
        )
        pilot_api = wait_for_api(timeout=args.client_ready_timeout)
        pilot_api.close()

        observer_command, observer_env = reloop.direct_client_launch(
            settings, observer, artifact_dir / "observer-launch"
        )
        observer_command[-1] = "-nSyncObserver"
        observer_process = reloop.start_process(
            observer_command,
            observer.gta_root,
            artifact_dir / "observer-launcher.log",
            "SyncObserver",
            env=observer_env,
        )
        write_json(
            artifact_dir / "launch-order.json",
            {
                "pilot": shlex.join(pilot_command),
                "pilot_api_verified_before_observer": True,
                "observer": shlex.join(observer_command),
            },
        )
        wait_for_pair(
            server_console,
            server_log,
            server_snapshot,
            args.pair_ready_timeout,
        )

        for scenario in scenarios:
            returncode, _console = run_driver(
                scenario,
                artifact_dir,
                args.fixture_timeout,
                args.action_seconds,
            )
            driver_returncodes[scenario] = returncode
            if returncode:
                break
            time.sleep(args.between)
    except BaseException as error:
        runner_exception = error
        runner_error = f"{type(error).__name__}: {error}"
    finally:
        # Capture before teardown as an interruption-safe checkpoint.  A
        # successful post-teardown pass below overwrites it with the complete
        # append-only slices.
        try:
            finalize_artifact(
                artifact_dir=artifact_dir,
                metadata=metadata,
                scenarios=scenarios,
                server_console=server_console,
                server_snapshot=server_snapshot,
                result_snapshot=result_snapshot,
                pilot_snapshots=pilot_snapshots,
                observer_snapshots=observer_snapshots,
                pilot=pilot,
                observer=observer,
                asi_before=asi_before,
                driver_returncodes=driver_returncodes,
                runner_error=runner_error,
                teardown_errors=teardown_errors,
                capture_complete=False,
            )
        except Exception as error:
            teardown_errors.append(
                f"pre_teardown_capture: {type(error).__name__}: {error}"
            )

        if observer_process is not None:
            try:
                observer_process.stop(settings.shutdown_timeout_s)
            except Exception as error:
                teardown_errors.append(
                    f"observer_stop: {type(error).__name__}: {error}"
                )
            try:
                reloop.terminate_pids(
                    reloop.prefix_pids(observer.prefix) - observer_pre_pids,
                    settings.shutdown_timeout_s,
                )
            except Exception as error:
                teardown_errors.append(
                    f"observer_prefix_stop: {type(error).__name__}: {error}"
                )
        if pilot_process is not None:
            try:
                pilot_process.stop(settings.shutdown_timeout_s)
            except Exception as error:
                teardown_errors.append(
                    f"pilot_stop: {type(error).__name__}: {error}"
                )
            try:
                reloop.terminate_pids(
                    reloop.prefix_pids(pilot.prefix) - pilot_pre_pids,
                    settings.shutdown_timeout_s,
                )
            except Exception as error:
                teardown_errors.append(
                    f"pilot_prefix_stop: {type(error).__name__}: {error}"
                )
        if server is not None:
            try:
                server.stop(settings.shutdown_timeout_s)
            except Exception as error:
                teardown_errors.append(
                    f"server_stop: {type(error).__name__}: {error}"
                )

        verdict = finalize_artifact(
            artifact_dir=artifact_dir,
            metadata=metadata,
            scenarios=scenarios,
            server_console=server_console,
            server_snapshot=server_snapshot,
            result_snapshot=result_snapshot,
            pilot_snapshots=pilot_snapshots,
            observer_snapshots=observer_snapshots,
            pilot=pilot,
            observer=observer,
            asi_before=asi_before,
            driver_returncodes=driver_returncodes,
            runner_error=runner_error,
            teardown_errors=teardown_errors,
            capture_complete=True,
        )

    print(f"verdict: {verdict['verdict']}", flush=True)
    if runner_exception is not None:
        raise runner_exception.with_traceback(runner_exception.__traceback__)
    if teardown_errors:
        raise SyncEdgeError("; ".join(teardown_errors))
    return artifact_dir, verdict


def analyze(path: Path) -> dict[str, Any]:
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    scenarios = list(metadata["scenarios"])
    server_text = ""
    for name in ("server.console.log", "server.log"):
        candidate = path / name
        if candidate.is_file():
            server_text += candidate.read_text(encoding="utf-8", errors="replace") + "\n"
    observer_logs = ""
    observer_dir = path / "observer" / "client"
    for name in reloop.CLIENT_LOG_NAMES:
        candidate = observer_dir / name
        if candidate.is_file():
            observer_logs += candidate.read_text(encoding="utf-8", errors="replace") + "\n"
    returncodes: dict[str, int] = {}
    old_verdict = path / "verdict.json"
    if old_verdict.is_file():
        raw = json.loads(old_verdict.read_text(encoding="utf-8"))
        returncodes = {
            str(key): int(value)
            for key, value in raw.get("driver_returncodes", {}).items()
        }
    verdict = evaluate_evidence(
        scenarios,
        server_text,
        observer_logs,
        metadata["observer"] == "replacement",
        returncodes,
    )
    write_json(path / "verdict.reanalyzed.json", verdict)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "--config", type=Path, default=reloop.DEFAULT_CONFIG
    )
    run_parser.add_argument("--pilot", choices=("original", "replacement"), default="original")
    run_parser.add_argument("--observer", choices=("original", "replacement"), default="replacement")
    run_parser.add_argument(
        "--scenario", choices=(*SUPPORTED_EDGE_SCENARIOS, "all"), default="all"
    )
    run_parser.add_argument(
        "--server-mode", choices=("fail", "replace", "reuse"), default="fail"
    )
    run_parser.add_argument(
        "--client-mode", choices=("fail", "replace"), default="fail"
    )
    run_parser.add_argument("--client-ready-timeout", type=float, default=45.0)
    run_parser.add_argument("--pair-ready-timeout", type=float, default=60.0)
    run_parser.add_argument("--fixture-timeout", type=float, default=20.0)
    run_parser.add_argument("--action-seconds", type=float, default=4.0)
    run_parser.add_argument("--between", type=float, default=1.0)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("artifact", type=Path)

    args = parser.parse_args()
    if args.command == "analyze":
        verdict = analyze(args.artifact.resolve())
        return 1 if verdict["verdict"] == "FAIL" else 0
    for field in (
        "client_ready_timeout",
        "pair_ready_timeout",
        "fixture_timeout",
        "action_seconds",
    ):
        if getattr(args, field) <= 0.0:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    if args.between < 0.0:
        parser.error("--between must not be negative")
    try:
        _artifact, verdict = execute(args)
    except (SyncEdgeError, reloop.ReLoopError, subprocess.TimeoutExpired) as exc:
        print(f"sync-edge probe failed: {exc}", file=sys.stderr)
        return 2
    return 1 if verdict["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
