#ifndef SAMPDLL_REMOTE_VEHICLE_PLAYBACK_COMPAT_H
#define SAMPDLL_REMOTE_VEHICLE_PLAYBACK_COMPAT_H

#include <math.h>
#include <stddef.h>
#include <string.h>

#define SAMP_REMOTE_VEHICLE_POSITION_EPSILON 0.05f
#define SAMP_REMOTE_VEHICLE_POSITION_SNAP_XY 8.0f
#define SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z 0.5f
#define SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z_AIR_WATER 2.0f
#define SAMP_REMOTE_VEHICLE_POSITION_CORRECTION 0.06f
#define SAMP_REMOTE_VEHICLE_CORRECTED_SPEED_EPSILON 0.01f
#define SAMP_REMOTE_VEHICLE_TURN_SPEED_LIMIT 0.02f
#define SAMP_REMOTE_VEHICLE_QUATERNION_SLERP 0.75f
#define SAMP_REMOTE_TRAILER_POSITION_EPSILON 0.5f
#define SAMP_REMOTE_TRAILER_POSITION_SNAP_XY 6.0f
#define SAMP_REMOTE_TRAILER_POSITION_SNAP_Z 3.0f

typedef enum samp_remote_vehicle_position_decision_compat {
  SAMP_REMOTE_VEHICLE_DECISION_INVALID = 0,
  SAMP_REMOTE_VEHICLE_DECISION_NOOP,
  SAMP_REMOTE_VEHICLE_DECISION_CORRECT,
  SAMP_REMOTE_VEHICLE_DECISION_SNAP
} samp_remote_vehicle_position_decision_compat;

typedef enum samp_remote_trailer_position_decision_compat {
  SAMP_REMOTE_TRAILER_DECISION_INVALID = 0,
  SAMP_REMOTE_TRAILER_DECISION_TRANSITION,
  SAMP_REMOTE_TRAILER_DECISION_NOOP,
  SAMP_REMOTE_TRAILER_DECISION_CORRECT,
  SAMP_REMOTE_TRAILER_DECISION_SNAP
} samp_remote_trailer_position_decision_compat;

/*
 * OBSERVED_037 + PROBE_TRACE:
 * A Packet-210 association transition is distinct from ordinary positional
 * correction. R5 calls SetTowLink and then publishes the exact Packet-210
 * transform even when the position sampled before SetTowLink was inside the
 * normal 0.5-m deadband.
 */
static inline samp_remote_trailer_position_decision_compat
samp_remote_trailer_position_decision_r5(
    const float current_position[3], const float target_position[3],
    int association_transition, float delta_out[3]) {
  unsigned int i = 0u;

  if (current_position == NULL || target_position == NULL ||
      delta_out == NULL) {
    return SAMP_REMOTE_TRAILER_DECISION_INVALID;
  }
  for (i = 0u; i < 3u; ++i) {
    if (!isfinite(current_position[i]) || !isfinite(target_position[i])) {
      return SAMP_REMOTE_TRAILER_DECISION_INVALID;
    }
    delta_out[i] = target_position[i] - current_position[i];
  }
  if (association_transition) {
    return SAMP_REMOTE_TRAILER_DECISION_TRANSITION;
  }
  if (fabsf(delta_out[0]) <= SAMP_REMOTE_TRAILER_POSITION_EPSILON &&
      fabsf(delta_out[1]) <= SAMP_REMOTE_TRAILER_POSITION_EPSILON &&
      fabsf(delta_out[2]) <= SAMP_REMOTE_TRAILER_POSITION_EPSILON) {
    return SAMP_REMOTE_TRAILER_DECISION_NOOP;
  }
  if (fabsf(delta_out[0]) > SAMP_REMOTE_TRAILER_POSITION_SNAP_XY ||
      fabsf(delta_out[1]) > SAMP_REMOTE_TRAILER_POSITION_SNAP_XY ||
      fabsf(delta_out[2]) > SAMP_REMOTE_TRAILER_POSITION_SNAP_Z) {
    return SAMP_REMOTE_TRAILER_DECISION_SNAP;
  }
  return SAMP_REMOTE_TRAILER_DECISION_CORRECT;
}

static inline const char *samp_remote_trailer_position_decision_name(
    samp_remote_trailer_position_decision_compat decision) {
  switch (decision) {
    case SAMP_REMOTE_TRAILER_DECISION_TRANSITION:
      return "transition";
    case SAMP_REMOTE_TRAILER_DECISION_NOOP:
      return "noop";
    case SAMP_REMOTE_TRAILER_DECISION_CORRECT:
      return "correct";
    case SAMP_REMOTE_TRAILER_DECISION_SNAP:
      return "snap";
    default:
      return "invalid";
  }
}

/*
 * STATIC_037:
 * Pure math extracted from samp.dll+0x15140. The caller owns the preceding
 * exact move-speed setter and the not-added/full-matrix branches.
 */
static inline samp_remote_vehicle_position_decision_compat
samp_remote_vehicle_position_decision_r5(
    const float current_position[3], const float target_position[3],
    const float target_speed[3], float snap_z, float delta_out[3],
    float corrected_speed_out[3], int *write_corrected_speed_out) {
  unsigned int i = 0u;
  int write_corrected_speed = 0;

  if (current_position == NULL || target_position == NULL ||
      target_speed == NULL || delta_out == NULL ||
      corrected_speed_out == NULL ||
      write_corrected_speed_out == NULL || !isfinite(snap_z) ||
      snap_z <= 0.0f) {
    return SAMP_REMOTE_VEHICLE_DECISION_INVALID;
  }
  for (i = 0u; i < 3u; ++i) {
    if (!isfinite(current_position[i]) ||
        !isfinite(target_position[i]) || !isfinite(target_speed[i])) {
      return SAMP_REMOTE_VEHICLE_DECISION_INVALID;
    }
    delta_out[i] = target_position[i] - current_position[i];
  }
  memcpy(corrected_speed_out, target_speed,
         sizeof(float) * 3u);
  *write_corrected_speed_out = 0;

  if (fabsf(delta_out[0]) <= SAMP_REMOTE_VEHICLE_POSITION_EPSILON &&
      fabsf(delta_out[1]) <= SAMP_REMOTE_VEHICLE_POSITION_EPSILON &&
      fabsf(delta_out[2]) <= SAMP_REMOTE_VEHICLE_POSITION_EPSILON) {
    return SAMP_REMOTE_VEHICLE_DECISION_NOOP;
  }
  if (fabsf(delta_out[0]) > SAMP_REMOTE_VEHICLE_POSITION_SNAP_XY ||
      fabsf(delta_out[1]) > SAMP_REMOTE_VEHICLE_POSITION_SNAP_XY ||
      fabsf(delta_out[2]) > snap_z) {
    return SAMP_REMOTE_VEHICLE_DECISION_SNAP;
  }

  for (i = 0u; i < 3u; ++i) {
    if (fabsf(delta_out[i]) > SAMP_REMOTE_VEHICLE_POSITION_EPSILON) {
      corrected_speed_out[i] +=
          delta_out[i] * SAMP_REMOTE_VEHICLE_POSITION_CORRECTION;
    }
    if (fabsf(corrected_speed_out[i]) >
        SAMP_REMOTE_VEHICLE_CORRECTED_SPEED_EPSILON) {
      write_corrected_speed = 1;
    }
  }
  *write_corrected_speed_out = write_corrected_speed;
  return SAMP_REMOTE_VEHICLE_DECISION_CORRECT;
}

#endif
