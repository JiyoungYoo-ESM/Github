"use client";

import { useCallback, useMemo, useState } from "react";

import type { ReportBlock } from "../../lib/types";
import { buildCrossAnalysisReportHtml } from "./crossAnalysisReportDocument";
import {
  buildCrossAnalysisReportModel,
  type CrossAnalysisReportModelOptions
} from "./crossAnalysisReportModel";

type CrossAnalysisReportOptions = CrossAnalysisReportModelOptions & {
  reportBlocks: ReportBlock[];
  canExportReport: boolean;
};

export function useCrossAnalysisReport({
  reportBlocks,
  canExportReport,
  ...reportOptions
}: CrossAnalysisReportOptions) {
  const [exportingCrossPdf, setExportingCrossPdf] = useState(false);
  const savedReportBlockIds = useMemo(
    () => new Set(reportBlocks.map((block) => block.id)),
    [reportBlocks]
  );
  const {
    block: crossReportBlock,
    ready: crossReportBlockReady
  } = buildCrossAnalysisReportModel(reportOptions);
  const crossReportBlockAdded = savedReportBlockIds.has(crossReportBlock.id);
  const {
    metric,
    scale,
    selectedAxisLabel,
    matrix: filterOptions,
    shareAllocation: crossShareAllocation,
    momHasCoverageIssue,
    momCoverageWarningMessage,
    yoyCoverageWarningMessage,
    dataScopeWarning: crossDataScopeWarning
  } = reportOptions;

  const exportCrossReportPdf = useCallback(() => {
    if (!canExportReport || exportingCrossPdf) return;
    setExportingCrossPdf(true);

    const generatedAt = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date());
    const fileDate = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul"
    }).format(new Date());
    const reportWindow = window.open("", "_blank", "width=1200,height=900");
    if (!reportWindow) {
      setExportingCrossPdf(false);
      return;
    }

    const html = buildCrossAnalysisReportHtml({
      generatedAt,
      fileDate,
      selectedAxisLabel,
      metric,
      scale,
      matrix: filterOptions,
      shareAllocation: crossShareAllocation,
      eurKrwRate: reportOptions.averageEurKrwRate,
      momHasCoverageIssue,
      momCoverageWarningMessage,
      yoyCoverageWarningMessage,
      dataScopeWarning: crossDataScopeWarning
    });

    reportWindow.document.open();
    reportWindow.document.write(html);
    reportWindow.document.close();
    window.setTimeout(() => setExportingCrossPdf(false), 800);
  }, [
    canExportReport,
    crossDataScopeWarning,
    crossShareAllocation,
    reportOptions.averageEurKrwRate,
    exportingCrossPdf,
    filterOptions,
    metric,
    momCoverageWarningMessage,
    momHasCoverageIssue,
    scale,
    selectedAxisLabel,
    yoyCoverageWarningMessage
  ]);

  return {
    crossReportBlock,
    crossReportBlockReady,
    crossReportBlockAdded,
    exportingCrossPdf,
    exportCrossReportPdf
  };
}
