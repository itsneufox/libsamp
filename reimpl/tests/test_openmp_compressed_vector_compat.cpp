#include "../src/net/openmp_compressed_vector_compat.h"

#include <cmath>
#include <cstdio>

namespace {

int expect(bool condition, const char *message) {
  if (condition) {
    return 0;
  }
  std::fprintf(stderr, "FAIL: %s\n", message);
  return 1;
}

bool near(float actual, float expected, float tolerance = 0.0001f) {
  return std::fabs(actual - expected) <= tolerance;
}

} // namespace

int main() {
  int failed = 0;

  {
    RakNet::BitStream stream;
    const float tiny_magnitude = 0.000005f;
    const unsigned short following_vehicle_health = 1000U;
    float x = 1.0f;
    float y = 1.0f;
    float z = 1.0f;
    unsigned short decoded_vehicle_health = 0U;

    // Mirrors open.mp-network writeCompressedVEC3 for a sub-epsilon vector.
    stream.Write(tiny_magnitude);
    stream.Write(following_vehicle_health);
    failed += expect(
        sampdll::read_openmp_compressed_vector(stream, x, y, z),
        "sub-epsilon vector decodes without consuming absent direction data");
    failed += expect(x == 0.0f && y == 0.0f && z == 0.0f,
                     "sub-epsilon vector normalizes to zero");
    failed += expect(stream.Read(decoded_vehicle_health) &&
                         decoded_vehicle_health == following_vehicle_health,
                     "field following sub-epsilon vector remains aligned");
  }

  {
    RakNet::BitStream stream;
    const float expected_x = 1.25f;
    const float expected_y = -0.5f;
    const float expected_z = 0.25f;
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    stream.WriteVector(expected_x, expected_y, expected_z);
    failed += expect(
        sampdll::read_openmp_compressed_vector(stream, x, y, z),
        "ordinary compressed vector decodes");
    failed += expect(near(x, expected_x) && near(y, expected_y) &&
                         near(z, expected_z),
                     "ordinary compressed vector preserves components");
  }

  {
    RakNet::BitStream stream;
    const float negative_magnitude = -1.0f;
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    stream.Write(negative_magnitude);
    failed += expect(
        !sampdll::read_openmp_compressed_vector(stream, x, y, z),
        "invalid negative magnitude is rejected");
  }

  if (failed == 0) {
    std::puts("open.mp compressed vector compatibility tests passed");
  }
  return failed == 0 ? 0 : 1;
}
