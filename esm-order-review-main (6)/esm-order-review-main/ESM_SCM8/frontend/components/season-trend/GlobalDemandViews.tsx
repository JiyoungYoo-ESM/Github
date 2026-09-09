"use client";

/**
 * Compatibility facade for global-demand lenses.
 *
 * Stateful page composition lives in GlobalDemandTab. This module preserves
 * the established import path while each lens owns its rendering separately.
 */
export {
  ALL,
  CALENDAR_EXCLUDED_CATEGORY1,
  CONTINENTS,
  DONUT_COLORS,
  brandCountOf,
  buildChartPoints,
  buildIngredientYoyMap,
  continentOfRegion,
  coverageFromRecord,
  emptyYoyMetric,
  encodeDetail,
  ingredientHelper,
  isUncategorizedIngredient,
  monthOfRow,
  parseDetail,
  skuCountOf,
  skuStockStatus,
  stockStatusOf,
  useQueryState
} from "./GlobalDemandViewModel";

export type {
  BrandLensRow,
  BrandSort,
  CoverageStats,
  DetailPayload,
  DonutRow,
  IngredientLensRow,
  IngredientSort,
  Lens,
  SkuLensRow,
  YoyMetric
} from "./GlobalDemandViewModel";

export { LensSegment, ScopeChip } from "./GlobalDemandShared";
export { MonthlyLensView } from "./GlobalDemandMonthlyView";
export { IngredientLensView } from "./GlobalDemandIngredientView";
export { BrandLensView } from "./GlobalDemandBrandView";
export { SkuLensView } from "./GlobalDemandSkuView";
