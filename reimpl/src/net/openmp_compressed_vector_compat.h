#ifndef SAMPDLL_OPENMP_COMPRESSED_VECTOR_COMPAT_H
#define SAMPDLL_OPENMP_COMPRESSED_VECTOR_COMPAT_H

#include <cmath>

#include "raknet/BitStream.h"

namespace sampdll {

constexpr float kOpenMpCompressedVectorMagnitudeEpsilon = 0.00001f;

inline bool read_openmp_compressed_vector(RakNet::BitStream &stream, float &x,
                                          float &y, float &z) {
  float magnitude = 0.0f;

  if (!stream.Read(magnitude) || !std::isfinite(magnitude) ||
      magnitude < 0.0f) {
    return false;
  }

  /*
   * OPENMP_REF + PROBE_TRACE:
   * open.mp-network dc3eac9d5dc30f96edcf4e7e64f33d8c241d49ff
   * writeCompressedVEC3 writes direction components only when magnitude is
   * greater than 1e-5. RakNet::BitStream::ReadVector instead tests != 0,
   * which consumes the following VehicleSync fields for tiny non-zero
   * magnitudes. Windows run
   * 20260726_164407_remote-vehicle-r5-context_9b4ddc0a observed this as
   * eleven valid 38-byte packet-200 frames rejected at rest.
   */
  if (magnitude > kOpenMpCompressedVectorMagnitudeEpsilon) {
    float compressed_x = 0.0f;
    float compressed_y = 0.0f;
    float compressed_z = 0.0f;
    if (!stream.ReadCompressed(compressed_x) ||
        !stream.ReadCompressed(compressed_y) ||
        !stream.ReadCompressed(compressed_z) ||
        !std::isfinite(compressed_x) || !std::isfinite(compressed_y) ||
        !std::isfinite(compressed_z)) {
      return false;
    }
    x = compressed_x * magnitude;
    y = compressed_y * magnitude;
    z = compressed_z * magnitude;
  } else {
    x = 0.0f;
    y = 0.0f;
    z = 0.0f;
  }
  return true;
}

} // namespace sampdll

#endif
