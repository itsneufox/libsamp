#include "gta_quaternion_compat.h"
#include "remote_vehicle_playback_compat.h"
#include "vehicle_attach_timing_compat.h"

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

static void expect_remote_vehicle_slerp(void) {
  const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
  const float target[4] = {
      0.70710678118f, 0.0f, 0.0f, 0.70710678118f};
  const float negative_target[4] = {
      -0.70710678118f, 0.0f, 0.0f, -0.70710678118f};
  float output[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float negative_output[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  const float expected_w =
      cosf(67.5f * (3.14159265358979323846f / 360.0f));
  const float expected_z =
      sinf(67.5f * (3.14159265358979323846f / 360.0f));

  assert(samp_gta_quaternion_slerp_wxyz(
      identity, target, 0.75f, output));
  assert(fabsf(output[0] - expected_w) < 0.00001f);
  assert(fabsf(output[1]) < 0.00001f);
  assert(fabsf(output[2]) < 0.00001f);
  assert(fabsf(output[3] - expected_z) < 0.00001f);

  /* q and -q are the same attitude; Slerp must take the short path. */
  assert(samp_gta_quaternion_slerp_wxyz(
      identity, negative_target, 0.75f, negative_output));
  assert(fabsf(negative_output[0] - output[0]) < 0.00001f);
  assert(fabsf(negative_output[3] - output[3]) < 0.00001f);
}

static void expect_matrix_to_wire_quaternion(void) {
  const float gta_xyzw[4] = {0.18257418f, -0.36514837f,
                             0.54772258f, 0.73029673f};
  const float negative_gta_xyzw[4] = {-0.18257418f, 0.36514837f,
                                      -0.54772258f, -0.73029673f};
  const float invalid_gta_xyzw[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float wire[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float negative_wire[4] = {0.0f, 0.0f, 0.0f, 0.0f};

  assert(samp_gta_matrix_quaternion_xyzw_to_wire_wxyz(
      gta_xyzw, wire));
  assert(fabsf(wire[0] - 0.73029673f) < 0.00001f);
  assert(fabsf(wire[1] - -0.18257418f) < 0.00001f);
  assert(fabsf(wire[2] - 0.36514837f) < 0.00001f);
  assert(fabsf(wire[3] - -0.54772258f) < 0.00001f);

  /* q and -q describe the same matrix; R5 canonicalizes the emitted W. */
  assert(samp_gta_matrix_quaternion_xyzw_to_wire_wxyz(
      negative_gta_xyzw, negative_wire));
  assert(fabsf(negative_wire[0] - wire[0]) < 0.00001f);
  assert(fabsf(negative_wire[1] - wire[1]) < 0.00001f);
  assert(fabsf(negative_wire[2] - wire[2]) < 0.00001f);
  assert(fabsf(negative_wire[3] - wire[3]) < 0.00001f);
  assert(!samp_gta_matrix_quaternion_xyzw_to_wire_wxyz(
      invalid_gta_xyzw, wire));
}

static void expect_remote_vehicle_position_decision(void) {
  const float current[3] = {0.0f, 0.0f, 0.0f};
  const float target_speed[3] = {0.1f, -0.2f, 0.0f};
  float target[3] = {0.05f, -0.05f, 0.05f};
  float delta[3] = {0.0f, 0.0f, 0.0f};
  float corrected[3] = {0.0f, 0.0f, 0.0f};
  int write_corrected = 0;

  assert(samp_remote_vehicle_position_decision_r5(
             current, target, target_speed,
             SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z, delta, corrected,
             &write_corrected) == SAMP_REMOTE_VEHICLE_DECISION_NOOP);

  target[0] = 1.0f;
  target[1] = -0.1f;
  target[2] = 0.25f;
  assert(samp_remote_vehicle_position_decision_r5(
             current, target, target_speed,
             SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z, delta, corrected,
             &write_corrected) == SAMP_REMOTE_VEHICLE_DECISION_CORRECT);
  assert(write_corrected);
  assert(fabsf(corrected[0] - 0.16f) < 0.00001f);
  assert(fabsf(corrected[1] - -0.206f) < 0.00001f);
  assert(fabsf(corrected[2] - 0.015f) < 0.00001f);

  target[0] = 8.0001f;
  assert(samp_remote_vehicle_position_decision_r5(
             current, target, target_speed,
             SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z, delta, corrected,
             &write_corrected) == SAMP_REMOTE_VEHICLE_DECISION_SNAP);
  target[0] = 0.0f;
  target[2] = 0.6f;
  assert(samp_remote_vehicle_position_decision_r5(
             current, target, target_speed,
             SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z, delta, corrected,
             &write_corrected) == SAMP_REMOTE_VEHICLE_DECISION_SNAP);
  assert(samp_remote_vehicle_position_decision_r5(
             current, target, target_speed,
             SAMP_REMOTE_VEHICLE_POSITION_SNAP_Z_AIR_WATER, delta,
             corrected, &write_corrected) ==
         SAMP_REMOTE_VEHICLE_DECISION_CORRECT);
}

static void expect_remote_trailer_position_decision(void) {
  const float current[3] = {10.0f, 20.0f, 30.0f};
  float target[3] = {10.25f, 19.75f, 30.1f};
  float delta[3] = {0.0f, 0.0f, 0.0f};

  assert(samp_remote_trailer_position_decision_r5(
             current, target, 0, delta) ==
         SAMP_REMOTE_TRAILER_DECISION_NOOP);
  assert(samp_remote_trailer_position_decision_r5(
             current, target, 1, delta) ==
         SAMP_REMOTE_TRAILER_DECISION_TRANSITION);

  target[0] = 10.75f;
  assert(samp_remote_trailer_position_decision_r5(
             current, target, 0, delta) ==
         SAMP_REMOTE_TRAILER_DECISION_CORRECT);
  target[0] = 16.001f;
  assert(samp_remote_trailer_position_decision_r5(
             current, target, 0, delta) ==
         SAMP_REMOTE_TRAILER_DECISION_SNAP);
  assert(samp_remote_trailer_position_decision_r5(
             current, target, 1, delta) ==
         SAMP_REMOTE_TRAILER_DECISION_TRANSITION);
}

static void expect_vehicle_attach_source_timing(void) {
  uint32_t packed_ages =
      samp_vehicle_attach_source_ages_pack(250u, 150u);

  assert(samp_vehicle_attach_source_towing_age_unpack(packed_ages) == 250u);
  assert(samp_vehicle_attach_source_trailer_age_unpack(packed_ages) == 150u);
  assert(samp_vehicle_attach_source_elapsed_ms(1000u, 1250u, 1) == 250u);
  assert(samp_vehicle_attach_source_elapsed_ms(1000u, 1250u, 0) == 0u);
  assert(samp_vehicle_attach_source_elapsed_ms(1250u, 1000u, 1) == 0u);
  assert(samp_vehicle_attach_source_elapsed_ms(
             UINT32_MAX - 99u, 150u, 1) == 250u);
  assert(samp_vehicle_attach_source_elapsed_ms(1000u, 70000u, 1) ==
         SAMP_VEHICLE_ATTACH_SOURCE_DELAY_MAX_MS);

  assert(samp_vehicle_attach_source_wait_pending(250u, 249u, 250u, 250u));
  assert(samp_vehicle_attach_source_wait_pending(250u, 250u, 250u, 249u));
  assert(!samp_vehicle_attach_source_wait_pending(250u, 250u, 250u,
                                                  250u));

  assert(samp_vehicle_attach_blocks_driver_sync(7u, 26u, 26u));
  assert(!samp_vehicle_attach_blocks_driver_sync(0u, 26u, 26u));
  assert(!samp_vehicle_attach_blocks_driver_sync(7u, 26u, 27u));
  assert(!samp_vehicle_attach_blocks_driver_sync(7u, 0u, 0u));
  assert(!samp_vehicle_attach_blocks_driver_sync(7u, UINT16_MAX,
                                                 UINT16_MAX));
}

int main(void) {
  const float scaled_identity[4] = {2.0f, 0.0f, 0.0f, 0.0f};
  const float zero[4] = {0.0f, 0.0f, 0.0f, 0.0f};
  float normalized[4] = {0.0f, 0.0f, 0.0f, 0.0f};

  expect_round_trip(0.0f);
  expect_round_trip(1.6030f);
  expect_round_trip(45.0f);
  expect_round_trip(90.0f);
  expect_round_trip(180.0f);
  expect_round_trip(270.0f);
  expect_round_trip(358.3970f);
  assert(samp_gta_yaw_degrees_from_quaternion(NAN, 0.0f, 0.0f, 0.0f) == 0.0f);
  assert(samp_gta_yaw_degrees_from_quaternion(INFINITY, 0.0f, 0.0f, 0.0f) == 0.0f);
  assert(samp_gta_quaternion_normalize_wxyz(
      scaled_identity, normalized));
  assert(fabsf(normalized[0] - 1.0f) < 0.00001f);
  assert(!samp_gta_quaternion_normalize_wxyz(zero, normalized));
  expect_matrix_to_wire_quaternion();
  expect_remote_vehicle_slerp();
  expect_remote_vehicle_position_decision();
  expect_remote_trailer_position_decision();
  expect_vehicle_attach_source_timing();
  return 0;
}
