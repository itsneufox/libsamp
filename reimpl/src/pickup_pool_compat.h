#ifndef SAMPDLL_PICKUP_POOL_COMPAT_H
#define SAMPDLL_PICKUP_POOL_COMPAT_H

#include <stdint.h>

/*
 * STATIC_037:
 * SA-MP 0.3.7-R5 CPickupPool owns 4096 indexed slots. The corresponding
 * methods are New at samp.dll+0x13270, Destroy at +0x13320, PickedUp at
 * +0x13440 and Process at +0x13520.
 * Binary SHA256:
 * b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
 */
#define SAMP_PICKUP_POOL_CAPACITY_037 4096u

typedef enum samp_pickup_rpc_source_compat {
  SAMP_PICKUP_RPC_SOURCE_INVALID = 0,
  SAMP_PICKUP_RPC_SOURCE_ORDINARY_PICKED_UP,
  SAMP_PICKUP_RPC_SOURCE_PROCESS
} samp_pickup_rpc_source_compat;

static inline int samp_pickup_pool_id_valid(int32_t pickup_id) {
  return pickup_id >= 0 &&
         (uint32_t)pickup_id < SAMP_PICKUP_POOL_CAPACITY_037;
}

/*
 * STATIC_037:
 * R5 CPickupPool::PickedUp at samp.dll+0x13440 sends RPC 131 with numeric
 * reliability 9 (RELIABLE_ORDERED).  The type-14 and dropped branches in
 * CPickupPool::Process at +0x13520 use numeric reliability 10
 * (RELIABLE_SEQUENCED).
 * OBSERVED_037 + PROBE_TRACE:
 * Run 20260802-112802-distributed-sync-pickup-57189 corroborates the ordinary
 * value on the original R5 DLL. The Process sources remain TODO_VERIFY.
 */
static inline unsigned int samp_pickup_rpc_reliability_r5(
    samp_pickup_rpc_source_compat source) {
  if (source == SAMP_PICKUP_RPC_SOURCE_ORDINARY_PICKED_UP) {
    return 9u;
  }
  if (source == SAMP_PICKUP_RPC_SOURCE_PROCESS) {
    return 10u;
  }
  return 0u;
}

#endif
