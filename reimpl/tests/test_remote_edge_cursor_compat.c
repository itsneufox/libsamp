#include "remote_edge_cursor_compat.h"

#include <assert.h>

static void expect_applied_then_defer_then_retry(void) {
  samp_remote_edge_cursor_decision_compat decision;
  uint32_t cursor = 0u;

  decision = samp_remote_edge_cursor_decide(
      cursor, 10u, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_APPLIED);
  cursor = decision.next_cursor;
  assert(cursor == 10u);

  decision = samp_remote_edge_cursor_decide(
      cursor, 11u, SAMP_REMOTE_EDGE_DEFER, 0u);
  assert(!decision.consume);
  assert(decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_DEFER);
  assert(decision.next_cursor == 10u);

  decision = samp_remote_edge_cursor_decide(
      cursor, 11u, SAMP_REMOTE_EDGE_APPLIED, 20u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_APPLIED);
  assert(decision.next_cursor == 11u);
}

static void expect_bounded_defer(void) {
  samp_remote_edge_cursor_decision_compat decision;

  decision = samp_remote_edge_cursor_decide(
      40u, 41u, SAMP_REMOTE_EDGE_DEFER,
      SAMP_REMOTE_EDGE_DEFER_MAX_MS - 1u);
  assert(!decision.consume);
  assert(decision.stop);
  assert(decision.next_cursor == 40u);

  decision = samp_remote_edge_cursor_decide(
      40u, 41u, SAMP_REMOTE_EDGE_DEFER,
      SAMP_REMOTE_EDGE_DEFER_MAX_MS);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_DROP);
  assert(decision.next_cursor == 41u);

  decision = samp_remote_edge_cursor_decide(
      40u, 41u, SAMP_REMOTE_EDGE_DEFER,
      SAMP_REMOTE_EDGE_DEFER_MAX_MS + 250u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_DROP);
  assert(decision.next_cursor == 41u);
}

static void expect_drop_stale_and_gap_input(void) {
  samp_remote_edge_cursor_decision_compat decision;

  decision = samp_remote_edge_cursor_decide(
      70u, 71u, SAMP_REMOTE_EDGE_DROP, 0u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.effective_result == SAMP_REMOTE_EDGE_DROP);
  assert(decision.next_cursor == 71u);

  decision = samp_remote_edge_cursor_decide(
      71u, 71u, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(!decision.consume);
  assert(!decision.stop);
  assert(decision.next_cursor == 71u);

  decision = samp_remote_edge_cursor_decide(
      71u, 0u, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(!decision.consume);
  assert(!decision.stop);
  assert(decision.next_cursor == 71u);

  decision = samp_remote_edge_cursor_decide(
      71u, 75u, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.next_cursor == 75u);

  decision = samp_remote_edge_cursor_decide(
      71u, 75u, SAMP_REMOTE_EDGE_DEFER, 0u);
  assert(!decision.consume);
  assert(decision.stop);
  assert(decision.next_cursor == 71u);

  decision = samp_remote_edge_cursor_decide(
      UINT32_MAX, 1u, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(decision.consume);
  assert(!decision.stop);
  assert(decision.next_cursor == 1u);
  assert(samp_remote_edge_seq_distance(UINT32_MAX, 1u) == 1u);
  assert(samp_remote_edge_seq_distance(UINT32_MAX - 1u, 1u) == 2u);

  decision = samp_remote_edge_cursor_decide(
      1u, UINT32_MAX, SAMP_REMOTE_EDGE_APPLIED, 0u);
  assert(!decision.consume);
  assert(!decision.stop);
  assert(decision.next_cursor == 1u);
}

int main(void) {
  expect_applied_then_defer_then_retry();
  expect_bounded_defer();
  expect_drop_stale_and_gap_input();
  return 0;
}
