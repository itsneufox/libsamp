#include "../src/custom_asset_bulk_compat.h"

#include <assert.h>
#include <stdint.h>

static void add_sections(samp_asset_prearchive_bulk_plan_compat *plan,
                         uint8_t section, uint32_t count) {
  uint32_t i = 0u;

  for (i = 0u; i < count; ++i) {
    samp_asset_prearchive_bulk_plan_add_section_compat(plan, section);
  }
}

int main(void) {
  samp_asset_prearchive_bulk_plan_compat stock_plan;
  samp_asset_prearchive_bulk_plan_compat mixed_plan;
  samp_asset_prearchive_bulk_plan_compat anim_only_plan;

  samp_asset_prearchive_bulk_plan_reset_compat(&stock_plan);
  add_sections(&stock_plan, SAMP_ASSET_IDE_SECTION_OBJS, 1433u);
  add_sections(&stock_plan, SAMP_ASSET_IDE_SECTION_ANIM, 2u);

  assert(stock_plan.model_info_count == 1433u);
  assert(stock_plan.deferred_anim_count == 2u);
  assert(samp_asset_prearchive_full_bulk_ready_compat(1, 1, 1433u,
                                                       &stock_plan));
  assert(!samp_asset_prearchive_full_bulk_ready_compat(1, 1, 1432u,
                                                        &stock_plan));
  assert(!samp_asset_prearchive_full_bulk_ready_compat(0, 1, 1433u,
                                                        &stock_plan));
  assert(!samp_asset_prearchive_full_bulk_ready_compat(1, 0, 1433u,
                                                        &stock_plan));

  assert(samp_asset_ide_section_is_prearchive_model_info_compat(
      SAMP_ASSET_IDE_SECTION_OBJS));
  assert(samp_asset_ide_section_is_prearchive_model_info_compat(
      SAMP_ASSET_IDE_SECTION_TOBJ));
  assert(!samp_asset_ide_section_is_prearchive_model_info_compat(
      SAMP_ASSET_IDE_SECTION_ANIM));
  assert(!samp_asset_ide_section_is_prearchive_model_info_compat(
      SAMP_ASSET_IDE_SECTION_UNKNOWN));

  samp_asset_prearchive_bulk_plan_reset_compat(&mixed_plan);
  samp_asset_prearchive_bulk_plan_add_section_compat(
      &mixed_plan, SAMP_ASSET_IDE_SECTION_OBJS);
  samp_asset_prearchive_bulk_plan_add_section_compat(
      &mixed_plan, SAMP_ASSET_IDE_SECTION_ANIM);
  samp_asset_prearchive_bulk_plan_add_section_compat(
      &mixed_plan, SAMP_ASSET_IDE_SECTION_UNKNOWN);
  samp_asset_prearchive_bulk_plan_add_section_compat(
      &mixed_plan, SAMP_ASSET_IDE_SECTION_TOBJ);
  assert(mixed_plan.model_info_count == 2u);
  assert(mixed_plan.deferred_anim_count == 1u);
  assert(samp_asset_prearchive_full_bulk_ready_compat(1, 1, 2u,
                                                       &mixed_plan));

  samp_asset_prearchive_bulk_plan_reset_compat(&anim_only_plan);
  add_sections(&anim_only_plan, SAMP_ASSET_IDE_SECTION_ANIM, 2u);
  assert(anim_only_plan.model_info_count == 0u);
  assert(anim_only_plan.deferred_anim_count == 2u);
  assert(!samp_asset_prearchive_full_bulk_ready_compat(1, 1, 1433u,
                                                        &anim_only_plan));
  assert(!samp_asset_prearchive_full_bulk_ready_compat(1, 1, 1433u, NULL));

  return 0;
}
