#!/usr/bin/env python3
"""Source contracts for the Original-R5 selectable TextDraw release path."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = ROOT / "reimpl" / "src" / "runtime_bridge.c"
CONTROL_SOURCE = ROOT / "tools" / "reloop_control" / "src" / "reloop_control.c"


def definition_body(source: str, signature: str) -> str:
    cursor = 0
    while True:
        start = source.index(signature, cursor)
        brace = source.find("{", start + len(signature))
        semicolon = source.find(";", start + len(signature))
        if brace >= 0 and (semicolon < 0 or brace < semicolon):
            end = source.find("\nstatic ", start + len(signature))
            return source[start:] if end < 0 else source[start:end]
        cursor = start + len(signature)


class TextDrawSelectorSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = RUNTIME_SOURCE.read_text(encoding="utf-8")
        cls.control = CONTROL_SOURCE.read_text(encoding="utf-8")
        cls.handle_mouse = definition_body(
            cls.runtime,
            "static int textdraw_compat_handle_mouse(",
        )

    def test_button_up_is_not_gated_by_a_button_down_latch(self) -> None:
        release = self.handle_mouse[
            self.handle_mouse.index("if (msg == WM_LBUTTONUP)") :
        ]

        self.assertIn("STATIC_037:samp.dll+0x71570", release)
        self.assertIn(
            "SHA256=b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2",
            release,
        )
        self.assertNotIn("if (msg == WM_LBUTTONUP &&", self.handle_mouse)
        self.assertNotIn(
            "InterlockedExchange(&g_runtime.textdraw_mouse_down, 0) != 0",
            self.handle_mouse,
        )
        clear_latch = release.index(
            "InterlockedExchange(&g_runtime.textdraw_mouse_down, 0);"
        )
        hit_test = release.index("textdraw_compat_hit_test(")
        submit = release.index("textdraw_compat_submit_click(")
        consume = release.index("return 1;", submit)
        self.assertLess(clear_latch, hit_test)
        self.assertLess(hit_test, submit)
        self.assertLess(submit, consume)

    def test_primary_button_messages_remain_consumed_without_cancel(self) -> None:
        self.assertIn(
            "if (msg == WM_LBUTTONDOWN || msg == WM_LBUTTONDBLCLK)",
            self.handle_mouse,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.textdraw_mouse_down, 1);",
            self.handle_mouse,
        )
        self.assertNotIn(
            "textdraw_compat_clear_select_mode(",
            self.handle_mouse,
        )

    def test_control_harness_can_post_an_orphan_button_up(self) -> None:
        post_mouse = definition_body(
            self.control,
            "static int post_mouse(",
        )
        left_up = post_mouse[
            post_mouse.index('strcmp(action, "left_up") == 0') :
            post_mouse.index('strcmp(action, "right_down") == 0')
        ]

        self.assertIn("MOUSEEVENTF_LEFTUP", left_up)
        self.assertIn("WM_LBUTTONUP", left_up)
        self.assertNotIn("MOUSEEVENTF_LEFTDOWN", left_up)
        self.assertNotIn("WM_LBUTTONDOWN", left_up)


if __name__ == "__main__":
    unittest.main()
