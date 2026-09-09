export type BrandSummary = {
  brand: string;
  amount: number;
  qty: number;
  skuCount: number;
  countryCount: number;
  categoryCount: number;
};

export type ReportBasisRow = readonly [string, string];
export type ReportMetricRow = readonly [string, string, string, string];
export type ReportSummaryRow = readonly [string, string, string[]];
