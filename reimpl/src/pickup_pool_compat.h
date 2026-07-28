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

static inline int samp_pickup_pool_id_valid(int32_t pickup_id) {
  return pickup_id >= 0 &&
         (uint32_t)pickup_id < SAMP_PICKUP_POOL_CAPACITY_037;
}

#endif
