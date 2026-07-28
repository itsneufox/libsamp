#include "../src/pickup_pool_compat.h"

#include <assert.h>
#include <stdint.h>

_Static_assert(SAMP_PICKUP_POOL_CAPACITY_037 == 4096u,
               "R5 pickup pool capacity must remain 4096 slots");

int main(void) {
  assert(!samp_pickup_pool_id_valid(-1));
  assert(samp_pickup_pool_id_valid(0));
  assert(samp_pickup_pool_id_valid(4095));
  assert(!samp_pickup_pool_id_valid(4096));
  assert(!samp_pickup_pool_id_valid(INT32_MAX));
  return 0;
}
