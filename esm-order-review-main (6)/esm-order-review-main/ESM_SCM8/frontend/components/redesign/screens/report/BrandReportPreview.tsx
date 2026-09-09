import { displayBrandName } from "@/lib/brand-display";
import { cn } from "@/lib/utils";
import type { BrandSummary, ReportBasisRow, ReportMetricRow, ReportSummaryRow } from "./reportBuilderTypes";

export function BrandReportPreview({ selectedBrand, reportBasisRows, metricRows, summaryRows }: { selectedBrand: BrandSummary; reportBasisRows: ReportBasisRow[]; metricRows: ReportMetricRow[]; summaryRows: ReportSummaryRow[] }) {
  return <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-[0_18px_45px_rgba(15,23,42,0.08)] sm:rounded-[16px]">
    <div className="bg-sidebar px-5 py-5 text-white sm:px-[32px] sm:py-[28px]"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div className="min-w-0"><p className="text-[10px] font-black tracking-[0.08em] text-row sm:text-[12px] sm:tracking-[0.12em]">BRAND PERFORMANCE REPORT · CMS DATA</p><h3 className="mt-3 break-words text-[25px] font-black leading-[1.08] sm:mt-[13px] sm:text-[30px] sm:leading-none">{displayBrandName(selectedBrand.brand)}</h3></div><p className="text-[20px] font-black sm:mt-[18px] sm:text-[25px]">Silicon2</p></div></div>
    <div className="grid grid-cols-1 gap-2 border-b border-divider bg-surface-soft px-3 py-3 sm:grid-cols-2 sm:px-[16px] sm:py-[14px] lg:grid-cols-4">{reportBasisRows.map(([label, value]) => <div key={label} className="rounded-[10px] border border-border bg-surface px-[12px] py-[10px]"><p className="text-[10px] font-black text-muted2">{label}</p><p className="mt-[5px] break-words text-[11px] font-black leading-[1.35] text-ink">{value}</p></div>)}</div>
    <div className={cn(
      "grid grid-cols-1 gap-px border-b border-divider bg-divider",
      metricRows.length >= 4
        ? "sm:grid-cols-2 lg:grid-cols-4"
        : metricRows.length === 3
          ? "sm:grid-cols-3"
          : metricRows.length === 2
            ? "sm:grid-cols-2"
            : ""
    )}>{metricRows.map(([label, value, tone, caption]) => <div key={label} className="min-h-[100px] bg-surface px-4 py-4 sm:px-[22px] sm:py-[18px]"><p className="text-[12px] font-bold text-muted2">{label}</p><p className={cn("mt-[7px] break-words text-[22px] font-black leading-none sm:text-[25px]", tone === "brand" || tone === "neg" ? "text-brand" : "text-ink")}>{value}</p><p className="mt-[7px] text-[10px] font-black leading-[1.35] text-muted2">{caption}</p></div>)}</div>
    <div className="py-2 sm:px-[16px] sm:py-[10px]">{summaryRows.map(([number, title, bodyLines]) => <div key={number} className="grid grid-cols-[32px_minmax(0,1fr)] border-b border-divider px-4 py-4 last:border-b-0 sm:grid-cols-[46px_minmax(0,1fr)] sm:px-[16px] sm:py-[16px]"><div className="text-[13px] font-black text-brand">{number}</div><div className="min-w-0"><h4 className="text-[14px] font-black leading-[1.25] text-ink">{title}</h4><div className="mt-[8px] max-w-[820px] space-y-1 break-words text-[12.5px] font-semibold leading-5 text-muted">{bodyLines.map((part, index) => {
      const isRecommendation = part.startsWith("권장 조치:");
      if (index === 0 || isRecommendation) return <p key={`${index}-${part}`} className={isRecommendation ? "pt-2 text-ink" : undefined}>{part}</p>;
      return <p key={`${index}-${part}`} className="flex gap-[7px]"><span aria-hidden="true" className="shrink-0 text-brand">•</span><span>{part}</span></p>;
    })}</div></div></div>)}</div>
    <div className="flex flex-col gap-1 border-t border-divider px-4 py-4 text-[11px] sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-[24px] sm:py-[17px] sm:text-[12px]"><p className="font-semibold text-muted2">자동 생성 · 실리콘투 SCM Analytics · CMS 분석 기준</p><p className="font-black text-ink3">브랜드 미팅 · 내부 보고 즉시 활용</p></div>
  </section>;
}
