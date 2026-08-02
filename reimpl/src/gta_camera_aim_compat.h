#ifndef SAMPDLL_GTA_CAMERA_AIM_COMPAT_H
#define SAMPDLL_GTA_CAMERA_AIM_COMPAT_H

#include <math.h>
#include <stddef.h>
#include <string.h>

/*
 * OBSERVED_037 + PROBE_TRACE:
 * Original R5 stores each 0x30-byte camera-aim context as
 * [front, position, position, up]. Across the non-degenerate contexts from
 * artifacts/runs/20260728-aim-r5-memory-observer, the up vector is:
 *
 *   h = sqrt(front.x^2 + front.y^2)
 *   up = (-front.x * front.z / h,
 *         -front.y * front.z / h,
 *          h)
 *
 * This is also the exact context copied by samp.dll+0x9C9C0 and restored by
 * +0x9C960 (R5 SHA256
 * b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2).
 *
 * TODO_VERIFY:
 * No exactly vertical front vector was captured. Reject that boundary rather
 * than inventing a basis which could differ from R5.
 */
static inline int samp_gta_camera_aim_build_r5(
    const float front[3], const float position[3], float out_front[3],
    float out_position1[3], float out_position2[3], float out_up[3]) {
  float built[12];
  float length_sq = 0.0f;
  float horizontal = 0.0f;
  unsigned int i = 0u;

  if (front == NULL || position == NULL || out_front == NULL ||
      out_position1 == NULL || out_position2 == NULL || out_up == NULL) {
    return 0;
  }

  for (i = 0u; i < 3u; ++i) {
    if (!isfinite(front[i]) || !isfinite(position[i]) ||
        fabsf(front[i]) > 2.0f || fabsf(position[i]) > 50000.0f) {
      return 0;
    }
    length_sq += front[i] * front[i];
  }
  if (!isfinite(length_sq) || length_sq < 0.01f || length_sq > 4.0f) {
    return 0;
  }

  horizontal = sqrtf(
      (front[0] * front[0]) + (front[1] * front[1]));
  if (!isfinite(horizontal) || horizontal <= 0.000001f) {
    return 0;
  }

  memcpy(&built[0], front, sizeof(float) * 3u);
  memcpy(&built[3], position, sizeof(float) * 3u);
  memcpy(&built[6], position, sizeof(float) * 3u);
  built[9] = -(front[0] * front[2]) / horizontal;
  built[10] = -(front[1] * front[2]) / horizontal;
  built[11] = horizontal;
  if (!isfinite(built[9]) || !isfinite(built[10]) ||
      !isfinite(built[11])) {
    return 0;
  }

  memcpy(out_front, &built[0], sizeof(float) * 3u);
  memcpy(out_position1, &built[3], sizeof(float) * 3u);
  memcpy(out_position2, &built[6], sizeof(float) * 3u);
  memcpy(out_up, &built[9], sizeof(float) * 3u);
  return 1;
}

#endif
