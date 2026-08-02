#!/usr/bin/env python3
"""Source-contract tests for the observed R5 local respawn ordering."""

from __future__ import annotations

import unittest
from pathlib import Path


RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[2] / "reimpl" / "src" / "runtime_bridge.c"
)


def function_body(source: str, name: str, next_name: str) -> str:
    declaration = f"static int {name}("
    first = source.index(declaration)
    start = source.index(declaration, first + len(declaration))
    end = source.index(f"static int {next_name}(", start)
    return source[start:end]


class LocalRespawnSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = RUNTIME_SOURCE.read_text(encoding="utf-8")

    def test_wasted_latch_precedes_death_rpc_result(self) -> None:
        body = function_body(
            self.source,
            "local_death_compat_process_report",
            "class_selection_compat_process_after_death_latch",
        )

        latch = body.index(
            "InterlockedExchange(&g_runtime.local_death_reported, 1);"
        )
        send = body.index("samp_raknet_client_send_death_notification(")
        self.assertLess(latch, send)
        self.assertNotIn(
            "if (result == 0) {\n"
            "    InterlockedExchange(&g_runtime.local_death_reported, 1);",
            body,
        )

    def test_health_recovery_reopens_cached_spawn_without_new_spawn_info(self) -> None:
        body = function_body(
            self.source,
            "local_death_compat_process_report",
            "class_selection_compat_process_after_death_latch",
        )

        reopen = body.index(
            "InterlockedExchange(&g_runtime.mp_session_finalized_spawn_seq, 0);"
        )
        pending = body.index(
            "InterlockedExchange(&g_runtime.local_respawn_pending, "
            "SAMP_LOCAL_RESPAWN_PENDING_APPLY);"
        )
        self.assertLess(reopen, pending)
        self.assertNotIn("raknet_spawn_info_seq, 1", body)
        self.assertNotIn("send_respawn_notification", body)

    def test_full_local_spawn_completes_before_unguarded_respawn_rpc(self) -> None:
        apply_start = self.source.index(
            "static void apply_multiplayer_session_bridge_compat("
        )
        apply_body = self.source[apply_start:]

        restart = apply_body.index("gta_restart_if_wasted_at_compat(")
        teleport = apply_body.index('runtime_tracef("mp_session_bridge: spawn_teleport_end')
        complete = apply_body.index(
            'runtime_tracef("local_death: respawn_apply_complete'
        )
        send = apply_body.index("samp_raknet_client_send_respawn_notification(")
        self.assertLess(restart, teleport)
        self.assertLess(teleport, complete)
        self.assertLess(complete, send)

        initial_notify = apply_body.index(
            "samp_raknet_client_send_spawn_notification_for_seq("
        )
        pending_guard = apply_body.rfind(
            "respawn_pending != SAMP_LOCAL_RESPAWN_PENDING_APPLY",
            0,
            initial_notify,
        )
        self.assertNotEqual(-1, pending_guard)

    def test_sync_waits_until_respawn_rpc_is_queued(self) -> None:
        apply_start = self.source.index(
            "static void apply_multiplayer_session_bridge_compat("
        )
        apply_body = self.source[apply_start:]
        sync_gate = (
            "InterlockedCompareExchange(&g_runtime.local_death_reported, 0, 0) == 0 &&\n"
            "               InterlockedCompareExchange(&g_runtime.local_respawn_pending, 0, 0) == 0"
        )
        self.assertIn(sync_gate, apply_body)


if __name__ == "__main__":
    unittest.main()
