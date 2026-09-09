import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { stockGapItemFromOrderReview } from "../../frontend/lib/api/mappers.ts";
import {
  calculateStockGapShortageQty,
  computeStockGapItem,
  formatDate,
} from "../../frontend/lib/stock-gap.ts";

const root = path.resolve(import.meta.dirname, "../..");
const sourcePath = path.resolve(
  process.argv[2] ??
    path.join(
      root,
      "backend/storage/latest_order_review/849fa1db-cffa-43bd-aaf6-832f21f35036.json",
    ),
);

const payload = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
const rows = Array.isArray(payload.rows) ? payload.rows : [];
let timelineWarningCount = 0;
const timelineWarningCategories = {
  out_of_order: 0,
  stockout_before_base: 0,
  eta_before_base: 0,
  backend_stockout_mismatch: 0,
};
const etaBeforeBaseSkus = new Set();
console.warn = (...args) => {
  if (String(args[0] ?? "").includes("[stock-gap] timeline consistency check")) {
    timelineWarningCount += 1;
    const details = args[1] ?? {};
    timelineWarningCategories.out_of_order += Number(Boolean(details.outOfOrder));
    timelineWarningCategories.stockout_before_base += Number(Boolean(details.stockoutBeforeBase));
    timelineWarningCategories.eta_before_base += Number(Boolean(details.etaBeforeBase));
    timelineWarningCategories.backend_stockout_mismatch += Number(Boolean(details.backendMismatch));
    if (details.etaBeforeBase && details.sku) {
      etaBeforeBaseSkus.add(String(details.sku));
    }
  }
};

const computed = rows.map((row) =>
  computeStockGapItem(stockGapItemFromOrderReview(row, []), new Date("2026-07-14T00:00:00+09:00")),
);

const statusCounts = Object.fromEntries(
  [...computed.reduce((counts, row) => {
    counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
    return counts;
  }, new Map()).entries()].sort(([left], [right]) => left.localeCompare(right)),
);
const riskRows = computed.filter(
  (row) => row.status === "stock_gap" || row.status === "urgent_replenishment",
);
const canonicalShortages = computed.map((row) => calculateStockGapShortageQty(row));
const directShortages = computed.map((row) => {
  const gapDays = Number(row.gapDays ?? 0);
  const dailySalesQty = Number(row.dailySalesQty ?? 0);
  return gapDays > 0 && dailySalesQty > 0 ? Math.ceil(gapDays * dailySalesQty) : 0;
});

const dateValues = computed.flatMap((row) => [row.stockoutDate, row.earliestEtaDate]).filter(Boolean);
const fullDateFailures = dateValues.filter((value) => !/^\d{4}-\d{2}-\d{2}$/.test(formatDate(value))).length;
const etaBeforeBaseRows = computed.filter((row) => etaBeforeBaseSkus.has(String(row.sku)));
const etaBeforeBaseStatusCounts = Object.fromEntries(
  [...etaBeforeBaseRows.reduce((counts, row) => {
    counts.set(row.status, (counts.get(row.status) ?? 0) + 1);
    return counts;
  }, new Map()).entries()].sort(([left], [right]) => left.localeCompare(right)),
);

const historicalInput = {
  sku: "HIST-001",
  productName: "Historical boundary",
  brand: "TEST",
  availableQty: 1000,
  recent3mSalesQty: 900,
  avgDailySalesQty: null,
  stockoutDate: null,
  earliestEtaDate: null,
  etaItems: [],
  riskScore: 0,
  backendStatus: "",
  priorityAction: "",
  riskReason: "",
  preArrivalStockoutRisk: false,
  etaDelayFlag: false,
  urgentReplenishmentQty: 0,
  urgentAction: "",
  shortageQty: 0,
  baseDate: "2026-01-01",
};
const historicalA = computeStockGapItem(historicalInput, new Date("2026-01-01T00:00:00Z"));
const historicalB = computeStockGapItem(historicalInput, new Date("2031-12-31T00:00:00Z"));
const dashboardSource = fs.readFileSync(path.join(root, "frontend/lib/api/dashboard.ts"), "utf8");
const workspaceSource = fs.readFileSync(
  path.join(root, "frontend/components/redesign/SiliconAnalyticsWorkspace.tsx"),
  "utf8",
);

const result = {
  source: {
    file: path.relative(root, sourcePath).replaceAll("\\", "/"),
    saved_at: payload.saved_at ?? null,
    job_id: payload.job_id ?? null,
    declared_row_count: payload.row_count ?? null,
  },
  population: {
    input_rows: rows.length,
    computed_rows: computed.length,
    unique_skus: new Set(computed.map((row) => row.sku)).size,
  },
  stock_gap: {
    status_counts: statusCounts,
    risk_rows: riskRows.length,
    long_gap_rows: riskRows.filter((row) => Number(row.gapDays ?? 0) >= 7).length,
    total_canonical_shortage_qty: riskRows.reduce(
      (sum, row) => sum + calculateStockGapShortageQty(row),
      0,
    ),
    canonical_shortage_mismatches: canonicalShortages.filter(
      (value, index) => value !== directShortages[index],
    ).length,
    date_values_checked: dateValues.length,
    full_year_date_failures: fullDateFailures,
    timeline_warning_rows: timelineWarningCount,
    timeline_warning_categories: timelineWarningCategories,
    eta_before_base_detail: {
      rows: etaBeforeBaseRows.length,
      status_counts: etaBeforeBaseStatusCounts,
      eta_delay_flag_rows: etaBeforeBaseRows.filter((row) => row.etaDelayFlag).length,
      pre_arrival_stockout_risk_rows: etaBeforeBaseRows.filter((row) => row.preArrivalStockoutRisk).length,
      risk_status_rows: etaBeforeBaseRows.filter(
        (row) => row.status === "stock_gap" || row.status === "urgent_replenishment",
      ).length,
    },
  },
  boundary_checks: {
    historical_base_date_status: historicalA.status,
    historical_base_date_expected: "sufficient",
    historical_fallback_independent: historicalA.status === historicalB.status,
    canonical_shortage_observed: calculateStockGapShortageQty({
      gapDays: 5,
      dailySalesQty: 10,
      urgentReplenishmentQty: 999,
      shortageQty: 777,
    }),
    canonical_shortage_expected: 50,
    current_session_guard_present:
      /options\.requireCurrentSession/.test(dashboardSource) &&
      /currentResult\.job_id\s*!==\s*getCurrentAnalysisJobId\(\)/.test(dashboardSource) &&
      /result\.job_id\s*!==\s*getCurrentAnalysisJobId\(\)/.test(dashboardSource),
    excel_error_style_stop_present: /errorStyle:\s*"stop"/.test(workspaceSource),
    excel_invalid_error_style_absent: !/errorStyle:\s*"error"/.test(workspaceSource),
    full_date_export_present:
      /formatStockGapDate\(row\.stockoutDate\)/.test(workspaceSource) &&
      /formatStockGapDate\(row\.earliestEtaDate\)/.test(workspaceSource),
  },
};

process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
