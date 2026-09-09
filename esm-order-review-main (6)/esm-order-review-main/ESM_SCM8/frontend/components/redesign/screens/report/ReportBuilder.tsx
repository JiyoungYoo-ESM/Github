"use client";

import { FileText } from "lucide-react";
import { displayBrandName } from "@/lib/brand-display";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandReportPreview } from "./BrandReportPreview";
import { useReportBuilderModel } from "./useReportBuilderModel";

export function ReportBuilder() {
  const model = useReportBuilderModel();
  const { loading, loadFailed, reportDataIssue, brandSummaries, selectedBrand, setSelectedBrandName, analysisOptions, reportBasisRows, metricRows, summaryRows, exportingPdf, pdfExportError, exportReportPdf } = model;

  return <div className="mx-auto max-w-[980px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
    <header className="mb-[22px] flex flex-col gap-4 max-sm:[&>div:last-of-type]:w-full max-sm:[&>div:last-of-type>div]:flex-1 max-sm:[&>div:last-of-type>div>button]:w-full max-sm:[&>div:last-of-type>div>button]:max-w-none max-sm:[&>div:last-of-type>button]:flex-1 sm:flex-row sm:items-start sm:justify-between">
      <div><h2 className="text-[18px] font-black leading-none text-ink">브랜드 자동 리포트</h2><div className="mt-[12px]"><AnalysisPeriodBadge options={analysisOptions} /><AnalysisPeriodCaveat options={analysisOptions} /></div></div>
      <div className="flex shrink-0 items-center gap-[10px]"><BrandSearchSelect value={selectedBrand?.brand ?? ""} options={brandSummaries.map((brand) => brand.brand)} getOptionLabel={displayBrandName} responsiveFullWidth disabled={loading || Boolean(reportDataIssue) || brandSummaries.length === 0} onChange={setSelectedBrandName} /><button type="button" onClick={exportReportPdf} disabled={exportingPdf || !selectedBrand || Boolean(reportDataIssue)} className="inline-flex h-[38px] items-center gap-[8px] rounded-[10px] bg-brand px-[17px] text-[13px] font-black text-white shadow-soft transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-60"><FileText className="h-4 w-4" />{exportingPdf ? "PDF 생성 중" : "PDF 내보내기"}</button></div>
    </header>
    {pdfExportError ? <p role="alert" className="mb-4 rounded-[10px] border border-brand/25 bg-brand/5 px-3 py-2 text-[12px] font-bold leading-5 text-brand">{pdfExportError}</p> : null}
    {loading ? <div className="rounded-[16px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">브랜드 리포트 데이터를 불러오는 중입니다.</div> : null}
    {!loading && (loadFailed || reportDataIssue || brandSummaries.length === 0) ? <div className="rounded-[16px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">{loadFailed ? "브랜드 리포트 데이터를 불러오지 못했습니다." : reportDataIssue ?? "브랜드 리포트에 사용할 분석 데이터가 없습니다."}</div> : null}
    {!loading && !loadFailed && !reportDataIssue && selectedBrand ? <BrandReportPreview selectedBrand={selectedBrand} reportBasisRows={reportBasisRows} metricRows={metricRows} summaryRows={summaryRows} /> : null}
  </div>;
}
