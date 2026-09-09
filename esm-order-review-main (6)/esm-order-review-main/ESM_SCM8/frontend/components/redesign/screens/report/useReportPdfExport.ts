"use client";

import { useCallback, useState } from "react";
import { displayBrandName } from "@/lib/brand-display";
import { buildBrandReportPdfHtml } from "./reportPdfDocument";
import type { BrandSummary, ReportBasisRow, ReportMetricRow, ReportSummaryRow } from "./reportBuilderTypes";

export function useReportPdfExport({
  selectedBrand,
  reportBasisRows,
  metricRows,
  summaryRows
}: {
  selectedBrand: BrandSummary | undefined;
  reportBasisRows: ReportBasisRow[];
  metricRows: ReportMetricRow[];
  summaryRows: ReportSummaryRow[];
}) {
  const [exportingPdf, setExportingPdf] = useState(false);
  const [pdfExportError, setPdfExportError] = useState<string | null>(null);
  const exportReportPdf = useCallback(() => {
    if (exportingPdf || !selectedBrand) return;
    setPdfExportError(null);
    setExportingPdf(true);
    const generatedAt = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date());
    const fileDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
    const reportWindow = window.open("", "_blank", "width=980,height=900");
    if (!reportWindow) {
      setPdfExportError("PDF 창을 열지 못했습니다. 브라우저 팝업 차단을 해제한 뒤 다시 시도해 주세요.");
      setExportingPdf(false);
      return;
    }
    reportWindow.document.open();
    reportWindow.document.write(buildBrandReportPdfHtml({ brandDisplayName: displayBrandName(selectedBrand.brand), generatedAt, fileDate, reportBasisRows, metricRows, summaryRows }));
    reportWindow.document.close();
    window.setTimeout(() => setExportingPdf(false), 800);
  }, [exportingPdf, metricRows, reportBasisRows, selectedBrand, summaryRows]);

  return { exportingPdf, pdfExportError, exportReportPdf };
}
