import { V3_PERIOD_DAYS } from "../../../../lib/format-calendar-duration.ts";

/**
 * Display horizon for the "향후 예상 수요" metric.  The server keeps demand at the
 * 1기(7일) grain (`demand_per_period`) because every target-stock layer consumes it
 * that way; the horizon figure below is a display-only scale-up and must not be fed
 * back into any calculation.
 */
export const DEMAND_HORIZON_PERIODS = 4;
export const DEMAND_HORIZON_DAYS = DEMAND_HORIZON_PERIODS * V3_PERIOD_DAYS;
export const DEMAND_HORIZON_LABEL = `향후 ${DEMAND_HORIZON_PERIODS}주(${DEMAND_HORIZON_DAYS}일) 예상 수요`;

export function demandOverHorizon(demandPerPeriod: number) {
  return demandPerPeriod * DEMAND_HORIZON_PERIODS;
}
