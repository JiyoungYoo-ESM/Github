import { amountOf, category1Of, category2Of, countryOf, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { getCountryRegion, needsRegionReview } from "@/lib/region-groups";

export type DiagnosticDraftCorrection = {
  category1: string;
  category2: string;
};

export const DIAGNOSTIC_UNMAPPED = "미분류";

export function diagnosticText(value: unknown) {
  return String(value ?? "").trim();
}

export function diagnosticUsableCategory(value: unknown) {
  const text = diagnosticText(value);
  return text && text !== DIAGNOSTIC_UNMAPPED ? text : "";
}

export function diagnosticCorrectionKey(row: Record<string, unknown>) {
  return skuCodeOf(row);
}

export function diagnosticReason(row: Record<string, unknown>) {
  return diagnosticText(row["진단사유"]) || "카테고리 분류 누락";
}

export function diagnosticEditable(row: Record<string, unknown>) {
  if (!Object.prototype.hasOwnProperty.call(row, "수정가능")) return true;
  const value = row["수정가능"];
  return value === true || ["true", "1", "y", "yes"].includes(diagnosticText(value).toLowerCase());
}

export function buildDiagnosticCorrectionRows(rows: Array<Record<string, unknown>>) {
  const bySku = new Map<string, Record<string, unknown>>();
  rows.forEach((row) => {
    const code = diagnosticCorrectionKey(row);
    if (!code || code === "-") return;
    const existing = bySku.get(code);
    if (!existing || qtyOf(row) > qtyOf(existing)) {
      bySku.set(code, row);
    }
  });
  return Array.from(bySku.values()).sort((a, b) => qtyOf(b) - qtyOf(a));
}

export function buildDiagnosticRegionRows(rows: Array<Record<string, unknown>>) {
  const countries = new Map<string, { qty: number; amount: number }>();
  rows.forEach((row) => {
    const country = countryOf(row);
    const current = countries.get(country) ?? { qty: 0, amount: 0 };
    current.qty += qtyOf(row);
    current.amount += amountOf(row);
    countries.set(country, current);
  });

  return Array.from(countries.entries())
    .map(([country, totals]) => {
      const regionInfo = getCountryRegion(country);
      return { country, ...totals, regionInfo };
    })
    .filter((item) => needsRegionReview(item.regionInfo))
    .sort((a, b) => b.qty - a.qty);
}

export function diagnosticCorrectionDraft(row: Record<string, unknown>, draft?: DiagnosticDraftCorrection): DiagnosticDraftCorrection {
  return {
    category1: draft?.category1 ?? diagnosticUsableCategory(category1Of(row)),
    category2: draft?.category2 ?? diagnosticUsableCategory(category2Of(row))
  };
}
