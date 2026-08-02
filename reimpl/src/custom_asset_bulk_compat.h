#ifndef SAMPDLL_CUSTOM_ASSET_BULK_COMPAT_H
#define SAMPDLL_CUSTOM_ASSET_BULK_COMPAT_H

#include <stddef.h>
#include <stdint.h>

#define SAMP_ASSET_IDE_SECTION_UNKNOWN 0u
#define SAMP_ASSET_IDE_SECTION_OBJS 1u
#define SAMP_ASSET_IDE_SECTION_TOBJ 2u
#define SAMP_ASSET_IDE_SECTION_ANIM 3u

typedef struct samp_asset_prearchive_bulk_plan_compat {
  uint32_t model_info_count;
  uint32_t deferred_anim_count;
} samp_asset_prearchive_bulk_plan_compat;

static inline int samp_asset_ide_section_is_prearchive_model_info_compat(
    uint8_t section) {
  /* OBSERVED_037 + PROBE_TRACE:
   * R5's pre-archive stock pass covers the `objs` Atomic rows, while the two
   * stock `anim` rows are outside that 1,433-entry pass.
   * GTA_REVERSED_REF + INFERRED + TODO_VERIFY: parsed `tobj` rows use the
   * corresponding AddTimeModel phase; animated clump/IFP conversion remains
   * separate in the replacement.
   */
  return section == SAMP_ASSET_IDE_SECTION_OBJS ||
         section == SAMP_ASSET_IDE_SECTION_TOBJ;
}

static inline void samp_asset_prearchive_bulk_plan_reset_compat(
    samp_asset_prearchive_bulk_plan_compat *plan) {
  if (plan == NULL) {
    return;
  }
  plan->model_info_count = 0u;
  plan->deferred_anim_count = 0u;
}

static inline void samp_asset_prearchive_bulk_plan_add_section_compat(
    samp_asset_prearchive_bulk_plan_compat *plan, uint8_t section) {
  if (plan == NULL) {
    return;
  }

  if (samp_asset_ide_section_is_prearchive_model_info_compat(section)) {
    ++plan->model_info_count;
  } else if (section == SAMP_ASSET_IDE_SECTION_ANIM) {
    ++plan->deferred_anim_count;
  }
}

static inline int samp_asset_prearchive_full_bulk_ready_compat(
    int bulk_enabled, int model_info_path_ready, uint32_t bulk_limit,
    const samp_asset_prearchive_bulk_plan_compat *plan) {
  return bulk_enabled && model_info_path_ready && plan != NULL &&
         plan->model_info_count > 0u && bulk_limit >= plan->model_info_count;
}

#endif
