"use client";

import { useEffect, useState } from "react";
import type { CrossAxis, CrossScale } from "@/lib/cross-analysis-matrix";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";
import type { ReportBlock } from "../../lib/types";
import {
  CrossAnalysisHeader,
  CrossAxisTabs,
  CrossMetricToolbar
} from "./CrossAnalysisControls";
import { CrossHeatmapCard } from "./CrossAnalysisHeatmap";
import { CrossComparisonControls, CrossSelectionChips } from "./CrossAnalysisPeriodControls";
import { CrossAnalysisSummaryStrip } from "./CrossAnalysisSummaryStrip";
import { useCrossAnalysisData } from "./useCrossAnalysisData";
import { useCrossAnalysisReport } from "./useCrossAnalysisReport";
import { useUserPermissions } from "@/lib/use-user-permissions";

export function CrossAnalysisScreenExact({
  reportBlocks
}: {
  reportBlocks: ReportBlock[];
}) {
  const { canExportAmountReport, canViewAmountData } = useUserPermissions();
  const [axis, setAxis] = useState<CrossAxis>("country-brand");
  const [scale, setScale] = useState<CrossScale>("amount");
  const [flipped] = useState(false);
  const { source, period, selection, matrix } = useCrossAnalysisData({ axis, flipped });
  const { season, ingredient, analysisOptions, loading, loadFailed } = source;
  const {
    metric,
    setMetric,
    momCurrentMonth,
    setMomCurrentMonth,
    momComparisonMonth,
    momPeriod,
    momMonthOptions,
    observedMonthSet,
    partialMonthSet,
    momPeriodReady,
    momHasMissingMonth,
    momHasPartialMonth,
    momHasCoverageIssue,
    momCoverageWarningMessage,
    nearestUsableMonth,
    applyNearestAvailableMonths,
    crossYoyWindow,
    crossYoyMonthOptions,
    yoyBaseMonth,
    setYoyBaseMonth,
    yoyMonthRange,
    yoyDisabled,
    momDisabled,
    averageEurKrwRate,
    crossGrowthBasisLabel
  } = period;
  const {
    displayedSelectedRows,
    displayedSelectedColumns,
    selectedRowCount,
    selectedColumnCount,
    rowSelectionLimitReached,
    columnSelectionLimitReached,
    rowSelectOptions,
    columnSelectOptions,
    selectedAxisLabel,
    addSelectedRow,
    addSelectedColumn,
    removeSelectedRow,
    removeSelectedColumn,
    clearSelection
  } = selection;
  const {
    filterOptions,
    crossDataScopeWarning,
    yoyCoverageWarningMessage,
    crossShareAllocation
  } = matrix;
  const monthComparisonMode = "mom" as const;
  const yoyComparisonMode = "ytd" as const;
  const axisTabs: Array<[CrossAxis, string]> = [
    ["country-brand", "국가 × 브랜드"],
    ["country-sku", "국가 × SKU"],
    ["brand-sku", "브랜드 × SKU"],
    ...(INGREDIENT_ANALYSIS_ENABLED
      ? [
          ["ingredient-country", "성분 × 국가"],
          ["ingredient-brand", "성분 × 브랜드"],
          ["ingredient-sku", "성분 × SKU"]
        ] satisfies Array<[CrossAxis, string]>
      : [])
  ];

  useEffect(() => {
    if (!canViewAmountData && metric === "sales" && scale === "amount") {
      setScale("share");
    }
  }, [canViewAmountData, metric, scale]);

  const {
    crossReportBlockReady,
    exportingCrossPdf,
    exportCrossReportPdf
  } = useCrossAnalysisReport({
    reportBlocks,
    canExportReport: canExportAmountReport,
    axis,
    flipped,
    metric,
    scale,
    monthComparisonMode,
    momCurrentMonth,
    momComparisonMonth,
    yoyComparisonMode,
    yoyMonthRange,
    selectedRows: displayedSelectedRows,
    selectedColumns: displayedSelectedColumns,
    selectedAxisLabel,
    growthBasisLabel: crossGrowthBasisLabel,
    momHasMissingMonth,
    momHasPartialMonth,
    momHasCoverageIssue,
    momCoverageWarningMessage,
    yoyCoverageWarningMessage,
    dataScopeWarning: crossDataScopeWarning,
    averageEurKrwRate,
    analysisOptions,
    matrix: filterOptions,
    shareAllocation: crossShareAllocation
  });


  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <CrossAnalysisHeader
        analysisOptions={analysisOptions}
        canExportReport={canExportAmountReport}
        exporting={exportingCrossPdf}
        reportReady={crossReportBlockReady}
        onExport={exportCrossReportPdf}
      />

      <CrossAxisTabs axis={axis} tabs={axisTabs} onChange={setAxis} />

      <section className="overflow-visible rounded-[14px] border border-border bg-surface shadow-soft">
        <CrossMetricToolbar
          metric={metric}
          scale={scale}
          yoyDisabled={yoyDisabled}
          momDisabled={momDisabled}
          rowOptions={rowSelectOptions}
          columnOptions={columnSelectOptions}
          rowLabel={filterOptions.rowLabel}
          columnLabel={filterOptions.columnLabel}
          selectedRowCount={selectedRowCount}
          selectedColumnCount={selectedColumnCount}
          rowSelectionLimitReached={rowSelectionLimitReached}
          columnSelectionLimitReached={columnSelectionLimitReached}
          growthBasisLabel={crossGrowthBasisLabel}
          canViewAmountData={canViewAmountData}
          onMetric={setMetric}
          onScale={setScale}
          onAddRow={addSelectedRow}
          onAddColumn={addSelectedColumn}
        />
        <CrossComparisonControls
          metric={metric}
          yoyBaseMonth={yoyBaseMonth}
          yoyMonthOptions={crossYoyMonthOptions}
          yoyLatestYear={crossYoyWindow?.latestYear}
          yoyPreviousYear={crossYoyWindow?.previousYear}
          growthBasisLabel={crossGrowthBasisLabel}
          momCurrentMonth={momCurrentMonth}
          momComparisonMonth={momComparisonMonth}
          momMonthOptions={momMonthOptions}
          partialMonths={partialMonthSet}
          observedMonths={observedMonthSet}
          momPeriodReady={momPeriodReady}
          momHasCoverageIssue={momHasCoverageIssue}
          momHasMissingMonth={momHasMissingMonth}
          momHasPartialMonth={momHasPartialMonth}
          momCoverageWarningMessage={momCoverageWarningMessage}
          nearestUsableMonth={nearestUsableMonth}
          yoyCoverageWarningMessage={yoyCoverageWarningMessage}
          onYoyBaseMonth={setYoyBaseMonth}
          onMomCurrentMonth={setMomCurrentMonth}
          onApplyNearestMonth={applyNearestAvailableMonths}
        />
        <CrossSelectionChips
          rows={displayedSelectedRows}
          columns={displayedSelectedColumns}
          rowLabel={filterOptions.rowLabel}
          columnLabel={filterOptions.columnLabel}
          onRemoveRow={removeSelectedRow}
          onRemoveColumn={removeSelectedColumn}
          onClear={clearSelection}
        />
        {loading ? (
          <div className="px-[20px] py-[34px] text-center text-[13px] font-semibold text-muted2">
            CMS 교차분석 결과를 불러오는 중입니다.
          </div>
        ) : loadFailed ? (
          <div className="px-[20px] py-[34px] text-center text-[13px] font-semibold text-muted2">
            CMS 분석 결과를 불러오지 못했습니다. 데이터 입력 탭에서 분석 시작을 다시 실행해 주세요.
          </div>
        ) : (
          <>
            <CrossAnalysisSummaryStrip
              axis={axis}
              metric={metric}
              scale={scale}
              season={season}
              ingredient={ingredient}
              selectedRows={displayedSelectedRows}
              selectedColumns={displayedSelectedColumns}
              flipped={flipped}
              momPeriod={momPeriod}
              yoyMonthRange={yoyMonthRange}
              eurKrwRate={averageEurKrwRate}
            />
            <CrossHeatmapCard
              axis={axis}
              metric={metric}
              scale={scale}
              season={season}
              ingredient={ingredient}
              selectedRows={displayedSelectedRows}
              selectedColumns={displayedSelectedColumns}
              flipped={flipped}
              momPeriod={momPeriod}
              yoyMonthRange={yoyMonthRange}
              eurKrwRate={averageEurKrwRate}
            />
          </>
        )}
      </section>
    </div>
  );
}
