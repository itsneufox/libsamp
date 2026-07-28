#!/usr/bin/env python3
"""Source contracts for the focused original-R5 pickup memory probe."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PICKUP_SOURCE = REPO_ROOT / "tools/asi_probe/src/samp_probe_pickup.c"
ASI_SOURCE = REPO_ROOT / "tools/asi_probe/src/samp_probe_asi.c"
ASI_CMAKE = REPO_ROOT / "tools/asi_probe/CMakeLists.txt"
PROFILE_SOURCE = (
    REPO_ROOT / "tools/windows/remote_lab/Set-SampProbeProfile.ps1"
)
LAB_WRAPPER = REPO_ROOT / "tools/windows/remote_lab/samp_lab.sh"
PROBE_README = REPO_ROOT / "tools/asi_probe/README.md"
EVIDENCE_DOC = REPO_ROOT / "docs/re/pickup_memory_probe_r5_20260728.md"


def body_between(source: str, start: str, end: str) -> str:
    start_offset = source.rindex(start)
    end_offset = source.index(end, start_offset + len(start))
    return source[start_offset:end_offset]


class PickupProbeSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pickup = PICKUP_SOURCE.read_text(encoding="utf-8")
        cls.asi = ASI_SOURCE.read_text(encoding="utf-8")
        cls.profile = PROFILE_SOURCE.read_text(encoding="utf-8")
        cls.readme = PROBE_README.read_text(encoding="utf-8")
        cls.evidence = EVIDENCE_DOC.read_text(encoding="utf-8")

    def test_exact_r5_identity_hooks_and_layout_are_guarded(self) -> None:
        required = (
            "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2",
            "PROBE_PICKUP_PICKED_UP_RVA 0x00013440u",
            "PROBE_PICKUP_PROCESS_RVA 0x00013520u",
            "PROBE_PICKUP_PROCESS_GATE_RVA 0x00118a10u",
            "PROBE_PICKUP_HANDLE_OFFSET 0x00000004u",
            "PROBE_PICKUP_RAW_GTA_INDEX_OFFSET 0x00004004u",
            "PROBE_PICKUP_TIMER_OFFSET 0x00008004u",
            "PROBE_PICKUP_DROPPED_OFFSET 0x0000c004u",
            "PROBE_PICKUP_DATA_OFFSET 0x0000f004u",
            "PROBE_PICKUP_DATA_STRIDE 0x14u",
            "PROBE_PICKUP_CAPACITY 4096u",
        )
        for token in required:
            self.assertIn(token, self.pickup)

        self.assertIn(
            "return pickup_bytes_match(0x00013500u, picked_up_tail,",
            self.pickup,
        )
        self.assertIn(
            "pickup_bytes_match(0x00013655u, process_tail,",
            self.pickup,
        )
        self.assertIn("pickup_preflight()", self.pickup)
        self.assertIn("pickup_process_gate_bytes_match()", self.pickup)
        self.assertIn("memcpy(expected + 2u, &relocated_gate", self.pickup)
        self.assertIn("incomplete_install installed=0", self.pickup)
        self.assertIn("pickup_patch_is_owned", self.pickup)

    def test_hook_threads_only_publish_to_the_bounded_ring(self) -> None:
        picked_up = body_between(
            self.pickup,
            "static void PROBE_PICKUP_THISCALL hook_pickup_picked_up(",
            "static void PROBE_PICKUP_THISCALL hook_pickup_process(",
        )
        process = body_between(
            self.pickup,
            "static void PROBE_PICKUP_THISCALL hook_pickup_process(",
            "void probe_pickup_observe_rpc(",
        )
        observer = body_between(
            self.pickup,
            "void probe_pickup_observe_rpc(",
            "static int pickup_bytes_match(",
        )
        for hook_body in (picked_up, process, observer):
            self.assertIn("pickup_publish_trace", hook_body)
            self.assertNotIn("log_fn(", hook_body)
            self.assertNotIn("CreateFile", hook_body)
            self.assertNotIn("fopen", hook_body)

        self.assertIn("#define PROBE_PICKUP_TRACE_RING_SIZE 256u", self.pickup)
        self.assertIn("probe_pickup_flush(probe_log);", self.asi)

    def test_outgoing_pickup_rpcs_share_the_existing_vtable_hook(self) -> None:
        rpc_hook = body_between(
            self.asi,
            "static BYTE PROBE_THISCALL hook_rakclient_rpc_bitstream(",
            "static int install_dialog_menu_rpc_hook(",
        )
        original_call = rpc_hook.index(
            "g_orig_rakclient_rpc_bitstream)("
        )
        observation = rpc_hook.rindex("probe_pickup_observe_rpc(")
        self.assertLess(original_call, observation)
        self.assertIn("rpc_id == PROBE_PICKUP_RPC", rpc_hook)
        self.assertIn("rpc_id == PROBE_PICKUP_WEAPON_RPC", rpc_hook)
        self.assertIn("probe_pickup_is_active()", rpc_hook)
        self.assertNotIn("pickup_hooks_enabled()", rpc_hook)

        observer = body_between(
            self.pickup,
            "void probe_pickup_observe_rpc(",
            "static int pickup_bytes_match(",
        )
        self.assertIn("bits >= 32", observer)
        self.assertIn("bits >= 16", observer)
        self.assertIn("g_pickup_install_state", observer)

    def test_profile_build_and_documentation_wiring_is_complete(self) -> None:
        self.assertIn("src/samp_probe_pickup.c", ASI_CMAKE.read_text())
        self.assertIn('"pickup-r5"', self.profile)
        self.assertIn('"samp_probe_pickup_hooks.flag"', self.profile)
        self.assertIn(
            "death-cleanup|pickup-r5|ui-latches-r5",
            LAB_WRAPPER.read_text(encoding="utf-8"),
        )
        self.assertIn("SAMP_PROBE_PICKUP_HOOKS=1", self.readme)
        self.assertIn("pickup_r5", self.readme)
        self.assertIn("STATIC_037", self.evidence)
        self.assertIn("TODO_VERIFY", self.evidence)
        self.assertIn("samp.dll+0x00013440", self.evidence)
        self.assertIn("samp.dll+0x00013520", self.evidence)
        self.assertIn("samp.dll+0x00118A10", self.evidence)
        self.assertIn("but no new\noriginal-R5 runtime trace", self.evidence)


if __name__ == "__main__":
    unittest.main()
