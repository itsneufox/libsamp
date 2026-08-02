#!/usr/bin/env python3
"""Host client and scripted UI interaction scenario for reloop_control.asi."""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

TOKEN = "reloop-local-v1"
VK_DOWN = 0x28
VK_F8 = 0x77
VK_RETURN = 0x0D
VK_SPACE = 0x20


class ControlClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 18737, timeout: float = 3.0):
        self.socket = socket.create_connection((host, port), timeout=timeout)
        self.stream = self.socket.makefile("rwb", buffering=0)

    def close(self) -> None:
        self.stream.close()
        self.socket.close()

    def command(self, cmd: str, **fields: Any) -> dict[str, Any]:
        payload = {"token": TOKEN, "cmd": cmd, **fields}
        self.stream.write(json.dumps(payload, separators=(",", ":")).encode() + b"\n")
        line = self.stream.readline()
        if not line:
            raise ConnectionError("reloop_control closed the connection")
        response = json.loads(line)
        if not response.get("ok"):
            raise RuntimeError(f"control command failed: {response}")
        return response

    def key(self, vk: int, action: str) -> dict[str, Any]:
        return self.command("key", vk=vk, action=action)

    def text(self, value: str) -> None:
        for character in value:
            self.command("char", code=ord(character))


def wait_for_api(timeout: float = 45.0) -> ControlClient:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client = ControlClient()
            client.command("ping")
            return client
        except (OSError, ConnectionError, RuntimeError, json.JSONDecodeError):
            time.sleep(0.25)
    raise TimeoutError("reloop_control API was not reachable on 127.0.0.1:18737")


def sample(client: ControlClient, label: str, output: list[dict[str, Any]]) -> dict[str, Any]:
    state = client.command("state")
    state["label"] = label
    state["host_time"] = time.time()
    output.append(state)
    print(json.dumps(state, sort_keys=True))
    return state


def chat_command(client: ControlClient, command: str) -> None:
    """Submit one command through the same WM_CHAR path as original SA-MP."""
    client.command("char", code=ord("t"))
    time.sleep(0.3)
    for character in command:
        client.command("char", code=ord(character))
        time.sleep(0.04)
    client.command("window_key", vk=VK_RETURN)


def request_samp_screenshot(client: ControlClient) -> dict[str, Any]:
    """Use the guarded R5 request flag, with ordinary F8 for the replacement."""
    try:
        return client.command("samp_screenshot")
    except RuntimeError:
        return client.key(VK_F8, "tap")


def run_scenario(output_path: Path, settle: float) -> None:
    states: list[dict[str, Any]] = []
    client = wait_for_api()
    try:
        client.command("focus")
        # RUN_START can precede the final class-selection handoff by a few
        # frames in the replacement. Wait until normal gameplay owns input.
        time.sleep(max(3.0, settle))
        baseline = sample(client, "baseline", states)

        if os.environ.get("SAMP_RELOOP_RPC73_REPLACE") == "1":
            chat_command(client, "/rpc73replace")
            time.sleep(max(1.0, settle))
            request_samp_screenshot(client)
            time.sleep(0.4)

        # Chat: opening T must own the mouse and stop GTA control/camera input.
        client.command("char", code=ord("t"))
        time.sleep(settle)
        sample(client, "chat_open", states)
        client.key(ord("W"), "down")
        client.command("mouse", action="move", x=max(10, baseline["client_w"] // 2 + 80),
                       y=max(10, baseline["client_h"] // 2))
        time.sleep(settle)
        sample(client, "chat_input_attempt", states)
        client.key(ord("W"), "up")
        client.text("reloop chat interaction")
        client.command("window_key", vk=13)
        time.sleep(settle)
        sample(client, "chat_closed", states)

        # Legacy CreateMenu: the server fixture mirrors the stock 0.3.7
        # menutest.pwn. Capture the visible GTA panel, move one row through
        # GTA's own input path, then require its RPC132 selection callback.
        chat_command(client, "/menutest")
        time.sleep(max(1.0, settle))
        sample(client, "legacy_menu_open", states)
        request_samp_screenshot(client)
        time.sleep(0.4)
        client.key(VK_DOWN, "tap")
        time.sleep(settle)
        sample(client, "legacy_menu_row_1", states)
        # STATIC_037: CMenuPool::Process selects on CPad ButtonCross
        # (index 16, default keyboard binding SPACE). Enter/F is
        # ButtonTriangle/index 15 and therefore sends RPC140 MenuQuit.
        client.key(VK_SPACE, "tap")
        time.sleep(max(1.0, settle))
        sample(client, "legacy_menu_closed", states)

        # OBSERVED_037 + PROBE_TRACE + STATIC_037:
        # R5 WndProc toggles CScoreboard+0x0 on WM_KEYUP/VK_TAB
        # (samp.dll+0x61785..+0x617B6). One complete pulse opens it and a
        # second complete pulse closes it; visibility is not a physical-key
        # hold.
        client.key(9, "tap")
        time.sleep(settle)
        scoreboard = sample(client, "scoreboard_open", states)
        row_x = scoreboard["client_w"] // 2
        row_y = scoreboard["client_h"] // 2
        # OBSERVED_037 + PROBE_TRACE:
        # Show already acquires R5 cursor mode 3, but that mode leaves GTA's
        # gameplay-input call intact. Capture the exclusive scoreboard frame,
        # then verify that ordinary movement remains available.
        request_samp_screenshot(client)
        time.sleep(0.4)
        client.key(ord("W"), "down")
        client.command("mouse", action="move", x=row_x + 45, y=row_y)
        time.sleep(settle)
        sample(client, "scoreboard_plain_input_attempt", states)
        client.key(ord("W"), "up")
        # OBSERVED_037 + PROBE_TRACE: Show already selects cursor mode 3.
        # Exercise RMB as a forwarded GUI edge, but require GTA gameplay input
        # to remain enabled just as it does before the edge.
        client.command("mouse", action="right_click", x=row_x, y=row_y)
        time.sleep(settle)
        sample(client, "scoreboard_mouse_mode", states)
        client.key(ord("W"), "down")
        client.command("mouse", action="move", x=row_x + 90, y=row_y)
        time.sleep(settle)
        sample(client, "scoreboard_input_attempt", states)
        client.key(ord("W"), "up")
        # Scan the vertically centred scoreboard area. Original 0.3.7 and the
        # replacement use different test-prefix video modes, so absolute pixel
        # coordinates are intentionally derived from each client rectangle.
        for candidate_y in range(max(20, scoreboard["client_h"] // 5),
                                 max(21, scoreboard["client_h"] * 4 // 5), 12):
            client.command("mouse", action="double_click", x=row_x, y=candidate_y)
            time.sleep(0.15)
        time.sleep(0.5)
        time.sleep(settle)
        sample(client, "scoreboard_clicked", states)
        client.key(9, "tap")
        time.sleep(settle)
        sample(client, "scoreboard_closed", states)
    finally:
        client.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(states, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["ping", "state", "enter", "alt-enter", "chat", "type", "type-enter", "scenario"],
    )
    parser.add_argument("--output", type=Path, default=Path("ui-interaction-states.json"))
    parser.add_argument("--settle", type=float, default=0.8)
    parser.add_argument(
        "--text",
        help="chat text, or raw WM_CHAR text submitted with type/type-enter",
    )
    args = parser.parse_args()
    if args.command == "scenario":
        run_scenario(args.output, args.settle)
    else:
        if args.command in {"chat", "type", "type-enter"} and not args.text:
            parser.error(f"--text is required for the {args.command} command")
        client = wait_for_api()
        try:
            if args.command == "enter":
                response = client.command("window_key", vk=13)
            elif args.command == "alt-enter":
                response = client.command("window_syskey", vk=13)
            elif args.command == "chat":
                chat_command(client, args.text)
                response = {"ok": True, "event": "chat", "text": args.text}
            elif args.command == "type-enter":
                client.text(args.text)
                response = client.command("window_key", vk=VK_RETURN)
            elif args.command == "type":
                client.text(args.text)
                response = {"ok": True, "event": "type", "text": args.text}
            else:
                response = client.command(args.command)
            print(json.dumps(response, indent=2, sort_keys=True))
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
