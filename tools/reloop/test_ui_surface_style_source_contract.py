#!/usr/bin/env python3
"""Source contracts for the user-requested dark glass UI surfaces."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


def definition_body(source: str, signature: str) -> str:
    """Return the definition beginning with *signature*, skipping prototypes."""

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


def define_value(source: str, name: str) -> int:
    """Resolve a literal ARGB macro or a simple alias to another macro."""

    seen: set[str] = set()
    current = name
    while current not in seen:
        seen.add(current)
        match = re.search(
            rf"^#define[ \t]+{re.escape(current)}[ \t]+(?P<value>\S+)",
            source,
            re.MULTILINE,
        )
        if match is None:
            raise AssertionError(f"missing color macro: {current}")
        value = match.group("value").rstrip("uUlL")
        if re.fullmatch(r"0[xX][0-9a-fA-F]+", value):
            return int(value, 16)
        if re.fullmatch(r"[0-9]+", value):
            return int(value, 10)
        current = value
    raise AssertionError(f"recursive color macro alias: {name}")


class UiSurfaceStyleSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")

    def test_central_surface_palette_is_dark_and_semitransparent(self) -> None:
        surface_names = (
            "SAMP_MODERN_UI_PANEL_COLOR",
            "SAMP_MODERN_UI_HEADER_COLOR",
            "SAMP_MODERN_UI_CONTROL_COLOR",
            "SAMP_MODERN_UI_CONTROL_HOVER_COLOR",
            "SAMP_MODERN_UI_CONTROL_PRESSED_COLOR",
        )
        colors = {name: define_value(self.source, name) for name in surface_names}

        for name, color in colors.items():
            with self.subTest(name=name):
                alpha = (color >> 24) & 0xFF
                red = (color >> 16) & 0xFF
                green = (color >> 8) & 0xFF
                blue = color & 0xFF
                perceived_luma = (red * 2126 + green * 7152 + blue * 722) // 10000
                self.assertGreater(alpha, 0x40)
                self.assertLess(alpha, 0xFF)
                # The hover state may carry a restrained blue/cyan tint, but
                # every composited surface must remain visibly dark.
                self.assertLessEqual(perceived_luma, 0x50)
                self.assertLessEqual(max(red, green, blue), 0x80)

        self.assertEqual(len(set(colors.values())), len(colors))

    def test_normal_hover_and_pressed_controls_are_visually_distinct(self) -> None:
        normal = define_value(self.source, "SAMP_MODERN_UI_CONTROL_COLOR")
        hover = define_value(self.source, "SAMP_MODERN_UI_CONTROL_HOVER_COLOR")
        pressed = define_value(self.source, "SAMP_MODERN_UI_CONTROL_PRESSED_COLOR")
        self.assertEqual(len({normal, hover, pressed}), 3)

        control = definition_body(
            self.source,
            "static void ui_compat_draw_glass_control(",
        )
        self.assertIn("SAMP_MODERN_UI_CONTROL_COLOR", control)
        self.assertIn("SAMP_MODERN_UI_CONTROL_HOVER_COLOR", control)
        self.assertIn("SAMP_MODERN_UI_CONTROL_PRESSED_COLOR", control)
        self.assertRegex(control, r"\bhover(?:ed)?\b")
        self.assertRegex(control, r"\bpressed\b")
        self.assertIn("ui_compat_draw_blended_rect(", control)
        self.assertIn("SAMP_MODERN_UI_BORDER_COLOR", control)

    def test_blended_rect_uses_complete_alpha_state_pipeline(self) -> None:
        blended = definition_body(
            self.source,
            "static int ui_compat_draw_blended_rect(",
        )
        alpha_pipeline = definition_body(
            self.source,
            "static int dialog_compat_d3d_alpha_rect(",
        )
        pipeline = blended + alpha_pipeline

        self.assertIn("dialog_compat_d3d_alpha_rect(", blended)
        self.assertIn("SAMP_D3DRS_ALPHATESTENABLE, 0u", pipeline)
        self.assertIn("SAMP_D3DRS_ALPHABLENDENABLE, 1u", pipeline)
        self.assertIn("SAMP_D3DBLEND_SRCALPHA", pipeline)
        self.assertIn("SAMP_D3DBLEND_INVSRCALPHA", pipeline)
        self.assertIn("SAMP_D3DRS_FILLMODE, SAMP_D3DFILL_SOLID", pipeline)
        self.assertIn("SAMP_D3DRS_CULLMODE, SAMP_D3DCULL_NONE", pipeline)
        self.assertIn("SAMP_D3DRS_COLORWRITEENABLE", pipeline)
        self.assertIn("SAMP_D3DCOLORWRITE_ALL", pipeline)
        self.assertIn("SAMP_D3DRS_BLENDOP, SAMP_D3DBLENDOP_ADD", pipeline)
        self.assertIn("SAMP_D3DRS_SCISSORTESTENABLE, 0u", pipeline)
        self.assertIn("set_texture(device, 0u, NULL)", pipeline)
        self.assertIn("SAMP_D3DTSS_COLORARG1, SAMP_D3DTA_DIFFUSE", pipeline)
        self.assertIn("SAMP_D3DTSS_ALPHAARG1, SAMP_D3DTA_DIFFUSE", pipeline)
        self.assertIn("apply_state_block", pipeline)

    def test_glass_panel_has_fill_header_highlight_and_border(self) -> None:
        panel = definition_body(
            self.source,
            "static void ui_compat_draw_glass_panel(",
        )
        self.assertGreaterEqual(panel.count("ui_compat_draw_blended_rect("), 2)
        self.assertIn("SAMP_MODERN_UI_PANEL_COLOR", panel)
        self.assertIn("SAMP_MODERN_UI_HEADER_COLOR", panel)
        self.assertIn("SAMP_MODERN_UI_BORDER_COLOR", panel)

    def test_scoreboard_uses_glass_panel_and_blended_row_states(self) -> None:
        scoreboard = definition_body(
            self.source,
            "static int scoreboard_compat_draw_d3dx_overlay(",
        )
        self.assertIn("ui_compat_draw_glass_panel(", scoreboard)
        self.assertIn("ui_compat_draw_blended_rect(", scoreboard)
        self.assertIn("SAMP_SCOREBOARD_COLOR_HOVER", scoreboard)
        self.assertIn("SAMP_MODERN_UI_BORDER_COLOR", scoreboard)

    def test_dialog_panel_and_buttons_use_glass_helpers(self) -> None:
        dialog = definition_body(
            self.source,
            "static int dialog_compat_draw_d3dx_overlay(",
        )
        button = definition_body(
            self.source,
            "static void dialog_compat_draw_button(",
        )
        self.assertIn("ui_compat_draw_glass_panel(", dialog)
        self.assertIn("ui_compat_draw_glass_control(", button)
        self.assertIn("dialog_compat_point_in_rect(", button)
        self.assertIn("dialog_mouse_down", button)

    def test_square_class_selection_is_the_default_glass_fallback(self) -> None:
        resources = definition_body(
            self.source,
            "static int class_selection_compat_ensure_resources(",
        )
        class_draw = definition_body(
            self.source,
            "static int class_selection_compat_draw_d3dx_overlay(",
        )

        env_read = resources.index(
            "getenv(SAMP_CLASS_SELECTION_R5_TEXTURE_ENV)"
        )
        opt_out = resources.index("if (!texture_style_enabled)", env_read)
        texture_use = resources.index(
            "if (g_runtime.class_selection_texture != NULL)",
            opt_out,
        )
        self.assertLess(env_read, opt_out)
        self.assertLess(opt_out, texture_use)
        self.assertIn("return 0;", resources[opt_out:texture_use])
        self.assertIn("USER_REQUESTED", resources)

        fallback_start = class_draw.index("if (!skin_drawn)")
        fallback = class_draw[fallback_start:]
        self.assertIn("ui_compat_draw_glass_panel(", class_draw)
        self.assertIn("ui_compat_draw_glass_control(", fallback)
        self.assertIn("class_selection_mouse_down", class_draw)
        self.assertIn("dialog_compat_point_in_rect(", class_draw)
        self.assertNotIn("sampgui.png", fallback)

    def test_class_selection_texture_colors_remain_separate_from_glass_palette(
        self,
    ) -> None:
        normal = define_value(
            self.source,
            "SAMP_CLASS_SELECTION_BUTTON_NORMAL_COLOR",
        )
        pressed = define_value(
            self.source,
            "SAMP_CLASS_SELECTION_BUTTON_PRESSED_COLOR",
        )
        self.assertNotEqual(normal, pressed)

        skin = definition_body(
            self.source,
            "static int class_selection_compat_draw_button_skin(",
        )
        self.assertIn("SAMP_CLASS_SELECTION_BUTTON_NORMAL_COLOR", skin)
        self.assertIn("SAMP_CLASS_SELECTION_BUTTON_PRESSED_COLOR", skin)
        self.assertIn("SAMP_CLASS_SELECTION_FILL_HOVER_COLOR", skin)
        self.assertIn("SAMP_CLASS_SELECTION_FILL_PRESSED_COLOR", skin)


if __name__ == "__main__":
    unittest.main()
