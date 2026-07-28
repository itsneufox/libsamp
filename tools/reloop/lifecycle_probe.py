#!/usr/bin/env python3
"""Reproduce and grade replacement-client connect/GMX/reconnect/quit lifecycle."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

import reloop
from control_client import ControlClient, chat_command, sample, wait_for_api


DEFAULT_CONFIG = reloop.DEFAULT_CONFIG
DEFAULT_FIXTURE_DELAY_MS = 6_000
CLIENT_LOG_NAMES = (
    "samp_runtime.log",
    "samp_net_trace.log",
    "samp_hook_trace.log",
    "samp_probe.log",
    "reloop_control.log",
    "samp_re.log",
)


@dataclass(frozen=True)
class LifecycleCheck:
    name: str
    status: str
    required: bool
    evidence: str


@dataclass
class StdinProcess:
    process: subprocess.Popen[str]
    log_handle: TextIO

    def send(self, line: str) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            raise reloop.ReLoopError("open.mp console stdin is unavailable")
        self.process.stdin.write(line.rstrip("\r\n") + "\n")
        self.process.stdin.flush()

    def stop(self, timeout: int) -> None:
        if self.process.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self.process.wait(timeout=5)
        self.log_handle.close()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _read_since(snapshot: reloop.FileSnapshot) -> str:
    try:
        stat = snapshot.path.stat()
    except FileNotFoundError:
        return ""
    offset = snapshot.size if stat.st_ino == snapshot.inode and stat.st_size >= snapshot.size else 0
    with snapshot.path.open("rb") as handle:
        handle.seek(offset)
        return handle.read().decode("utf-8", "replace")


def _ordered(text: str, *patterns: str) -> bool:
    offset = 0
    for pattern in patterns:
        match = re.search(pattern, text[offset:], re.MULTILINE)
        if match is None:
            return False
        offset += match.end()
    return True


def _event_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in _read(path).splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _event_seen(records: list[dict[str, Any]], state: str, **fields: Any) -> bool:
    return any(
        record.get("state") == state
        and all(record.get(key) == value for key, value in fields.items())
        for record in records
    )


def _check(name: str, ok: bool, evidence: str, required: bool = True) -> LifecycleCheck:
    return LifecycleCheck(name, "PASS" if ok else "FAIL", required, evidence)


def analyze_lifecycle(run_dir: Path, write_outputs: bool = True) -> dict[str, Any]:
    """Analyze only evidence captured inside one lifecycle artifact directory."""
    runtime = _read(run_dir / "client/samp_runtime.log")
    net = _read(run_dir / "client/samp_net_trace.log")
    probe = _read(run_dir / "client/samp_probe.log")
    hook = _read(run_dir / "client/samp_hook_trace.log")
    server_console = _read(run_dir / "server.console.log")
    server_results = _read(run_dir / "server-results.log")
    events = _event_records(run_dir / "lifecycle-events.jsonl")
    client_combined = "\n".join((runtime, net, probe, hook))

    rpc40_index = net.find("rpc-in id=40")
    init_indices = [match.start() for match in re.finditer(r"rpc-in id=139\b", net)]
    restart_index = runtime.find("client_control: session_reset reason=gamemode_restart")
    textdraw_index = runtime.find("textdraw: show")
    menu_index = runtime.find("menu_overlay: active")
    object_index = runtime.find("object: bridge active")
    remote_join_index = net.find("rpc-in id=137")

    checks: list[LifecycleCheck] = [
        _check(
            "runner_completed",
            _event_seen(events, "RUNNER_DONE") and not _event_seen(events, "RUNNER_ERROR"),
            "lifecycle-events.jsonl has RUNNER_DONE and no RUNNER_ERROR",
        ),
        _check(
            "initial_init_before_gmx",
            len(init_indices) >= 1 and rpc40_index > init_indices[0],
            f"InitGame indices={init_indices[:3]}, RPC40 index={rpc40_index}",
        ),
        _check(
            "initial_spawn_before_reset",
            _ordered(
                runtime,
                r"mp_session_bridge: spawn_finalize\b",
                r"client_control: session_reset reason=gamemode_restart\b",
            ),
            "runtime spawn_finalize precedes gamemode_restart session_reset",
        ),
        _check(
            "textdraw_precondition",
            0 <= textdraw_index < restart_index,
            f"textdraw show index={textdraw_index}, reset index={restart_index}",
        ),
        _check(
            "menu_precondition",
            0 <= menu_index < restart_index,
            f"menu active index={menu_index}, reset index={restart_index}",
        ),
        _check(
            "object_precondition",
            0 <= object_index < restart_index,
            f"object bridge index={object_index}, reset index={restart_index}",
        ),
        _check(
            "remote_player_metadata_precondition",
            0 <= remote_join_index < rpc40_index,
            f"ScrServerJoin index={remote_join_index}, RPC40 index={rpc40_index}",
        ),
        _check(
            "rpc40_received",
            rpc40_index >= 0,
            f"rpc-in id=40 index={rpc40_index}",
        ),
        _check(
            "adapter_session_reset",
            "rpc-state id=40" in net
            and "session_probe_reset=1" in net
            and "transport_preserved=1" in net,
            "RPC adapter reports session_probe_reset=1 and transport_preserved=1",
        ),
        _check(
            "runtime_session_reset",
            restart_index >= 0 and "session_reset=complete" in runtime[restart_index:],
            f"gamemode_restart reset index={restart_index}, session_reset=complete follows",
        ),
        _check(
            "consumer_generation_reset",
            restart_index >= 0
            and runtime.find("client_control: consumers_reset", restart_index) >= 0,
            "consumer-local sequence latches reset after session generation change",
        ),
        _check(
            "post_gmx_init",
            len(init_indices) >= 2 and rpc40_index < init_indices[1],
            f"InitGame indices={init_indices[:3]}, RPC40 index={rpc40_index}",
        ),
        _check(
            "post_gmx_spawn",
            restart_index >= 0
            and runtime.find("mp_session_bridge: spawn_finalize", restart_index) >= 0,
            "a second spawn_finalize follows the GMX reset",
        ),
        _check(
            "menu_cleanup",
            restart_index >= 0
            and re.search(
                r"menu_native: hidden[^\n]*reason=gamemode_restart", runtime[: restart_index + 1]
            )
            is not None,
            "active legacy menu is explicitly hidden with reason=gamemode_restart",
        ),
        _check(
            "object_cleanup",
            restart_index >= 0
            and re.search(
                r"object: destroy(?:_pending)?[^\n]*reason=gamemode_restart",
                runtime[: restart_index + 1],
            )
            is not None,
            "at least one active/pending object is explicitly destroyed by GMX reset",
        ),
        _check(
            "quit_exitprocess_sequence",
            _ordered(
                runtime,
                r"chat_input: local quit command\b",
                r"chat_input: quit_after_frame[^\n]*action=network_shutdown\b",
                r"chat_input: quit_after_frame action=ExitProcess code=0\b",
            ),
            "real /q path reaches delayed network shutdown and ExitProcess(0)",
        ),
        _check(
            "native_process_exit",
            _event_seen(events, "CLIENT_NATIVE_EXIT", clean=True),
            "runner observed no remaining GTA/SA-MP process before fallback termination",
        ),
        _check(
            "no_client_exception",
            "exception_filter" not in client_combined
            and "unhandled page fault" not in client_combined.lower(),
            "no exception_filter or Wine unhandled-page-fault marker",
        ),
    ]

    cleanup_matches = re.findall(r"call:\s+WSACleanup[^\n]*\brc=(-?\d+)", probe)
    startup_matches = re.findall(r"call:\s+WSAStartup[^\n]*\brc=(-?\d+)", probe)
    cleanup_failures = [result for result in cleanup_matches if result != "0"]
    checks.append(
        _check(
            "winsock_cleanup_valid",
            bool(cleanup_matches) and not cleanup_failures,
            "WSAStartup(success)={} WSACleanup(success)={} WSACleanup(fail)={}; "
            "counts are diagnostic because RakNet and the module own separate references".format(
                startup_matches.count("0"), cleanup_matches.count("0"), len(cleanup_failures)
            ),
        )
    )

    process_detach_seen = "process_detach: done" in runtime
    exitprocess_seen = "chat_input: quit_after_frame action=ExitProcess code=0" in runtime
    if process_detach_seen:
        process_detach_class = "OBSERVED"
    elif exitprocess_seen:
        process_detach_class = "EXPECTED_ABSENT_EXITPROCESS"
    else:
        process_detach_class = "MISSING_WITHOUT_EXITPROCESS"

    reset_suffix = runtime[restart_index:] if restart_index >= 0 else ""
    textdraw_zero_logged = re.search(r"\btextdraws=0\b", reset_suffix) is not None
    checks.append(
        LifecycleCheck(
            "textdraw_visual_cleanup",
            "PASS" if textdraw_zero_logged else "MANUAL",
            False,
            (
                "post-reset renderer state logged textdraws=0"
                if textdraw_zero_logged
                else "pool reset ran, but no post-reset textdraw-count/visual oracle is logged"
            ),
        )
    )

    remote_destroy_logged = (
        re.search(
            r"remote_player: destroy(?:_pending)?[^\n]*reason=gamemode_restart",
            runtime[: restart_index + 1] if restart_index >= 0 else runtime,
        )
        is not None
    )
    checks.append(
        LifecycleCheck(
            "remote_player_physical_cleanup",
            "PASS" if remote_destroy_logged else "MANUAL",
            False,
            (
                "an active/pending remote physical slot was explicitly destroyed"
                if remote_destroy_logged
                else "ScrServerJoin metadata was present, but no streamed remote ped existed to provide a physical-destroy oracle"
            ),
        )
    )
    checks.append(
        LifecycleCheck(
            "process_detach_classification",
            "PASS" if process_detach_seen else "INFO",
            False,
            process_detach_class,
        )
    )

    required_failures = [
        check.name for check in checks if check.required and check.status != "PASS"
    ]
    manual_checks = [check.name for check in checks if check.status == "MANUAL"]
    informational_checks = [check.name for check in checks if check.status == "INFO"]
    if required_failures:
        verdict = "FAIL"
    elif manual_checks:
        verdict = "PASS_WITH_MANUAL_VISUAL"
    else:
        verdict = "PASS"

    result = {
        "verdict": verdict,
        "run_dir": str(run_dir),
        "checks": [asdict(check) for check in checks],
        "required_failures": required_failures,
        "manual_checks": manual_checks,
        "informational_checks": informational_checks,
        "diagnostics": {
            "init_game_count": len(init_indices),
            "rpc40_count": len(re.findall(r"rpc-in id=40\b", net)),
            "scr_server_join_count": len(re.findall(r"rpc-in id=137\b", net)),
            "spawn_finalize_count": len(
                re.findall(r"mp_session_bridge: spawn_finalize\b", runtime)
            ),
            "wsa_startup_success_count": startup_matches.count("0"),
            "wsa_cleanup_success_count": cleanup_matches.count("0"),
            "wsa_cleanup_failure_count": len(cleanup_failures),
            "process_detach": process_detach_class,
            "server_gmx_command_seen": _event_seen(events, "GMX_SENT"),
            "server_console_bytes": len(server_console.encode("utf-8")),
            "server_result_bytes": len(server_results.encode("utf-8")),
        },
        "automation_boundary": {
            "automated": [
                "connect/initial InitGame and spawn ordering",
                "RPC40 adapter/runtime generation reset and transport preservation",
                "post-GMX InitGame and spawn",
                "menu/object reset markers",
                "real /q delayed ExitProcess and native process exit",
                "invalid WSACleanup and client exception detection",
            ],
            "manual_or_companion_required": [
                "pixel-level absence of old TextDraw after GMX",
                "physical remote-ped destruction when no companion was streamed",
                "process_detach is normally not observable after ExitProcess termination",
            ],
        },
    }
    if write_outputs:
        reloop.write_json(run_dir / "lifecycle-verdict.json", result)
        lines = [
            "# lifecycle probe",
            "",
            f"- Verdict: **{verdict}**",
            f"- Required failures: `{', '.join(required_failures) or 'none'}`",
            f"- Manual checks: `{', '.join(manual_checks) or 'none'}`",
            f"- Informational checks: `{', '.join(informational_checks) or 'none'}`",
            f"- Process detach: `{process_detach_class}`",
            "",
            "## Checks",
            "",
        ]
        lines.extend(
            f"- `{check.status}` {check.name}: {check.evidence}" for check in checks
        )
        lines.extend(
            [
                "",
                "## Automation boundary",
                "",
                "- Automated: RPC/lifecycle ordering, reset markers, `/q`, native exit, "
                "Winsock failures and crashes.",
                "- Manual/companion: pixel-level TextDraw disappearance and physical "
                "remote-ped cleanup when only NPC metadata was observed.",
                "",
            ]
        )
        (run_dir / "lifecycle-summary.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )
    return result


def _wait_until(
    label: str,
    predicate: Callable[[], bool],
    timeout_s: float,
    events: Path,
    process: subprocess.Popen[Any] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            reloop.append_event(events, label)
            return
        if process is not None and process.poll() is not None:
            raise reloop.ReLoopError(
                f"{label} failed because process exited with {process.returncode}"
            )
        time.sleep(0.2)
    raise reloop.ReLoopError(f"timed out waiting for {label} after {timeout_s:.1f}s")


def _start_server(settings: reloop.Settings, log_path: Path) -> StdinProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8", buffering=1)
    process = subprocess.Popen(
        [str(settings.server_executable)],
        cwd=settings.server_root,
        stdin=subprocess.PIPE,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return StdinProcess(process, log_handle)


def _prefix_game_pids(prefix: Path) -> set[int]:
    needle = str(prefix.resolve()).encode()
    result: set[int] = set()
    for pid, executable, arguments, environment in reloop.process_info():
        if needle not in environment:
            continue
        command = " ".join(arguments).lower()
        executable_name = executable.name.lower() if executable is not None else ""
        if (
            "gta_sa.exe" in command
            or "samp.exe" in command
            or executable_name in {"gta_sa.exe", "samp.exe"}
        ):
            result.add(pid)
    return result


def _capture_logs(
    snapshots: dict[str, reloop.FileSnapshot], artifact_dir: Path
) -> None:
    for name, snapshot in snapshots.items():
        snapshot.capture_append(artifact_dir / "client" / name)


def _click_replacement_spawn_button(
    control: ControlClient, state: dict[str, Any]
) -> None:
    """Click the replacement class-selection overlay's fixed R5 Spawn control."""
    width = int(state["client_w"])
    height = int(state["client_h"])
    dialog_width = 310
    dialog_height = 40
    bottom_margin = 50
    spawn_offset_x = 210
    button_offset_y = 5
    button_width = 90
    button_height = 30
    dialog_x = (width - dialog_width) // 2
    dialog_y = height - dialog_height - bottom_margin
    control.command(
        "mouse",
        action="click",
        x=dialog_x + spawn_offset_x + (button_width // 2),
        y=dialog_y + button_offset_y + (button_height // 2),
    )


def run_lifecycle(
    settings: reloop.Settings,
    fixture_delay_ms: int,
    timeout_s: int,
    build: bool,
    deploy: bool,
) -> tuple[Path, dict[str, Any]]:
    if not 2_000 <= fixture_delay_ms <= 10_000:
        raise reloop.ReLoopError("fixture delay must be between 2000 and 10000 ms")

    profile = settings.clients["replacement"]
    artifact_dir = settings.artifacts_root / reloop.run_id(
        "replacement", "lifecycle-gmx"
    )
    artifact_dir.mkdir(parents=True, exist_ok=False)
    events = artifact_dir / "lifecycle-events.jsonl"
    current_request = reloop.request_id()
    request_file = settings.server_root / "scriptfiles/test_cmds_request.txt"
    result_file = settings.server_root / "scriptfiles/test_cmds_results.log"
    states: list[dict[str, Any]] = []
    server: StdinProcess | None = None
    client: reloop.ManagedProcess | None = None
    control: ControlClient | None = None
    pre_prefix_pids: set[int] = set()
    runner_error: str | None = None

    reloop.write_json(
        artifact_dir / "metadata.json",
        {
            "run_id": artifact_dir.name,
            "started_at": reloop.utc_timestamp(),
            "request_id": current_request,
            "scenario": "connect_spawn-gmx-session_reset-respawn-q",
            "fixture": "existing test_cmds ui request plus bare /menutest",
            "fixture_delay_ms": fixture_delay_ms,
            "prefix": str(profile.prefix),
            "dll_sha256_before_build": reloop.sha256(profile.samp_dll),
            "evidence": ["PROBE_TRACE", "STATIC_037", "TODO_VERIFY"],
        },
    )
    reloop.append_event(events, "PREPARE", artifact=str(artifact_dir))

    try:
        reloop.replace_existing_client(
            profile, "replace", settings.shutdown_timeout_s
        )
        reloop.replace_existing_server(settings, "replace")
        if build:
            reloop.append_event(events, "BUILD_DLL")
            # The existing Pawn fixture is deliberately not rebuilt or modified.
            reloop.build_all(settings, artifact_dir / "build", dll=True, pawn=False)
        if deploy:
            reloop.append_event(events, "DEPLOY_DLL")
            reloop.deploy_replacement(settings, artifact_dir / "build")
        reloop.install_device_helper(settings, profile, artifact_dir / "build")
        reloop.install_control_helper(profile, artifact_dir / "build")
        if not settings.pawn_output.is_file():
            raise reloop.ReLoopError(
                f"existing test_cmds AMX fixture is missing: {settings.pawn_output}"
            )

        request_file.parent.mkdir(parents=True, exist_ok=True)
        request_file.write_text(
            f"{current_request} ui {fixture_delay_ms} 1 {settings.nickname}\n",
            encoding="ascii",
        )
        result_snapshot = reloop.FileSnapshot.take(result_file)
        client_snapshots = {
            name: reloop.FileSnapshot.take(profile.gta_root / name)
            for name in CLIENT_LOG_NAMES
        }
        pre_prefix_pids = reloop.prefix_pids(profile.prefix)
        reloop.append_event(events, "REQUEST_QUEUED", request=current_request)

        server = _start_server(settings, artifact_dir / "server.console.log")
        _wait_until(
            "SERVER_READY",
            lambda: reloop.SERVER_READY_PATTERN.search(
                _read(artifact_dir / "server.console.log")
            )
            is not None,
            settings.server_ready_timeout_s,
            events,
            server.process,
        )

        command, environment = reloop.direct_client_launch(
            settings, profile, artifact_dir / "launcher"
        )
        reloop.append_event(events, "CLIENT_START", command=shlex.join(command))
        client = reloop.start_process(
            command,
            profile.gta_root,
            artifact_dir / "client-launcher.log",
            "SA-MP replacement",
            env=environment,
        )

        runtime_snapshot = client_snapshots["samp_runtime.log"]
        net_snapshot = client_snapshots["samp_net_trace.log"]
        _wait_until(
            "INITIAL_SPAWN",
            lambda: "mp_session_bridge: spawn_finalize" in _read_since(runtime_snapshot),
            min(timeout_s, 70),
            events,
        )
        control = wait_for_api(timeout=min(timeout_s, 45))
        control.command("focus")
        sample(control, "initial_spawn", states)

        _wait_until(
            "UI_TEXTDRAW_ACTIVE",
            lambda: "event=ui_textdraw" in _read_since(result_snapshot)
            and "textdraw: show" in _read_since(runtime_snapshot),
            min(timeout_s, 75),
            events,
        )
        chat_command(control, "/menutest")
        _wait_until(
            "MENU_ACTIVE",
            lambda: "menu_overlay: active" in _read_since(runtime_snapshot),
            8,
            events,
        )
        _wait_until(
            "OBJECT_AND_REMOTE_PRECONDITIONS",
            lambda: "object: bridge active" in _read_since(runtime_snapshot)
            and "rpc-in id=137" in _read_since(net_snapshot),
            8,
            events,
        )
        sample(control, "pre_gmx_active_ui", states)

        server.send("gmx")
        reloop.append_event(events, "GMX_SENT", source="open.mp_console")
        _wait_until(
            "RPC40_RESET",
            lambda: "rpc-in id=40" in _read_since(net_snapshot)
            and "rpc-state id=40" in _read_since(net_snapshot)
            and "client_control: session_reset reason=gamemode_restart"
            in _read_since(runtime_snapshot),
            20,
            events,
            server.process,
        )
        _wait_until(
            "POST_GMX_INIT",
            lambda: len(
                re.findall(r"rpc-in id=139\b", _read_since(net_snapshot))
            )
            >= 2,
            30,
            events,
            server.process,
        )
        post_gmx_state = sample(control, "post_gmx_pre_spawn", states)

        respawn_deadline = time.monotonic() + 35
        while time.monotonic() < respawn_deadline:
            runtime = _read_since(runtime_snapshot)
            reset_at = runtime.find(
                "client_control: session_reset reason=gamemode_restart"
            )
            if reset_at >= 0 and runtime.find(
                "mp_session_bridge: spawn_finalize", reset_at
            ) >= 0:
                break
            control.command("focus")
            _click_replacement_spawn_button(control, post_gmx_state)
            time.sleep(1.0)
        else:
            raise reloop.ReLoopError("post-GMX spawn_finalize was not observed")
        reloop.append_event(events, "POST_GMX_SPAWN")
        sample(control, "post_gmx_spawn", states)

        chat_command(control, "/q")
        _wait_until(
            "QUIT_EXITPROCESS",
            lambda: "chat_input: quit_after_frame action=ExitProcess code=0"
            in _read_since(runtime_snapshot),
            15,
            events,
        )
        native_deadline = time.monotonic() + settings.shutdown_timeout_s
        while time.monotonic() < native_deadline and _prefix_game_pids(profile.prefix):
            time.sleep(0.2)
        native_clean = not _prefix_game_pids(profile.prefix)
        reloop.append_event(
            events,
            "CLIENT_NATIVE_EXIT",
            clean=native_clean,
            remaining_game_pids=sorted(_prefix_game_pids(profile.prefix)),
        )
        if not native_clean:
            raise reloop.ReLoopError("GTA/SA-MP process remained after /q")
        reloop.append_event(events, "RUNNER_DONE")
    except Exception as error:  # Keep partial evidence analyzable.
        runner_error = f"{type(error).__name__}: {error}"
        reloop.append_event(events, "RUNNER_ERROR", error=runner_error)
    finally:
        if control is not None:
            with contextlib.suppress(Exception):
                control.close()
        with contextlib.suppress(FileNotFoundError):
            request_file.unlink()
        if client is not None:
            client.stop(settings.shutdown_timeout_s)
        remaining_prefix_pids = reloop.prefix_pids(profile.prefix) - pre_prefix_pids
        if remaining_prefix_pids:
            reloop.terminate_pids(remaining_prefix_pids, settings.shutdown_timeout_s)
        if server is not None:
            server.stop(settings.shutdown_timeout_s)

        if "client_snapshots" in locals():
            _capture_logs(client_snapshots, artifact_dir)
        if "result_snapshot" in locals():
            result_snapshot.capture_append(artifact_dir / "server-results.log")
        reloop.write_json(artifact_dir / "client-states.json", states)
        reloop.write_json(
            artifact_dir / "runner-result.json",
            {
                "finished_at": reloop.utc_timestamp(),
                "runner_error": runner_error,
            },
        )

    verdict = analyze_lifecycle(artifact_dir)
    print(f"artifact: {artifact_dir}")
    print(f"verdict: {verdict['verdict']}")
    return artifact_dir, verdict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze", help="grade a previously captured lifecycle artifact"
    )
    analyze_parser.add_argument("run_dir", type=Path)

    run_parser = subparsers.add_parser(
        "run", help="run connect/spawn -> GMX -> respawn -> /q on replacement"
    )
    run_parser.add_argument("--fixture-delay", type=int, default=DEFAULT_FIXTURE_DELAY_MS)
    run_parser.add_argument("--timeout", type=int, default=120)
    run_parser.add_argument("--no-build", action="store_true")
    run_parser.add_argument("--no-deploy", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        result = analyze_lifecycle(args.run_dir)
    else:
        settings = reloop.load_settings(args.config)
        _run_dir, result = run_lifecycle(
            settings,
            fixture_delay_ms=args.fixture_delay,
            timeout_s=args.timeout,
            build=not args.no_build,
            deploy=not args.no_deploy,
        )
    return 0 if result["verdict"] in {"PASS", "PASS_WITH_MANUAL_VISUAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
