#!/usr/bin/env python3
"""Source-contract tests for the original-R5 terminal cleanup checkpoint."""

from __future__ import annotations

import unittest
from pathlib import Path


PROBE_ROOT = Path(__file__).resolve().parents[1]
DEATH_CLEANUP_SOURCE = (
    PROBE_ROOT / "src" / "samp_probe_death_cleanup.c"
)
ASI_SOURCE = PROBE_ROOT / "src" / "samp_probe_asi.c"


def definition_body(source: str, declaration: str, next_declaration: str) -> str:
    cursor = 0
    while True:
        candidate = source.index(declaration, cursor)
        brace = source.index("{", candidate)
        semicolon = source.index(";", candidate)
        if brace < semicolon:
            start = candidate
            break
        cursor = candidate + len(declaration)
    end = source.index(next_declaration, start)
    return source[start:end]


class DeathCleanupExitSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.death_cleanup = DEATH_CLEANUP_SOURCE.read_text(encoding="utf-8")
        cls.asi = ASI_SOURCE.read_text(encoding="utf-8")

    def test_r5_exit_callsite_and_iat_are_exactly_guarded(self) -> None:
        source = self.death_cleanup
        self.assertIn(
            "#define PROBE_DC_EXITPROCESS_CALLSITE_RVA 0x000c508au",
            source,
        )
        self.assertIn(
            "#define PROBE_DC_EXITPROCESS_CALLER_RVA 0x000c5091u",
            source,
        )
        self.assertIn(
            "#define PROBE_DC_EXITPROCESS_IAT_RVA 0x000e5188u",
            source,
        )
        self.assertIn(
            "0x57, 0xff, 0x15, 0x88, 0x51, 0x0e,\n"
            "    0x10, 0x61, 0x5f, 0x5e, 0x5b, 0xc3",
            source,
        )
        preflight = definition_body(
            source,
            "static int dc_preflight(void)",
            "static int dc_rel32(",
        )
        self.assertIn("PROBE_DC_EXITPROCESS_CALLSITE_RVA", preflight)
        self.assertIn("PROBE_DC_EXITPROCESS_IAT_RVA", preflight)
        self.assertIn("dc_exit_iat_target_matches()", preflight)

    def test_only_clean_quit_caller_requests_bounded_worker_drain(self) -> None:
        body = definition_body(
            self.death_cleanup,
            "static VOID WINAPI hook_dc_exit_process(UINT exit_code)",
            "static int dc_bytes_match(",
        )
        self.assertIn(
            "caller_rva != PROBE_DC_EXITPROCESS_CALLER_RVA",
            body,
        )
        self.assertIn(
            "InterlockedCompareExchange(&g_dc_install_state, 0, 0) != 1",
            body,
        )
        preparing = body.index(
            "InterlockedCompareExchange(&g_dc_terminal_state, -1, 0)"
        )
        ready = body.index(
            "InterlockedExchange(&g_dc_terminal_state, 1)"
        )
        self.assertIn(
            "#define PROBE_DC_TERMINAL_DRAIN_TIMEOUT_MS 1500u",
            self.death_cleanup,
        )
        signal = body.index("SetEvent(g_dc_terminal_stop_event)")
        wait = body.index("WaitForSingleObject(g_dc_terminal_done_event")
        final_exit = body.rindex("dc_invoke_original_exit_process(exit_code)")
        self.assertLess(preparing, ready)
        self.assertLess(ready, signal)
        self.assertLess(signal, wait)
        self.assertLess(wait, final_exit)
        self.assertNotIn("probe_log(", body)
        self.assertNotIn("log_fn(", body)

    def test_iat_patch_is_owned_and_all_or_nothing(self) -> None:
        source = self.death_cleanup
        install = definition_body(
            source,
            "int probe_death_cleanup_install(HMODULE samp_module",
            "static const char *dc_event_name(",
        )
        self.assertIn("if (!dc_install_exit_iat())", install)
        failure = install[install.index("if (!dc_install_exit_iat())") :]
        self.assertIn("dc_restore_one(&g_dc_hooks[installed])", failure)
        self.assertIn("dc_close_terminal_done_event(log_fn)", failure)

        restore = definition_body(
            source,
            "static int dc_restore_exit_iat(void)",
            "int probe_death_cleanup_install(HMODULE samp_module",
        )
        self.assertIn("InterlockedCompareExchangePointer(", restore)
        self.assertIn("original, replacement", restore)

    def test_worker_flushes_restores_and_acknowledges_before_exit(self) -> None:
        worker_start = self.asi.index("static DWORD WINAPI probe_worker(")
        worker_end = self.asi.index(
            "static int WINAPI hook_samp_socketlayer_sendto(",
            worker_start,
        )
        worker = self.asi[worker_start:worker_end]

        final_flush = worker.rindex("probe_death_cleanup_flush(probe_log)")
        uninstall = worker.rindex(
            "probe_death_cleanup_uninstall(probe_log)"
        )
        stopping = worker.rindex('probe_log("probe: stopping")')
        complete = worker.rindex(
            "probe_death_cleanup_complete_terminal_drain(probe_log)"
        )
        self.assertLess(final_flush, uninstall)
        self.assertLess(uninstall, stopping)
        self.assertLess(stopping, complete)
        self.assertEqual(
            2,
            worker.count(
                'env_flag_enabled("SAMP_PROBE_NO_SAMP_CODE_HOOKS"), '
                "g_stop_event,"
            ),
        )

    def test_terminal_marker_proves_ring_boundary_and_final_pointer(self) -> None:
        complete = self.death_cleanup[
            self.death_cleanup.index(
                "void probe_death_cleanup_complete_terminal_drain("
            ) :
        ]
        self.assertIn('"death_cleanup_exit_r5:', complete)
        self.assertIn("destructor_seq=%ld", complete)
        self.assertIn("requested_seq=%ld flushed_seq=%ld", complete)
        self.assertIn('drain=%s timeout_ms=%u', complete)
        self.assertIn("exit_iat_restored=%d", complete)
        self.assertIn("SetEvent(g_dc_terminal_done_event)", complete)


if __name__ == "__main__":
    unittest.main()
