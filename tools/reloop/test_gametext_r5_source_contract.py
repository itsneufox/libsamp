#!/usr/bin/env python3
"""Source contracts for Original-R5's globally exclusive GameText lifetime."""

from __future__ import annotations

import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


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


class GameTextR5SourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        cls.clear_all = definition_body(
            cls.source,
            "static void game_text_compat_clear_all("
            "uint32_t seq, const char *reason)",
        )
        cls.show = definition_body(
            cls.source,
            "static void game_text_compat_show_slot("
            "int style, uint32_t seq, int32_t time_ms, const char *text)",
        )
        cls.apply_event = definition_body(
            cls.source,
            "static void game_text_compat_apply_event("
            "const samp_raknet_game_text_event *event)",
        )
        cls.snapshot = definition_body(
            cls.source,
            "static void game_text_compat_update_from_snapshot("
            "const samp_raknet_rpc_probe_snapshot *snapshot)",
        )

    def test_clear_all_invalidates_every_style_and_global_count(self) -> None:
        self.assertIn(
            "style < (int)SAMP_RAKNET_GAMETEXT_MAX_STYLES",
            self.clear_all,
        )
        self.assertIn("InterlockedExchange(&slot->active, 0)", self.clear_all)
        self.assertIn("memset(slot, 0, sizeof(*slot));", self.clear_all)
        self.assertIn(
            "InterlockedExchange(&g_runtime.game_text_active_count, 0)",
            self.clear_all,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.game_text_active, 0)",
            self.clear_all,
        )

    def test_new_show_clears_all_before_installing_only_one_slot(self) -> None:
        clear = self.show.index(
            'game_text_compat_clear_all(seq, "replace_before_show")'
        )
        install = self.show.index("slot = &g_runtime.game_text_slots[style]")
        publish = self.show.index(
            "InterlockedExchange(&g_runtime.game_text_active_count, 1)"
        )

        self.assertLess(clear, install)
        self.assertLess(install, publish)
        self.assertNotIn(
            "InterlockedIncrement(&g_runtime.game_text_active_count)",
            self.show,
        )
        self.assertIn(
            "samp.dll+0xA0CE0,+0xA0CEC,+0xEC724,+0xA0D3E",
            self.show,
        )

    def test_empty_zero_and_hide_paths_do_not_leave_old_style_visible(self) -> None:
        self.assertIn(
            'game_text_compat_clear_all(seq, "empty_text")',
            self.show,
        )
        self.assertIn(
            'game_text_compat_clear_all(seq, "zero_time")',
            self.show,
        )
        self.assertIn(
            'game_text_compat_clear_all(event->seq, "event_hide")',
            self.apply_event,
        )
        self.assertIn(
            "game_text_compat_clear_all(snapshot->game_text_seq, "
            '"legacy_snapshot_hide")',
            self.snapshot,
        )

    def test_static_evidence_names_text_clear_all_descriptor(self) -> None:
        self.assertIn("GTA opcode 0x00BE", self.clear_all)
        self.assertIn("text_clear_all", self.clear_all)
        self.assertIn("samp.dll+0xEC724", self.clear_all)
        self.assertIn("samp.dll+0xA0D3E", self.clear_all)


if __name__ == "__main__":
    unittest.main()
