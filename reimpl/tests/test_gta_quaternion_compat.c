#include "gta_quaternion_compat.h"

#include <assert.h>
#include <math.h>

static float angle_distance(float first, float second) {
  float difference = fabsf(first - second);
  return difference > 180.0f ? 360.0f - difference : difference;
}

static void expect_round_trip(float gta_angle) {
  const float radians = gta_angle * (3.14159265358979323846f / 180.0f);
  const float w = cosf(radians * -0.5f);
  const float z = sinf(radians * -0.5f);
  const float decoded = samp_gta_yaw_degrees_from_quaternion(w, 0.0f, 0.0f, z);

  assert(angle_distance(decoded, gta_angle) < 0.001f);
}

int main(void) {
  expect_round_trip(0.0f);
  expect_round_trip(1.6030f);
  expect_round_trip(45.0f);
  expect_round_trip(90.0f);
  expect_round_trip(180.0f);
  expect_round_trip(270.0f);
  expect_round_trip(358.3970f);
  assert(samp_gta_yaw_degrees_from_quaternion(NAN, 0.0f, 0.0f, 0.0f) == 0.0f);
  assert(samp_gta_yaw_degrees_from_quaternion(INFINITY, 0.0f, 0.0f, 0.0f) == 0.0f);
  return 0;
}
