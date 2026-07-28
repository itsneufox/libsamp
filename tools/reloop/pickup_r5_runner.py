#!/usr/bin/env python3
"""Run the focused Original-R5 ordinary-pickup probe on Windows.

This is a pickup-only adapter around ``distributed_sync_runner``.  It keeps the
shared runner untouched, reverses the topology so Windows Original R5 is the
pilot, enables only the pickup probe profile, waits for the server-side pickup
callback, and emits ``pickup-r5-analysis.json`` beside the captured artifact.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
import re
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import distributed_sync_runner as distributed  # noqa: E402
import reloop  # noqa: E402
import sync_edge_probe  # noqa: E402
import sync_pair_client  # noqa: E402
import windows_sync_edge_probe as windows_edge  # noqa: E402
from analyze_pickup_r5 import (  # noqa: E402
    MISMATCH,
    ORIGINAL_R5_SHA256,
    PICKUP_FLAG,
    analyze_log,
)


SCENARIO = "pickup"
PROFILE = "pickup-r5"
PROFILE_FLAGS = (PICKUP_FLAG,)
ACCEPTABLE_ASSESSMENTS = ("OBSERVED_ORDINARY", "OBSERVED_COMPLETE")


def pickup_request_state(text: str, request_id: int) -> dict[str, Any]:
    """Return request-scoped server markers, ignoring older fixture runs."""
    active = False
    checks = {
        "request_accepted": False,
        "scenario_started": False,
        "pickup_created": False,
        "request_done": False,
        "pickup_collected": False,
    }
    collection_line: str | None = None
    for line in text.splitlines():
        accepted = re.search(r"marker=REQUEST_ACCEPTED\b.*\brequest=(\d+)\b", line)
        if accepted:
            active = int(accepted.group(1)) == request_id
            if active:
                checks["request_accepted"] = True
        if not active:
            continue
        if (
            "marker=SCENARIO_START" in line
            and f"request={request_id} " in line
            and "scenario=pickup " in line
        ):
            checks["scenario_started"] = True
        elif "marker=PICKUP_CREATED" in line:
            checks["pickup_created"] = True
        elif (
            "marker=REQUEST_DONE" in line
            and f"request={request_id} " in line
            and "status=PASS " in line
            and "scenario=pickup " in line
        ):
            checks["request_done"] = True
        elif "marker=PICKUP_COLLECTED" in line:
            checks["pickup_collected"] = True
            collection_line = line
    return {
        "complete": all(checks.values()),
        "checks": checks,
        "collection_line": collection_line,
    }


def wait_for_pickup_collection(
    server_log: Path,
    start_offset: int,
    request_id: int,
    timeout_seconds: float,
    output: list[dict[str, Any]],
) -> str:
    """Wait until the Windows pilot's RPC131 reaches the fixture callback."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server_log.exists():
            data = server_log.read_bytes()
            if len(data) < start_offset:
                start_offset = 0
            state = pickup_request_state(
                data[start_offset:].decode("utf-8", errors="replace"),
                request_id,
            )
            if state["complete"]:
                event = {
                    "event": "windows_pilot_pickup_observed",
                    "scenario": SCENARIO,
                    "request_id": request_id,
                    "result": state["collection_line"],
                    "checks": state["checks"],
                    "host_time": time.time(),
                }
                output.append(event)
                print(json.dumps(event, sort_keys=True))
                return str(state["collection_line"])
        time.sleep(0.05)
    raise TimeoutError(
        f"sync_pair emitted no complete pickup collection for request "
        f"{request_id} within {timeout_seconds:.1f}s"
    )


def run_windows_pickup_driver(
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
    """Queue one ordinary pickup while Original R5 is the Windows pilot."""
    del lab_timeout
    output_path = artifact_dir / "driver" / f"{SCENARIO}.json"
    console_path = artifact_dir / "driver" / f"{SCENARIO}.console.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    returncode = 0
    screenshot_label = f"dist-sync-pickup-r5-pilot-{int(time.time())}"
    start_offset = server_log.stat().st_size if server_log.exists() else 0

    with console_path.open("w", encoding="utf-8") as handle:
        with contextlib.redirect_stdout(handle), contextlib.redirect_stderr(handle):
            try:
                if death_f4:
                    raise ValueError("pickup driver does not accept death_f4")
                sync_pair_client.capture_observer(
                    f"{screenshot_label}-before", 1, 0.0
                )
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    burst = pool.submit(
                        sync_pair_client.capture_observer,
                        screenshot_label,
                        screenshot_count,
                        screenshot_interval,
                    )
                    time.sleep(min(0.5, max(0.1, screenshot_interval * 2.0)))
                    request_id = sync_pair_client.queue_sync_pair_scenario(
                        SCENARIO,
                        request_path,
                        results_path,
                        fixture_timeout,
                        output,
                    )
                    wait_for_pickup_collection(
                        server_log,
                        start_offset,
                        request_id,
                        fixture_timeout,
                        output,
                    )
                    # Give the probe worker a bounded opportunity to flush the
                    # nested RPC event and enclosing PickedUp snapshot.
                    time.sleep(0.75)
                    burst.result(
                        timeout=fixture_timeout
                        + screenshot_count * max(0.025, screenshot_interval)
                        + 30.0
                    )
                sync_pair_client.capture_observer(
                    f"{screenshot_label}-after", 1, 0.0
                )
                output.append(
                    {
                        "event": "windows_pilot_pickup_capture_completed",
                        "scenario": SCENARIO,
                        "request_id": request_id,
                        "screenshot_label": screenshot_label,
                        "screenshot_count": screenshot_count,
                        "screenshot_interval": screenshot_interval,
                        "probe_flush_settle_seconds": 0.75,
                        "host_time": time.time(),
                    }
                )
            except Exception as error:
                returncode = 1
                output.append(
                    {
                        "event": "windows_pilot_pickup_driver_error",
                        "scenario": SCENARIO,
                        "error": f"{type(error).__name__}: {error}",
                        "host_time": time.time(),
                    }
                )
                traceback.print_exc()
    reloop.write_json(
        output_path,
        {
            "scenario": SCENARIO,
            "windows_role": "pilot",
            "fixture_scope": "ordinary type-1 pickup",
            "returncode": returncode,
            "events": output,
        },
    )
    return returncode


@contextmanager
def pickup_runner_patch() -> Iterator[None]:
    """Temporarily add only the pickup topology/profile adapter in memory."""
    missing = object()
    previous_profile = distributed.PROBE_PROFILE_FLAGS.get(PROFILE, missing)
    previous_validate = distributed.validate_role_scenario
    previous_death_driver = distributed.run_windows_death_driver
    previous_pickup_driver = getattr(
        distributed, "run_windows_pickup_driver", missing
    )
    if previous_profile is not missing and previous_profile != PROFILE_FLAGS:
        raise distributed.DistributedSyncError(
            f"shared runner defines incompatible {PROFILE!r} flags: "
            f"{previous_profile!r}"
        )

    def validate_role_scenario(windows_role: str, scenario: str) -> None:
        if windows_role == "pilot" and scenario == SCENARIO:
            return
        previous_validate(windows_role, scenario)

    distributed.PROBE_PROFILE_FLAGS[PROFILE] = PROFILE_FLAGS
    distributed.validate_role_scenario = validate_role_scenario
    # Current shared-runner fallback dispatches all non-UI/GMX Windows-pilot
    # scenarios through this symbol.  Also expose the explicit pickup symbol
    # so the adapter remains compatible when that dispatch grows upstream.
    distributed.run_windows_death_driver = run_windows_pickup_driver
    distributed.run_windows_pickup_driver = run_windows_pickup_driver
    try:
        yield
    finally:
        distributed.validate_role_scenario = previous_validate
        distributed.run_windows_death_driver = previous_death_driver
        if previous_pickup_driver is missing:
            delattr(distributed, "run_windows_pickup_driver")
        else:
            distributed.run_windows_pickup_driver = previous_pickup_driver
        if previous_profile is missing:
            distributed.PROBE_PROFILE_FLAGS.pop(PROFILE, None)
        else:
            distributed.PROBE_PROFILE_FLAGS[PROFILE] = previous_profile


def build_runner_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        config=args.config,
        scenario=SCENARIO,
        server_mode=args.server_mode,
        local_client_mode=args.local_client_mode,
        windows_client_mode=args.windows_client_mode,
        windows_role="pilot",
        death_f4=False,
        windows_server_host=args.windows_server_host,
        windows_favorite_index=args.windows_favorite_index,
        deploy_windows_dll=args.original_dll,
        deploy_windows_probe=args.probe,
        windows_probe_profile=PROFILE,
        client_ready_timeout=args.client_ready_timeout,
        pair_ready_timeout=args.pair_ready_timeout,
        fixture_timeout=args.fixture_timeout,
        action_seconds=1.0,
        between=0.0,
        screenshot_count=args.screenshot_count,
        screenshot_interval=args.screenshot_interval,
        windows_start_timeout=args.windows_start_timeout,
        lab_timeout=args.lab_timeout,
        fetch_timeout=args.fetch_timeout,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=reloop.DEFAULT_CONFIG
    )
    parser.add_argument(
        "--original-dll",
        type=Path,
        default=REPO_ROOT / "samp.dll",
        help="documented Original 0.3.7-R5 samp.dll to deploy on Windows",
    )
    parser.add_argument(
        "--probe",
        type=Path,
        default=REPO_ROOT / "build-asi-probe" / "samp_probe.asi",
        help="focused probe ASI to deploy on Windows",
    )
    parser.add_argument(
        "--server-mode", choices=("fail", "replace", "reuse"), default="replace"
    )
    parser.add_argument(
        "--local-client-mode", choices=("fail", "replace"), default="replace"
    )
    parser.add_argument(
        "--windows-client-mode", choices=("fail", "replace"), default="replace"
    )
    parser.add_argument("--windows-server-host", default="192.168.3.181")
    parser.add_argument("--windows-favorite-index", type=int, default=3)
    parser.add_argument("--client-ready-timeout", type=float, default=60.0)
    parser.add_argument("--pair-ready-timeout", type=float, default=90.0)
    parser.add_argument("--fixture-timeout", type=float, default=45.0)
    parser.add_argument("--screenshot-count", type=int, default=12)
    parser.add_argument("--screenshot-interval", type=float, default=0.05)
    parser.add_argument("--windows-start-timeout", type=float, default=45.0)
    parser.add_argument("--lab-timeout", type=float, default=45.0)
    parser.add_argument("--fetch-timeout", type=float, default=120.0)
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    args.original_dll = args.original_dll.expanduser().resolve()
    args.probe = args.probe.expanduser().resolve()
    args.config = args.config.expanduser().resolve()
    if not args.original_dll.is_file():
        parser.error(f"Original R5 DLL is missing: {args.original_dll}")
    if reloop.sha256(args.original_dll) != ORIGINAL_R5_SHA256:
        parser.error(
            "pickup-r5 requires the documented Original R5 samp.dll "
            f"SHA256={ORIGINAL_R5_SHA256}"
        )
    if not args.probe.is_file():
        parser.error(f"probe ASI is missing: {args.probe}")
    for field in (
        "client_ready_timeout",
        "pair_ready_timeout",
        "fixture_timeout",
        "windows_start_timeout",
        "lab_timeout",
        "fetch_timeout",
    ):
        if getattr(args, field) <= 0:
            parser.error(f"--{field.replace('_', '-')} must be positive")
    if not 1 <= args.screenshot_count <= 120:
        parser.error("--screenshot-count must be between 1 and 120")
    if not 0.025 <= args.screenshot_interval <= 10.0:
        parser.error("--screenshot-interval must be between 0.025 and 10 seconds")
    if not 0 <= args.windows_favorite_index <= 100:
        parser.error("--windows-favorite-index must be between 0 and 100")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    try:
        with pickup_runner_patch():
            artifact, distributed_verdict = distributed.execute(
                build_runner_args(args)
            )
        analysis = analyze_log(artifact)
        reloop.write_json(artifact / "pickup-r5-analysis.json", analysis)
        print(f"pickup analysis: {analysis['assessment']}", flush=True)
        print(
            f"pickup analysis artifact: {artifact / 'pickup-r5-analysis.json'}",
            flush=True,
        )
    except (
        distributed.DistributedSyncError,
        windows_edge.WindowsSyncEdgeError,
        sync_edge_probe.SyncEdgeError,
        reloop.ReLoopError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
        OSError,
        ValueError,
    ) as error:
        print(f"Pickup R5 runner failed: {error}", file=sys.stderr)
        return 2
    except Exception:
        traceback.print_exc()
        return 2

    if distributed_verdict.get("verdict") == "FAIL":
        return 1
    if analysis["assessment"] == MISMATCH:
        return 1
    return 0 if analysis["assessment"] in ACCEPTABLE_ASSESSMENTS else 1


if __name__ == "__main__":
    raise SystemExit(main())
