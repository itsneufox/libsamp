#!/usr/bin/env python3
"""Static contracts for the bounded Windows TAB/F6/F7 lab actions."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTE_LAB = REPO_ROOT / "tools/windows/remote_lab"
UI_KEYS = ("TAB", "F6", "F7")


def read(name: str) -> str:
    return (REMOTE_LAB / name).read_text(encoding="utf-8")


class WindowsUiKeySourceContractTests(unittest.TestCase):
    def test_all_external_allowlists_contain_exact_ui_keys(self) -> None:
        input_script = read("Send-SampTestInput.ps1")
        queue_script = read("Submit-SampTestCommand.ps1")
        wrapper = read("samp_lab.sh")

        for key in UI_KEYS:
            self.assertIn(f'"{key}"', input_script)
            self.assertIn(f'"{key}"', queue_script)
            self.assertRegex(wrapper, rf"\b{key}\b")

        self.assertIn(
            'ENTER|ESCAPE|SPACE|ALTENTER|TAB|F6|F7|UP|DOWN',
            wrapper,
        )
        self.assertIn(
            '[ValidateSet("ENTER", "ESCAPE", "SPACE", "ALTENTER", '
            '"TAB", "F6", "F7", "UP"',
            input_script,
        )
        self.assertIn(
            '[ValidateSet("ENTER", "ESCAPE", "SPACE", "ALTENTER", '
            '"TAB", "F6", "F7", "UP"',
            queue_script,
        )

    def test_ui_actions_are_real_bounded_down_up_pairs(self) -> None:
        source = read("Send-SampTestInput.ps1")
        match = re.search(
            r'\} elseif \(\$Key -in @\("TAB", "F6", "F7"\)\) \{'
            r"(?P<body>.*?)"
            r'\} elseif \(\$Key -in @\("SPACE", "UP"',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        body = match.group("body")  # type: ignore[union-attr]

        for key, virtual_key, scan_code in (
            ("TAB", "0x09", "0x0F"),
            ("F6", "0x75", "0x40"),
            ("F7", "0x76", "0x41"),
        ):
            self.assertIn(f'"{key}" {{ {virtual_key} }}', body)
            self.assertIn(f'"{key}" {{ {scan_code} }}', body)

        self.assertIn(
            "keybd_event($virtualKey, $scanCode, 0, [UIntPtr]::Zero)",
            body,
        )
        self.assertIn("try {", body)
        self.assertIn("finally {", body)
        self.assertIn(
            "keybd_event($virtualKey, $scanCode, 0x0002, "
            "[UIntPtr]::Zero)",
            body,
        )
        self.assertIn(
            'if ($Key -eq "TAB") { 750 } else { 100 }',
            body,
        )
        self.assertNotIn("SendKeys", body)

    def test_agent_routes_through_the_validated_input_script(self) -> None:
        source = read("SampTestAgent.ps1")
        self.assertIn('"input" {', source)
        self.assertIn(
            'Join-Path $PSScriptRoot "Send-SampTestInput.ps1"',
            source,
        )
        self.assertIn("-Mode $mode -Key $key", source)


if __name__ == "__main__":
    unittest.main()
