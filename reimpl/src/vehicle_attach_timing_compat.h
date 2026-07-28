#ifndef SAMPDLL_VEHICLE_ATTACH_TIMING_COMPAT_H
#define SAMPDLL_VEHICLE_ATTACH_TIMING_COMPAT_H

#include <stdint.h>

/*
 * PROBE_TRACE + INFERRED:
 * Deferred GTA vehicle construction must not collapse the observed interval
 * between RPC 164 and RPC 148 to a zero-age SetTowLink call. Keep the carried
 * interval below the shared movement cursor's 2000-ms retry bound.
 */
#define SAMP_VEHICLE_ATTACH_SOURCE_DELAY_MAX_MS 1000u

/*
 * Internal vehicle events are action-tagged. ATTACH_TRAILER does not use the
 * component field, so carry both 16-bit receive ages there without changing
 * the public event struct or its source/binary ABI.
 */
static inline uint32_t samp_vehicle_attach_source_ages_pack(
    uint16_t towing_age_ms, uint16_t trailer_age_ms) {
  return (uint32_t)towing_age_ms | ((uint32_t)trailer_age_ms << 16u);
}

static inline uint16_t samp_vehicle_attach_source_towing_age_unpack(
    uint32_t packed_ages) {
  return (uint16_t)(packed_ages & 0xFFFFu);
}

static inline uint16_t samp_vehicle_attach_source_trailer_age_unpack(
    uint32_t packed_ages) {
  return (uint16_t)(packed_ages >> 16u);
}

static inline uint16_t samp_vehicle_attach_source_elapsed_ms(
    uint32_t create_tick, uint32_t attach_tick, int create_tick_valid) {
  int32_t elapsed = 0;

  if (!create_tick_valid) {
    return 0u;
  }
  elapsed = (int32_t)(attach_tick - create_tick);
  if (elapsed <= 0) {
    return 0u;
  }
  if ((uint32_t)elapsed > SAMP_VEHICLE_ATTACH_SOURCE_DELAY_MAX_MS) {
    return (uint16_t)SAMP_VEHICLE_ATTACH_SOURCE_DELAY_MAX_MS;
  }
  return (uint16_t)elapsed;
}

static inline int samp_vehicle_attach_source_wait_pending(
    uint16_t towing_required_age_ms, uint32_t towing_active_age_ms,
    uint16_t trailer_required_age_ms, uint32_t trailer_active_age_ms) {
  return towing_active_age_ms < (uint32_t)towing_required_age_ms ||
         trailer_active_age_ms < (uint32_t)trailer_required_age_ms;
}

/*
 * OBSERVED_037 + PROBE_TRACE:
 * RPC 148 is dispatched before the first Packet-200 driver update in the
 * trailer scenario. The replacement may still be replaying that older RPC
 * after paced vehicle construction, so keep the driver packet behind the
 * pending association instead of seating the remote ped first.
 */
static inline int samp_vehicle_attach_blocks_driver_sync(
    uint32_t pending_attach_seq, uint16_t pending_trailer_id,
    uint16_t sync_trailer_id) {
  return pending_attach_seq != 0u && pending_trailer_id != 0u &&
         pending_trailer_id != UINT16_MAX &&
         pending_trailer_id == sync_trailer_id;
}

#endif
