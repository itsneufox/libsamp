import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("analyze_trailer_physics.py")
SPEC = importlib.util.spec_from_file_location("analyze_trailer_physics", MODULE_PATH)
assert SPEC and SPEC.loader
analyzer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = analyzer
SPEC.loader.exec_module(analyzer)


def main_line(
    *,
    seq: int,
    event: int,
    kind: str,
    generation: int,
    frame: int,
    trailer_dpos: str,
    tractor_dpos: str = "(0.000000,0.000000,0.000000)",
    game_ms: int = 1000,
) -> str:
    return (
        f"[ {game_ms:9d}] trailer_physics: seq={seq} event={event} kind={kind} "
        f"generation={generation} frame={frame} trailer=0x10000000 "
        "tractor=0x20000000 set_my_pos_raw=0x00000001 result=1 "
        f"pre_tick={game_ms} pre_thread=7 pre_valid=0x07 pre_gta_frame={frame + 20} "
        f"pre_game_ms={game_ms} pre_timestep=1.000000 "
        f"post_tick={game_ms} post_thread=7 post_valid=0x07 "
        f"post_gta_frame={frame + 20} post_game_ms={game_ms} "
        f"post_timestep=1.000000 trailer_dpos={trailer_dpos} "
        f"tractor_dpos={tractor_dpos} evidence=PROBE_TRACE"
    )


def state_line(
    *,
    seq: int,
    event: int,
    generation: int,
    frame: int,
    phase: str,
    trailer_object: str,
    tractor_object: str,
    trailer_tow: str,
    tractor_reverse: str,
    trailer_x: float,
) -> str:
    return (
        f"[      1000] trailer_physics_state: seq={seq} event={event} "
        f"generation={generation} frame={frame} phase={phase} "
        f"trailer={trailer_object} valid=0x07 vtable=0x11111111 matrix=0x11112222 "
        "basis_r=(1.000000,0.000000,0.000000) "
        "basis_f=(0.000000,1.000000,0.000000) "
        "basis_u=(0.000000,0.000000,1.000000) "
        f"pos=({trailer_x:.6f},2.000000,3.000000) "
        "move=(0.100000,0.000000,0.000000) "
        "turn=(0.000000,0.000000,0.010000) flags=0x00000001 "
        f"status=0x02 fake=0x00 tow={trailer_tow} reverse=0x00000000 "
        f"tractor={tractor_object} valid=0x03 vtable=0x22222222 matrix=0x22223333 "
        "basis_r=(1.000000,0.000000,0.000000) "
        "basis_f=(0.000000,1.000000,0.000000) "
        "basis_u=(0.000000,0.000000,1.000000) "
        "pos=(1.000000,2.000000,3.000000) "
        "move=(0.100000,0.000000,0.000000) "
        "turn=(0.000000,0.000000,0.010000) flags=0x00000001 "
        f"status=0x02 fake=0x00 tow=0x00000000 reverse={tractor_reverse}"
    )


def detail_line(
    *,
    seq: int,
    event: int,
    generation: int,
    frame: int,
    phase: str,
    support_x: float = 1.0,
) -> str:
    return (
        f"[      1000] trailer_physics_detail: seq={seq} event={event} "
        f"generation={generation} frame={frame} phase={phase} trailer_valid=0x07 "
        f"support=({support_x:.6f},2.000000,3.000000,4.000000,5.000000) "
        "wheel=(0.100000,0.200000,0.300000,0.400000) "
        "wheel_prev=(0.100000,0.200000,0.300000,0.400000) "
        "spring=(1.000000,1.000000,1.000000,1.000000) "
        "line=(1.000000,1.000000,1.000000,1.000000) "
        "ride=(0.500000,0.600000) evidence=PROBE_TRACE"
    )


def record_lines(
    *,
    seq: int,
    event: int,
    kind: str,
    generation: int,
    frame: int,
    trailer_dpos: str,
    pointer_bias: int = 0,
    trailer_x: float = 1.0,
    game_ms: int = 1000,
    linked: bool = True,
) -> list[str]:
    trailer = f"0x{0x10000000 + pointer_bias:08x}"
    tractor = f"0x{0x20000000 + pointer_bias:08x}"
    no_pointer = "0x00000000"
    lines = [
        main_line(
            seq=seq,
            event=event,
            kind=kind,
            generation=generation,
            frame=frame,
            trailer_dpos=trailer_dpos,
            game_ms=game_ms,
        )
    ]
    for phase in ("pre", "post"):
        relation_active = linked and (phase == "post" or kind == "process_control")
        lines.append(
            state_line(
                seq=seq,
                event=event,
                generation=generation,
                frame=frame,
                phase=phase,
                trailer_object=trailer,
                tractor_object=tractor,
                trailer_tow=tractor if relation_active else no_pointer,
                tractor_reverse=trailer if relation_active else no_pointer,
                trailer_x=trailer_x,
            )
        )
        lines.append(
            detail_line(
                seq=seq,
                event=event,
                generation=generation,
                frame=frame,
                phase=phase,
            )
        )
    return lines


class ParseTests(unittest.TestCase):
    def test_correlates_main_state_and_detail_and_normalizes_links(self):
        text = "\n".join(
            record_lines(
                seq=1,
                event=9,
                kind="set_tow_link",
                generation=3,
                frame=0,
                trailer_dpos="(1.000000,0.000000,0.000000)",
                pointer_bias=0x1234,
            )
        )

        trace = analyzer.parse_trace(text)

        self.assertEqual(len(trace.records), 1)
        record = trace.records[0]
        self.assertEqual(set(record.states), {"pre", "post"})
        self.assertEqual(set(record.details), {"pre", "post"})
        self.assertFalse(analyzer._link_state(record, "pre")["bidirectional"])
        self.assertTrue(analyzer._link_state(record, "post")["bidirectional"])
        summary = analyzer.summarize_trace(trace)
        self.assertEqual(summary["set_tow_link"]["events"], 1)
        self.assertEqual(summary["set_tow_link"]["trailer_jump_m"]["max"], 1.0)
        self.assertEqual(summary["set_tow_link"]["bidirectional_link_post"], 1)

    def test_reports_partial_frame_coverage_overflow_and_orphan(self):
        lines = ["trailer_physics: overflow skipped=3 total_skipped=3 write_seq=515"]
        lines.extend(
            record_lines(
                seq=1,
                event=1,
                kind="set_tow_link",
                generation=4,
                frame=0,
                trailer_dpos="(0.000000,0.000000,0.000000)",
            )
        )
        lines.extend(
            record_lines(
                seq=2,
                event=2,
                kind="process_control",
                generation=4,
                frame=0,
                trailer_dpos="(0.100000,0.000000,0.000000)",
            )
        )
        lines.extend(
            record_lines(
                seq=3,
                event=3,
                kind="process_control",
                generation=4,
                frame=1,
                trailer_dpos="(0.200000,0.000000,0.000000)",
                game_ms=1033,
            )
        )
        lines.append(
            detail_line(
                seq=99,
                event=99,
                generation=99,
                frame=0,
                phase="pre",
            )
        )

        trace = analyzer.parse_trace("\n".join(lines))
        summary = analyzer.summarize_trace(trace)
        process = summary["generations"][0]["process_control"]

        self.assertEqual(summary["parse"]["overflow_skipped"], 3)
        self.assertEqual(len(summary["parse"]["orphan_auxiliary_lines"]), 1)
        self.assertEqual(process["frames_observed"], 2)
        self.assertEqual(process["contiguous_prefix_frames"], 2)
        self.assertEqual(process["missing_first_64"][:2], [2, 3])
        self.assertAlmostEqual(process["trailer_step_m"]["mean"], 0.15)
        self.assertEqual(process["elapsed_game_ms"]["max"], 33.0)

    def test_malformed_physics_record_is_nonfatal(self):
        trace = analyzer.parse_trace(
            "prefix trailer_physics: seq=no event=1 kind=process_control "
            "generation=1 frame=0\n"
        )
        self.assertEqual(trace.records, [])
        self.assertEqual(trace.malformed_lines, [1])


class DiffTests(unittest.TestCase):
    def _trace(
        self,
        *,
        pointer_bias: int,
        attach_delta: float,
        frame_delta: float,
        trailer_x: float,
        frame_one: bool = False,
    ):
        lines = record_lines(
            seq=1,
            event=1,
            kind="set_tow_link",
            generation=10 + pointer_bias,
            frame=0,
            trailer_dpos=f"({attach_delta:.6f},0.000000,0.000000)",
            pointer_bias=pointer_bias,
            trailer_x=trailer_x,
        )
        lines.extend(
            record_lines(
                seq=2,
                event=2,
                kind="process_control",
                generation=10 + pointer_bias,
                frame=0,
                trailer_dpos=f"({frame_delta:.6f},0.000000,0.000000)",
                pointer_bias=pointer_bias,
                trailer_x=trailer_x,
            )
        )
        if frame_one:
            lines.extend(
                record_lines(
                    seq=3,
                    event=3,
                    kind="process_control",
                    generation=10 + pointer_bias,
                    frame=1,
                    trailer_dpos=f"({frame_delta:.6f},0.000000,0.000000)",
                    pointer_bias=pointer_bias,
                    trailer_x=trailer_x,
                    game_ms=1033,
                )
            )
        return analyzer.parse_trace("\n".join(lines))

    def test_diff_pairs_by_encounter_order_and_ignores_raw_pointers(self):
        original = self._trace(
            pointer_bias=0,
            attach_delta=0.1,
            frame_delta=0.1,
            trailer_x=1.0,
            frame_one=True,
        )
        replacement = self._trace(
            pointer_bias=100,
            attach_delta=1.1,
            frame_delta=0.4,
            trailer_x=3.0,
        )

        result = analyzer.compare_traces(original, replacement)
        pair = result["generation_pairs"][0]

        self.assertEqual(
            result["generation_pairing_policy"],
            "successful_attach_encounter_order",
        )
        self.assertEqual(result["set_tow_link_comparison"]["original_events"], 1)
        self.assertEqual(
            result["set_tow_link_comparison"]["replacement_events"], 1
        )
        self.assertEqual(
            result["pointer_policy"],
            "raw_addresses_ignored_relationships_compared",
        )
        self.assertAlmostEqual(
            pair["attach"]["trailer_jump_vector_delta_m"], 1.0
        )
        self.assertEqual(pair["frames"]["common_indices"], [0])
        self.assertEqual(pair["frames"]["missing_in_replacement"], [1])
        self.assertAlmostEqual(
            pair["metrics"]["trailer_step_vector_delta_m"]["max"], 0.3
        )
        self.assertEqual(
            pair["metrics"]["trailer_pre_position_residual_m"]["max"], 2.0
        )
        self.assertEqual(pair["state_mismatches"]["pre_link"], 0)
        self.assertEqual(pair["state_mismatches"]["post_link"], 0)


class CliTests(unittest.TestCase):
    def test_artifact_discovery_prefers_windows_non_root_documents_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collected = root / "windows/run/latest_log_bytes"
            collected.mkdir(parents=True)
            active = collected / "samp_probe.log"
            active.write_text(
                "\n".join(
                    record_lines(
                        seq=1,
                        event=1,
                        kind="set_tow_link",
                        generation=1,
                        frame=0xFFFFFFFF,
                        trailer_dpos="(0.000000,0.000000,0.000000)",
                    )
                ),
                encoding="utf-8",
            )
            (collected / "samp_probe.root.log").write_text("", encoding="utf-8")
            (root / "pilot/client").mkdir(parents=True)
            (root / "pilot/client/samp_probe.log").write_text(
                "unrelated host-side log\n", encoding="utf-8"
            )

            trace = analyzer.load_trace(root)

            self.assertEqual(trace.source, str(active.resolve()))
            self.assertEqual(len(trace.records), 1)

    def test_summary_writes_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "samp_probe.log"
            output = root / "summary.json"
            source.write_text(
                "\n".join(
                    record_lines(
                        seq=1,
                        event=1,
                        kind="set_tow_link",
                        generation=1,
                        frame=0,
                        trailer_dpos="(0.000000,0.000000,0.000000)",
                    )
                ),
                encoding="utf-8",
            )

            with mock.patch("builtins.print"):
                return_code = analyzer.main(
                    ["summary", str(source), "--output", str(output)]
                )

            self.assertEqual(return_code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["evidence"], "PROBE_TRACE")
            self.assertEqual(result["assessment"], "MEASURED_NO_PARITY_THRESHOLD")


if __name__ == "__main__":
    unittest.main()
