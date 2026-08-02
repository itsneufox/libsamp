#!/usr/bin/env python3
"""Source-contract tests for the observed R5 RemoveBuilding rule lifecycle."""

from __future__ import annotations

import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


class RemoveBuildingSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        start = cls.source.index(
            "static void remove_building_store_event_compat("
        )
        end = cls.source.index(
            "static void remove_building_compat_update_from_snapshot(", start
        )
        cls.body = cls.source[start:end]

    def test_duplicate_rules_are_appended(self) -> None:
        self.assertNotIn("remove_building_event_equal_compat", self.source)
        self.assertNotIn("memcmp(", self.body)
        self.assertIn(
            "g_runtime.remove_building_records[count] = *event;", self.body
        )
        self.assertIn(
            "InterlockedExchange(&g_runtime.remove_building_record_count, count + 1);",
            self.body,
        )

    def test_observed_r5_evidence_is_recorded(self) -> None:
        self.assertIn("OBSERVED_037 + PROBE_TRACE + STATIC_037", self.body)
        self.assertIn("samp.dll+0x9D3D0", self.body)
        self.assertIn(
            "20260728-144428-distributed-sync-gmx-1646159", self.body
        )

    def test_conservative_capacity_guard_remains(self) -> None:
        guard = self.body.index(
            "if (count >= (LONG)SAMP_REMOVE_BUILDING_COMPAT_MAX)"
        )
        write = self.body.index(
            "g_runtime.remove_building_records[count] = *event;"
        )
        self.assertLess(guard, write)
        self.assertIn("remove_building: record_overflow", self.body)


if __name__ == "__main__":
    unittest.main()
