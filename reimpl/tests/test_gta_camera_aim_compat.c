#include "gta_camera_aim_compat.h"

#include <assert.h>
#include <math.h>
#include <string.h>

static void expect_context(
    const float front[3], const float position[3],
    const float expected_up[3]) {
  float actual_front[3] = {0.0f, 0.0f, 0.0f};
  float position1[3] = {0.0f, 0.0f, 0.0f};
  float position2[3] = {0.0f, 0.0f, 0.0f};
  float actual_up[3] = {0.0f, 0.0f, 0.0f};
  float front_length_sq = 0.0f;
  float up_length_sq = 0.0f;
  float dot = 0.0f;
  unsigned int i = 0u;

  assert(samp_gta_camera_aim_build_r5(
      front, position, actual_front, position1, position2, actual_up));
  assert(memcmp(actual_front, front, sizeof(actual_front)) == 0);
  assert(memcmp(position1, position, sizeof(position1)) == 0);
  assert(memcmp(position2, position, sizeof(position2)) == 0);
  for (i = 0u; i < 3u; ++i) {
    assert(fabsf(actual_up[i] - expected_up[i]) < 0.00002f);
    front_length_sq += actual_front[i] * actual_front[i];
    up_length_sq += actual_up[i] * actual_up[i];
    dot += actual_front[i] * actual_up[i];
  }
  assert(fabsf(front_length_sq - up_length_sq) < 0.00002f);
  assert(fabsf(dot) < 0.00002f);
}

int main(void) {
  const float position[3] = {1958.3783f, 1343.1572f, 16.1514f};
  const float forward_a[3] = {0.0f, 0.998750f, -0.049979f};
  const float up_a[3] = {0.0f, 0.049979f, 0.998750f};
  const float forward_b[3] = {-0.455182f, -0.889818f, 0.032151f};
  const float up_b[3] = {0.014642f, 0.028624f, 0.999483f};
  const float zero[3] = {0.0f, 0.0f, 0.0f};
  const float vertical[3] = {0.0f, 0.0f, 1.0f};
  const float invalid_front[3] = {NAN, 0.0f, 0.0f};
  const float invalid_position[3] = {0.0f, INFINITY, 0.0f};
  float output[3] = {7.0f, 8.0f, 9.0f};

  expect_context(forward_a, position, up_a);
  expect_context(forward_b, position, up_b);

  assert(!samp_gta_camera_aim_build_r5(
      NULL, position, output, output, output, output));
  assert(!samp_gta_camera_aim_build_r5(
      zero, position, output, output, output, output));
  assert(!samp_gta_camera_aim_build_r5(
      vertical, position, output, output, output, output));
  assert(!samp_gta_camera_aim_build_r5(
      invalid_front, position, output, output, output, output));
  assert(!samp_gta_camera_aim_build_r5(
      forward_a, invalid_position, output, output, output, output));
  return 0;
}
