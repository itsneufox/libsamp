#!/usr/bin/env python3
"""Source contracts for the observed Original-R5 TAB key-up latch."""

from __future__ import annotations

import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


def function_body(source: str, name: str, next_name: str) -> str:
    start = source.index(f"static int {name}(")
    start = source.index(f"static int {name}(", start + len(name))
    end = source.index(f"static int {next_name}(", start)
    return source[start:end]


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


class ScoreboardLatchSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        cls.visible = definition_body(
            cls.source,
            "static int scoreboard_compat_visible_latched(void)",
        )
        cls.active = function_body(
            cls.source,
            "scoreboard_compat_active",
            "scoreboard_compat_handle_key",
        )
        cls.handle = function_body(
            cls.source,
            "scoreboard_compat_handle_key",
            "scoreboard_compat_ensure_font",
        )

    def test_visibility_is_latched_instead_of_polled_from_tab(self) -> None:
        self.assertIn("LONG scoreboard_visible;", self.source)
        self.assertIn(
            "return InterlockedCompareExchange("
            "&g_runtime.scoreboard_visible, 0, 0) != 0;",
            self.visible,
        )
        self.assertIn("return scoreboard_compat_visible_latched();", self.active)
        self.assertNotIn(
            "return game_window_key_down_compat(VK_TAB);",
            self.active,
        )

    def test_plain_tab_toggles_only_on_keyup(self) -> None:
        self.assertIn(
            "if (msg == WM_KEYUP && wparam == VK_TAB)",
            self.handle,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.scoreboard_visible, 0);",
            self.handle,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.scoreboard_visible, 1);",
            self.handle,
        )
        self.assertIn("samp.dll+0x61785..+0x61790", self.handle)
        self.assertIn("samp.dll+0x617A0", self.handle)
        self.assertIn("samp.dll+0x617B6", self.handle)
        self.assertIn(
            "OBSERVED_037 + PROBE_TRACE + STATIC_037",
            self.handle,
        )

    def test_paging_uses_visible_latch(self) -> None:
        self.assertIn("if (scoreboard_compat_active())", self.handle)
        self.assertNotIn(
            "if (game_window_key_down_compat(VK_TAB))",
            self.handle,
        )

    def test_show_owns_cursor_without_disabling_gameplay_input(self) -> None:
        self.assertIn(
            "InterlockedExchange(&g_runtime.scoreboard_mouse_mode, 1);",
            self.handle,
        )
        self.assertIn("dialog_compat_set_mouse_mode(1);", self.handle)
        self.assertIn("cursor_mode=3", self.handle)

        mouse_start = self.source.index(
            "static int scoreboard_compat_handle_mouse("
        )
        mouse_end = self.source.index(
            "static int scoreboard_compat_slot_name_conflicts_with_local(",
            mouse_start,
        )
        mouse = self.source[mouse_start:mouse_end]
        self.assertIn(
            "scoreboard: right_button cursor_mode=3 game_input=unchanged",
            mouse,
        )
        self.assertNotIn(
            'chat_input_game_controls_apply_compat("scoreboard_right_button")',
            mouse,
        )

    def test_hud_is_enforced_on_scoreboard_render_cadence(self) -> None:
        draw_start = self.source.index(
            "static int scoreboard_compat_draw_d3dx_overlay("
        )
        draw_start = self.source.index(
            "static int scoreboard_compat_draw_d3dx_overlay(",
            draw_start + 1,
        )
        draw_end = self.source.index(
            "static const samp_scoreboard_player_compat "
            "*death_window_compat_scoreboard_slot(",
            draw_start,
        )
        draw = self.source[draw_start:draw_end]
        active = draw.index("if (!scoreboard_compat_visible_latched())")
        enforce = draw.index("scoreboard_compat_update_hud();")
        font = draw.index("if (!scoreboard_compat_ensure_font(device))")
        self.assertLess(active, enforce)
        self.assertLess(enforce, font)
        self.assertIn("Original R5 keeps HUD=0/radar_blank=1", draw)

    def test_shared_cursor_release_paths_preserve_scoreboard_owner(self) -> None:
        required_guards = (
            "static void dialog_compat_close(void)",
            "static void edit_state_compat_set_mouse_mode(int enabled)",
            "static void textdraw_compat_update_from_snapshot(",
            "static void textdraw_compat_clear_select_mode(const char *reason)",
            "static void class_selection_compat_update_mouse_mode(void)",
        )
        for index, marker in enumerate(required_guards):
            with self.subTest(marker=marker):
                self.assertIn(
                    "scoreboard_compat_cursor_owned()",
                    definition_body(self.source, marker),
                )
        cursor_owner = definition_body(
            self.source,
            "static int scoreboard_compat_cursor_owned(void)",
        )
        self.assertIn("&g_runtime.scoreboard_visible", cursor_owner)
        self.assertIn("&g_runtime.scoreboard_mouse_mode", cursor_owner)

    def test_session_hud_writers_defer_to_visible_scoreboard(self) -> None:
        maintain_start = self.source.index(
            "static void maintain_online_session_state(void)"
        )
        maintain_end = self.source.index(
            "static int gta_code_ptr_compat(",
            maintain_start,
        )
        maintain = self.source[maintain_start:maintain_end]
        self.assertIn(
            "scoreboard_compat_write_hud_if_unowned(1u, 0u)",
            maintain,
        )
        self.assertNotIn(
            "write_game_u8(SAMP_ADDR_ENABLE_HUD, 1u)",
            maintain,
        )

        session = definition_body(
            self.source,
            "static void apply_multiplayer_session_bridge_compat(void)",
        )
        self.assertIn(
            "scoreboard_compat_write_hud_if_unowned(spawn_ready ? 1u : 0u",
            session,
        )
        self.assertIn(
            "scoreboard_compat_write_hud_if_unowned(1u, 0u)",
            session,
        )
        hud_owner = definition_body(
            self.source,
            "static int scoreboard_compat_hud_owned(void)",
        )
        self.assertIn("&g_runtime.scoreboard_visible", hud_owner)
        self.assertIn("&g_runtime.scoreboard_hud_hidden", hud_owner)
        guarded_writer = definition_body(
            self.source,
            "static int scoreboard_compat_write_hud_if_unowned("
            "uint8_t hud, uint8_t radar_blank)",
        )
        self.assertEqual(
            guarded_writer.count("if (scoreboard_compat_hud_owned())"),
            2,
        )

    def test_visible_scoreboard_is_exclusive_overlay_branch(self) -> None:
        draw = definition_body(
            self.source,
            "static int chat_compat_draw_d3dx_overlay(void *device)",
        )
        raw_latch = draw.index(
            "scoreboard_active = scoreboard_compat_visible_latched();"
        )
        branch = draw.index("if (scoreboard_active)", raw_latch)
        netstats = draw.index("if (netstats_active)", branch)
        chat_history = draw.index(
            "for (i = 0; i < display_count; ++i)",
            branch,
        )
        branch_end = draw.index(
            "if (!chat_compat_ensure_d3dx_font(device))",
            branch,
        )
        exclusive = draw[branch:branch_end]

        self.assertLess(branch, netstats)
        self.assertLess(branch, chat_history)
        self.assertIn("scoreboard_compat_draw_d3dx_overlay(device)", exclusive)
        self.assertIn(
            "chat_compat_end_d3dx_overlay_state(state_block, apply_state_block)",
            exclusive,
        )
        self.assertIn("return 1;", exclusive)
        self.assertIn(
            "scoreboard: exclusive_overlay normal_overlay_draws=0",
            exclusive,
        )
        self.assertIn("samp.dll+0x7593A..+0x7593F", draw)
        self.assertIn("Chat::Draw (+0x75A81)", draw)
        self.assertIn("ChatInput::Draw (+0x75A90)", draw)

    def test_focus_and_session_resets_clear_visibility(self) -> None:
        focus = self.source.index(
            "InterlockedExchange(&g_runtime.scoreboard_focus_release_latched, 1);"
        )
        focus_clear = self.source.index(
            "InterlockedExchange(&g_runtime.scoreboard_visible, 0);",
            focus,
        )
        focus_restore = self.source.index(
            'scoreboard_compat_restore_hud("wm_killfocus");',
            focus,
        )
        self.assertLess(focus_clear, focus_restore)

        reset = self.source.index(
            "static void game_session_reset_to_preconnect_compat("
        )
        reset_clear = self.source.index(
            "InterlockedExchange(&g_runtime.scoreboard_visible, 0);",
            reset,
        )
        self.assertLess(reset_clear, self.source.index("textdraw_compat_clear_select_mode", reset))


if __name__ == "__main__":
    unittest.main()
