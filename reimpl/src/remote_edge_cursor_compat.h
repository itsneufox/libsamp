#ifndef SAMPDLL_REMOTE_EDGE_CURSOR_COMPAT_H
#define SAMPDLL_REMOTE_EDGE_CURSOR_COMPAT_H

#include <stdint.h>

/*
 * INFERRED:
 * The shared 128-entry ring carries both Packet 200 and Packet 210, normally
 * about 56--60 events/s for one towing player. Keep the retry below that
 * ring's roughly 2.1-second overwrite window.
 */
#define SAMP_REMOTE_EDGE_DEFER_MAX_MS 2000u

typedef enum samp_remote_edge_apply_result_compat {
  SAMP_REMOTE_EDGE_APPLIED = 0,
  SAMP_REMOTE_EDGE_DEFER = 1,
  SAMP_REMOTE_EDGE_DROP = 2
} samp_remote_edge_apply_result_compat;

typedef struct samp_remote_edge_cursor_decision_compat {
  uint32_t next_cursor;
  samp_remote_edge_apply_result_compat effective_result;
  int consume;
  int stop;
} samp_remote_edge_cursor_decision_compat;

static inline int samp_remote_edge_seq_is_newer(uint32_t cursor,
                                                uint32_t candidate) {
  if (candidate == 0u) {
    return 0;
  }
  if (cursor == 0u) {
    return 1;
  }
  return (int32_t)(candidate - cursor) > 0;
}

static inline uint32_t samp_remote_edge_seq_distance(uint32_t cursor,
                                                     uint32_t candidate) {
  uint32_t distance = candidate - cursor;
  if (candidate < cursor && distance > 0u) {
    --distance;
  }
  return distance;
}

/*
 * PROBE_TRACE + INFERRED:
 * A runtime dependency may lag network delivery while GTA entities are
 * created. Retain the shared arrival-order head for a bounded interval, then
 * consume it as a drop so one invalid live pointer cannot block every remote
 * player behind the global movement stream.
 */
static inline samp_remote_edge_cursor_decision_compat
samp_remote_edge_cursor_decide(uint32_t cursor, uint32_t movement_seq,
                               samp_remote_edge_apply_result_compat result,
                               uint32_t defer_age_ms) {
  samp_remote_edge_cursor_decision_compat decision;

  decision.next_cursor = cursor;
  decision.effective_result = result;
  decision.consume = 0;
  decision.stop = 0;

  if (!samp_remote_edge_seq_is_newer(cursor, movement_seq)) {
    return decision;
  }
  if (result == SAMP_REMOTE_EDGE_DEFER &&
      defer_age_ms < SAMP_REMOTE_EDGE_DEFER_MAX_MS) {
    decision.stop = 1;
    return decision;
  }
  if (result == SAMP_REMOTE_EDGE_DEFER) {
    decision.effective_result = SAMP_REMOTE_EDGE_DROP;
  } else if (result != SAMP_REMOTE_EDGE_APPLIED &&
             result != SAMP_REMOTE_EDGE_DROP) {
    decision.effective_result = SAMP_REMOTE_EDGE_DROP;
  }
  decision.next_cursor = movement_seq;
  decision.consume = 1;
  return decision;
}

#endif
