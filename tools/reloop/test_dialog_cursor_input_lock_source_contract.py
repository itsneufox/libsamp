#!/usr/bin/env python3
"""Source contracts for modal-dialog input ownership and cursor rendering."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


def definition_body(source: str, signature: str) -> str:
    """Return the function definition beginning with *signature*."""

    cursor = 0
    while True:
        start = source.index(signature, cursor)
        brace = source.find("{", start + len(signature))
        semicolon = source.find(";", start + len(signature))
        if brace >= 0 and (semicolon < 0 or brace < semicolon):
            depth = 0
            for index in range(brace, len(source)):
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                    if depth == 0:
                        return source[start : index + 1]
            raise AssertionError(f"unterminated function definition: {signature}")
        cursor = start + len(signature)


class DialogCursorInputLockSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")

    def test_network_and_f1_dialogs_apply_keyboard_and_mouse_input_patches(
        self,
    ) -> None:
        network_dialog = definition_body(
            self.source,
            "static void dialog_compat_update_from_snapshot(",
        )
        help_dialog = definition_body(
            self.source,
            "static void dialog_compat_show_help(",
        )

        self.assertIn(
            'chat_input_game_controls_apply_compat(\n'
            '      new_dialog ? "dialog_open" : "dialog_active")',
            network_dialog,
        )
        self.assertIn(
            'chat_input_game_controls_apply_compat("help_dialog_open")',
            help_dialog,
        )
        self.assertIn("dialog_game_mouse_flush_pending", network_dialog)
        self.assertIn("dialog_game_mouse_flush_pending", help_dialog)
        self.assertIn(
            "dialog_game_mouse_controls_activate_compat(",
            network_dialog,
        )
        self.assertIn(
            'dialog_game_mouse_controls_activate_compat("help_dialog_open")',
            help_dialog,
        )

    def test_dialog_close_uses_r5_ten_tick_delayed_restore(self) -> None:
        close = definition_body(
            self.source,
            "static void dialog_compat_close(",
        )

        self.assertIsNotNone(
            re.search(
                r"^#define\s+SAMP_DIALOG_INPUT_RELEASE_FRAMES\s+10\s*$",
                self.source,
                re.MULTILINE,
            ),
        )
        self.assertIn("LONG was_active", close)
        self.assertIn(
            "InterlockedExchange(&g_runtime.chat_game_input_release_frames,",
            close,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.dialog_game_mouse_release_frames,",
            close,
        )
        self.assertEqual(close.count("SAMP_DIALOG_INPUT_RELEASE_FRAMES"), 2)
        self.assertIn("chat_input_active", close)

    def test_update_holds_and_flushes_dialog_patches_but_not_scoreboard(
        self,
    ) -> None:
        update = definition_body(
            self.source,
            "static void chat_input_game_controls_update_compat(",
        )

        self.assertIn("g_runtime.chat_input_active", update)
        self.assertIn("dialog_compat_active()", update)
        self.assertIn(
            'chat_input_game_controls_apply_compat("dialog_active_tick")',
            update,
        )
        self.assertIn(
            'dialog_game_mouse_controls_activate_compat("dialog_active_tick")',
            update,
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.chat_game_input_release_frames, 0)",
            update,
        )
        self.assertIn("chat_input_game_controls_restore_compat(", update)
        self.assertIn("dialog_game_mouse_controls_restore_compat(", update)
        self.assertNotIn("scoreboard_visible", update)
        self.assertNotIn("scoreboard_compat_cursor_owned", update)
        self.assertNotIn("g_runtime.dialog_mouse_mode", update)

    def test_dialog_restore_edge_survives_chat_open_and_retries(self) -> None:
        update = definition_body(
            self.source,
            "static void chat_input_game_controls_update_compat(",
        )
        restore_due = update.index("if (dialog_restore_due)")
        chat_return = update.index("if (chat_active || dialog_active)")
        restore_block = update[restore_due:chat_return]

        self.assertLess(restore_due, chat_return)
        self.assertIn("if (!chat_active)", restore_block)
        self.assertIn(
            "chat_input_game_controls_restore_compat("
            '"dialog_close_release")',
            restore_block,
        )
        self.assertIn(
            "dialog_game_mouse_controls_restore_compat(",
            restore_block,
        )
        self.assertIn("dialog_game_mouse_patch_applied", update)
        self.assertIn('"input_release_retry"', update)

    def test_r5_directinput_mouse_gate_has_exact_validated_bytes(self) -> None:
        apply = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_apply_compat(",
        )
        flush = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_flush_compat(",
        )
        state_flush = definition_body(
            self.source,
            "static int dialog_game_mouse_state_flush_compat(",
        )
        restore = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_restore_code_compat(",
        )

        for address in (
            "SAMP_ADDR_GAME_MOUSE_POLL_CALL",
            "SAMP_ADDR_GAME_MOUSE_RESULT_BRANCH",
        ):
            with self.subTest(address=address):
                self.assertIn(address, apply)
                self.assertIn(address, restore)
        for expected in (
            "0xE8u, 0xB4u, 0x7Au, 0x20u, 0x00u",
            "0x90u, 0x90u, 0x90u, 0x90u, 0x90u",
            "0x85u, 0xC0u, 0x0Fu, 0x8Cu",
            "0x33u, 0xC0u, 0x0Fu, 0x84u",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, apply)
        self.assertIn("target_bytes_mismatch=1", apply)
        self.assertIn("dialog_game_mouse_patch_owned", apply)
        self.assertIn("dialog_game_mouse_patch_owned", restore)
        self.assertIn("SAMP_ADDR_GAME_MOUSE_MOVE_X", state_flush)
        self.assertIn("SAMP_ADDR_GAME_MOUSE_MOVE_Y", state_flush)
        self.assertIn("SAMP_GTA_FUNC_CLEAR_MOUSE_HISTORY", state_flush)
        self.assertIn("SAMP_GTA_FUNC_UPDATE_PADS", state_flush)
        self.assertLess(
            state_flush.index("clear_mouse_history();"),
            state_flush.index("update_pads();"),
        )
        self.assertIn(
            'dialog_game_mouse_state_flush_compat(\n'
            '        "dialog_restore_after_patch", 1)',
            restore,
        )
        self.assertIn(
            'dialog_game_mouse_state_flush_compat(\n'
            '          "dialog_restore_second_clear", 0)',
            restore,
        )
        self.assertIn(
            "visible_cursor_recenter_patch_restore_compat(",
            restore,
        )

    def test_pad_calls_are_game_thread_only_and_shutdown_is_code_only(
        self,
    ) -> None:
        apply = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_apply_compat(",
        )
        state_flush = definition_body(
            self.source,
            "static int dialog_game_mouse_state_flush_compat(",
        )
        restore = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_restore_compat(",
        )
        shutdown = definition_body(
            self.source,
            "static void dialog_game_mouse_controls_restore_shutdown_compat(",
        )
        modules_shutdown = definition_body(
            self.source,
            "static void phase_runtime_modules_shutdown(",
        )

        for body in (apply, state_flush, restore):
            with self.subTest(signature=body.splitlines()[0]):
                self.assertIn(
                    "dialog_game_mouse_on_game_thread_compat(",
                    body,
                )
        self.assertIn(
            "dialog_game_mouse_controls_restore_code_compat(reason, 0)",
            shutdown,
        )
        self.assertNotIn("dialog_game_mouse_state_flush_compat(", shutdown)
        self.assertNotIn("d3d9_cursor_show_compat(", shutdown)
        self.assertIn(
            'dialog_game_mouse_controls_restore_shutdown_compat('
            '"module_shutdown")',
            modules_shutdown,
        )
        self.assertNotIn(
            'dialog_game_mouse_controls_restore_compat("module_shutdown")',
            modules_shutdown,
        )

    def test_restore_ownership_is_kept_until_no_owned_patch_remains(
        self,
    ) -> None:
        restore = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_restore_code_compat(",
        )

        ownership_clear = restore.index(
            "g_runtime.dialog_game_mouse_patch_owned = 0u"
        )
        remaining_check = restore.index("owned_patch_remaining=1")
        self.assertLess(remaining_check, ownership_clear)
        self.assertIn("poll_rollback", restore)
        self.assertGreaterEqual(restore.count("retry=1"), 4)
        self.assertEqual(
            restore.count(
                "g_runtime.dialog_game_mouse_patch_owned = 0u"
            ),
            1,
        )

    def test_other_cursor_owner_does_not_hold_dialog_input_patches(self) -> None:
        update = definition_body(
            self.source,
            "static void chat_input_game_controls_update_compat(",
        )
        restore = definition_body(
            self.source,
            "static int dialog_game_mouse_controls_restore_code_compat(",
        )

        self.assertNotIn("dialog_mouse_mode", update)
        self.assertNotIn("scoreboard_compat_", update)
        self.assertNotIn("g_runtime.scoreboard_", update)
        self.assertIn("g_runtime.dialog_mouse_mode", restore)
        ownership_clear = restore.index(
            "g_runtime.dialog_game_mouse_patch_owned = 0u"
        )
        cursor_owner_check = restore.index("g_runtime.dialog_mouse_mode")
        self.assertLess(ownership_clear, cursor_owner_check)

    def test_recenter_restore_is_deferred_with_the_r5_dialog_gate(self) -> None:
        mouse_mode = definition_body(
            self.source,
            "static void dialog_compat_set_mouse_mode(",
        )

        self.assertIn(
            "g_runtime.dialog_game_mouse_patch_applied",
            mouse_mode,
        )
        self.assertIn(
            'visible_cursor_recenter_patch_restore_compat("dialog_mouse_disable")',
            mouse_mode,
        )
        self.assertIn("recenter restore deferred", mouse_mode)

    def test_bullet_sync_is_suppressed_during_dialog_mouse_ownership(
        self,
    ) -> None:
        callback = definition_body(
            self.source,
            "static void __cdecl bullet_impact_hook_callback_compat(",
        )

        precondition = callback[: callback.index("memcpy(&start_value")]
        self.assertIn("dialog_compat_active()", precondition)
        self.assertIn(
            "g_runtime.dialog_game_mouse_patch_applied",
            precondition,
        )

    def test_game_window_key_poll_is_gated_by_chat_and_dialog_only(self) -> None:
        key_down = definition_body(
            self.source,
            "static int game_window_key_down_compat(",
        )

        self.assertIn("g_runtime.chat_input_active", key_down)
        self.assertIn("g_runtime.dialog_overlay_active", key_down)
        self.assertIn("return 0;", key_down)
        self.assertNotIn("scoreboard_visible", key_down)
        self.assertNotIn("scoreboard_compat_cursor_owned", key_down)

    def test_modal_wndproc_consumes_non_primary_mouse_input(self) -> None:
        wndproc = definition_body(
            self.source,
            "static LRESULT CALLBACK chat_input_wndproc_compat(",
        )
        dialog_branch = wndproc[wndproc.index("if (dialog_active)") :]
        consumed_branch = dialog_branch[
            dialog_branch.index("if (msg == WM_RBUTTONDOWN") :
        ]
        consumed_branch = consumed_branch[: consumed_branch.index("return 0;") + 9]

        for message in (
            "WM_RBUTTONDOWN",
            "WM_RBUTTONUP",
            "WM_RBUTTONDBLCLK",
            "WM_MBUTTONDOWN",
            "WM_MBUTTONUP",
            "WM_MBUTTONDBLCLK",
            "WM_XBUTTONDOWN",
            "WM_XBUTTONUP",
            "WM_XBUTTONDBLCLK",
            "WM_MOUSEWHEEL",
            "WM_MOUSEHWHEEL",
        ):
            with self.subTest(message=message):
                self.assertIn(message, consumed_branch)
        self.assertTrue(consumed_branch.rstrip().endswith("return 0;"))

    def test_legacy_hand_drawn_cursor_is_absent(self) -> None:
        for legacy_raster in ("outline_widths", "fill_offsets", "fill_widths"):
            with self.subTest(legacy_raster=legacy_raster):
                self.assertNotIn(legacy_raster, self.source)

    def test_external_mouse_texture_drives_one_backbuffer_quad(self) -> None:
        prepare = definition_body(
            self.source,
            "static int ui_cursor_compat_prepare_d3d(",
        )
        draw = definition_body(
            self.source,
            "static int ui_compat_draw_cursor(",
        )

        self.assertIn('snprintf(path, sizeof(path), "%smouse.png"', prepare)
        self.assertIn("g_runtime.d3dx_create_texture_from_file_a(", prepare)
        self.assertIn("ui_cursor_texture_ready", prepare)
        self.assertIn("g_runtime.ui_cursor_texture", draw)
        self.assertIn("SAMP_UI_CURSOR_WIDTH", draw)
        self.assertIn("SAMP_UI_CURSOR_HEIGHT", draw)
        self.assertIn("SAMP_D3DFVF_XYZRHW_DIFFUSE_TEX1", draw)
        self.assertIn("SAMP_D3D9_DRAW_PRIMITIVE_UP_INDEX", draw)
        self.assertIn("SAMP_D3DTOP_DISABLE", draw)
        self.assertIn(
            "draw_primitive_up(device, SAMP_D3DPT_TRIANGLESTRIP, 2u, vertices,",
            draw,
        )

    def test_cursor_is_drawn_once_after_each_mouse_ui_render_branch(self) -> None:
        overlay = definition_body(
            self.source,
            "static int chat_compat_draw_d3dx_overlay(",
        )

        self.assertEqual(overlay.count("ui_compat_draw_cursor(device)"), 2)
        scoreboard_draw = overlay.index("scoreboard_compat_draw_d3dx_overlay(device)")
        scoreboard_cursor = overlay.index("ui_compat_draw_cursor(device)")
        scoreboard_restore = overlay.index(
            "chat_compat_end_d3dx_overlay_state(state_block, apply_state_block)",
            scoreboard_cursor,
        )
        self.assertLess(scoreboard_draw, scoreboard_cursor)
        self.assertLess(scoreboard_cursor, scoreboard_restore)

        dialog_draw = overlay.rindex("dialog_compat_draw_d3dx_overlay(")
        normal_cursor = overlay.rindex("ui_compat_draw_cursor(device)")
        normal_restore = overlay.rindex(
            "chat_compat_end_d3dx_overlay_state(state_block, apply_state_block)"
        )
        self.assertLess(dialog_draw, normal_cursor)
        self.assertLess(normal_cursor, normal_restore)

    def test_win32_cursor_is_an_explicit_fallback_only(self) -> None:
        prepare = definition_body(
            self.source,
            "static int ui_cursor_compat_prepare_d3d(",
        )
        mouse_mode = definition_body(
            self.source,
            "static void dialog_compat_set_mouse_mode(",
        )

        self.assertIn("fallback=win32", prepare)
        self.assertIn(
            'd3d9_cursor_show_compat(0, "dialog_mouse_enable_backbuffer")',
            mouse_mode,
        )
        self.assertIn(
            "ui_cursor_compat_set_win32_visible(!texture_cursor_ready)",
            mouse_mode,
        )
        self.assertNotIn(
            "d3d9_cursor_show_compat(texture_cursor_ready", mouse_mode
        )
        self.assertIn(
            'texture_cursor_ready ? "backbuffer_mouse.png"\n'
            '                                          : "win32_fallback"',
            mouse_mode,
        )


if __name__ == "__main__":
    unittest.main()
