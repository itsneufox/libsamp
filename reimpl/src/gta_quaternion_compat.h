#ifndef SAMPDLL_GTA_QUATERNION_COMPAT_H
#define SAMPDLL_GTA_QUATERNION_COMPAT_H

#include <float.h>
#include <math.h>

/*
 * OBSERVED_037 + PROBE_TRACE + OPENMP_REF:
 * GTA/SA-MP facing angles run opposite to the conventional mathematical yaw.
 * Original R5 emitted q=(0.99990,0,0,0.01398) while reporting facing
 * 358.397 degrees. A conventional positive atan2 decodes that quaternion as
 * about 1.603 degrees, which mirrored remote left/right turns.
 *
 * This is kept internal because it is a wire-to-GTA convention, not a public
 * replacement API.
 */
static inline float samp_gta_yaw_degrees_from_quaternion(float w, float x, float y, float z) {
  float siny_cosp;
  float cosy_cosp;
  float yaw;

  if (!(w == w) || !(x == x) || !(y == y) || !(z == z) ||
      w > FLT_MAX || w < -FLT_MAX || x > FLT_MAX || x < -FLT_MAX ||
      y > FLT_MAX || y < -FLT_MAX || z > FLT_MAX || z < -FLT_MAX) {
    return 0.0f;
  }

  siny_cosp = 2.0f * ((w * z) + (x * y));
  cosy_cosp = 1.0f - (2.0f * ((y * y) + (z * z)));
  yaw = -atan2f(siny_cosp, cosy_cosp) * (180.0f / 3.14159265358979323846f);
  if (!(yaw == yaw) || yaw > FLT_MAX || yaw < -FLT_MAX) {
    return 0.0f;
  }
  if (yaw < 0.0f) {
    yaw += 360.0f;
  } else if (yaw >= 360.0f) {
    yaw -= 360.0f;
  }
  return yaw == 0.0f ? 0.0f : yaw;
}

#endif
