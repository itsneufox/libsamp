#ifndef SAMPDLL_GTA_QUATERNION_COMPAT_H
#define SAMPDLL_GTA_QUATERNION_COMPAT_H

#include <float.h>
#include <math.h>
#include <string.h>

static inline int samp_gta_quaternion_normalize_wxyz(
    const float input[4], float output[4]) {
  float length_sq = 0.0f;
  float inverse_length = 0.0f;
  unsigned int i = 0u;

  if (input == NULL || output == NULL) {
    return 0;
  }
  for (i = 0u; i < 4u; ++i) {
    if (!isfinite(input[i])) {
      return 0;
    }
    length_sq += input[i] * input[i];
  }
  if (!isfinite(length_sq) || length_sq <= 0.000001f) {
    return 0;
  }
  inverse_length = 1.0f / sqrtf(length_sq);
  for (i = 0u; i < 4u; ++i) {
    output[i] = input[i] * inverse_length;
  }
  return 1;
}

/*
 * STATIC_037 + GTA_REVERSED_REF:
 * R5's matrix-to-wire path at samp.dll+0xB52B0/+0xB4D70 is the inverse of
 * its wire-to-matrix path at +0xB6A80/+0xB4F10. GTA CQuaternion::Set stores
 * x,y,z,w, while SA-MP sends the conjugated quaternion as w,-x,-y,-z.
 * The original converter takes the positive square-root branch for W, so
 * canonicalize the otherwise equivalent global sign after normalization.
 */
static inline int samp_gta_matrix_quaternion_xyzw_to_wire_wxyz(
    const float gta_xyzw[4], float wire_wxyz[4]) {
  float converted[4];

  if (gta_xyzw == NULL || wire_wxyz == NULL) {
    return 0;
  }
  converted[0] = gta_xyzw[3];
  converted[1] = -gta_xyzw[0];
  converted[2] = -gta_xyzw[1];
  converted[3] = -gta_xyzw[2];
  if (!samp_gta_quaternion_normalize_wxyz(converted, wire_wxyz)) {
    return 0;
  }
  if (wire_wxyz[0] < 0.0f) {
    wire_wxyz[0] = -wire_wxyz[0];
    wire_wxyz[1] = -wire_wxyz[1];
    wire_wxyz[2] = -wire_wxyz[2];
    wire_wxyz[3] = -wire_wxyz[3];
  }
  return 1;
}

/*
 * STATIC_037:
 * R5 remote-vehicle playback calls D3DXQuaternionSlerp through
 * samp.dll+0xB5480 and normalizes through +0xB5500. Inputs and outputs here
 * use SA-MP's w,x,y,z ordering.
 */
static inline int samp_gta_quaternion_slerp_wxyz(
    const float current[4], const float target[4], float amount,
    float output[4]) {
  float normalized_current[4];
  float normalized_target[4];
  float adjusted_target[4];
  float dot = 0.0f;
  float theta = 0.0f;
  float sin_theta = 0.0f;
  float current_weight = 0.0f;
  float target_weight = 0.0f;
  unsigned int i = 0u;

  if (!isfinite(amount) || amount < 0.0f || amount > 1.0f ||
      !samp_gta_quaternion_normalize_wxyz(
          current, normalized_current) ||
      !samp_gta_quaternion_normalize_wxyz(
          target, normalized_target)) {
    return 0;
  }
  for (i = 0u; i < 4u; ++i) {
    dot += normalized_current[i] * normalized_target[i];
  }
  if (dot < 0.0f) {
    dot = -dot;
    for (i = 0u; i < 4u; ++i) {
      adjusted_target[i] = -normalized_target[i];
    }
  } else {
    memcpy(adjusted_target, normalized_target, sizeof(adjusted_target));
  }
  if (dot > 1.0f) {
    dot = 1.0f;
  }

  if (dot > 0.9995f) {
    for (i = 0u; i < 4u; ++i) {
      output[i] = normalized_current[i] +
                  amount * (adjusted_target[i] - normalized_current[i]);
    }
    return samp_gta_quaternion_normalize_wxyz(output, output);
  }

  theta = acosf(dot);
  sin_theta = sinf(theta);
  if (!isfinite(theta) || !isfinite(sin_theta) ||
      fabsf(sin_theta) <= 0.000001f) {
    return 0;
  }
  current_weight = sinf((1.0f - amount) * theta) / sin_theta;
  target_weight = sinf(amount * theta) / sin_theta;
  for (i = 0u; i < 4u; ++i) {
    output[i] = current_weight * normalized_current[i] +
                target_weight * adjusted_target[i];
  }
  return samp_gta_quaternion_normalize_wxyz(output, output);
}

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
