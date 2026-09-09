"use client";

import { AlertTriangle, ArrowLeftRight, CalendarDays, X } from "lucide-react";

import { formatAnalysisMonthLabel } from "@/lib/cross-analysis-mom";
import type { CrossMetric } from "@/lib/cross-analysis-matrix";
import { cn } from "@/lib/utils";

function CrossComparisonControls({
  metric,
  yoyBaseMonth,
  yoyMonthOptions,
  yoyLatestYear,
  yoyPreviousYear,
  growthBasisLabel,
  momCurrentMonth,
  momComparisonMonth,
  momMonthOptions,
  partialMonths,
  observedMonths,
  momPeriodReady,
  momHasCoverageIssue,
  momHasMissingMonth,
  momHasPartialMonth,
  momCoverageWarningMessage,
  nearestUsableMonth,
  yoyCoverageWarningMessage,
  onYoyBaseMonth,
  onMomCurrentMonth,
  onApplyNearestMonth
}: {
  metric: CrossMetric;
  yoyBaseMonth: number;
  yoyMonthOptions: number[];
  yoyLatestYear?: number;
  yoyPreviousYear?: number;
  growthBasisLabel: string;
  momCurrentMonth: string;
  momComparisonMonth: string;
  momMonthOptions: string[];
  partialMonths: ReadonlySet<string>;
  observedMonths: ReadonlySet<string>;
  momPeriodReady: boolean;
  momHasCoverageIssue: boolean;
  momHasMissingMonth: boolean;
  momHasPartialMonth: boolean;
  momCoverageWarningMessage: string;
  nearestUsableMonth: string;
  yoyCoverageWarningMessage: string;
  onYoyBaseMonth: (month: number) => void;
  onMomCurrentMonth: (month: string) => void;
  onApplyNearestMonth: () => void;
}) {
  return (
    <>
      {metric === "yoy" ? (
        <div className="flex flex-wrap items-center gap-[10px] border-b border-divider bg-surface-soft px-[18px] py-[11px]">
          <div className="mr-[2px] flex items-center gap-[7px] text-[12px] font-black text-ink3">
            <CalendarDays className="h-4 w-4 text-brand" />
            YTD YoY 비교 기준
          </div>
          <label className="flex h-[34px] items-center gap-[8px] rounded-[8px] border border-border bg-surface px-[10px] text-[12px] font-black text-ink3">
            <span>최신 완료월</span>
            <select
              data-testid="cross-yoy-base-month"
              aria-label="YTD YoY 최신 완료월"
              value={yoyBaseMonth}
              onChange={(event) => onYoyBaseMonth(Number(event.target.value))}
              className="h-[26px] min-w-[138px] border-none bg-transparent text-[12px] font-bold text-ink outline-none"
            >
              {yoyMonthOptions.map((month) => (
                <option key={month} value={month}>{yoyLatestYear}년 {month}월</option>
              ))}
            </select>
          </label>
          <ArrowLeftRight className="h-4 w-4 text-muted2" aria-hidden="true" />
          <div data-testid="cross-yoy-comparison-month" aria-label="YTD YoY 자동 비교기간" className="flex h-[34px] items-center gap-[8px] rounded-[8px] border border-border bg-surface px-[12px] text-[12px] font-black text-ink3">
            <span>비교기간</span>
            <strong>{yoyPreviousYear && yoyBaseMonth > 0 ? `${yoyPreviousYear}년 1~${yoyBaseMonth}월` : "-"}</strong>
            <span className="text-muted2">자동</span>
          </div>
          <span className="ml-auto rounded-full border border-border bg-surface px-[10px] py-[5px] text-[11px] font-black text-muted">
            {growthBasisLabel || "전년도 동일 월 데이터 없음"}
          </span>
        </div>
      ) : null}

      {metric === "mom" ? (
        <>
          <div className="flex flex-wrap items-center gap-[10px] border-b border-divider bg-surface-soft px-[18px] py-[11px]">
            <div className="mr-[2px] flex items-center gap-[7px] text-[12px] font-black text-ink3">
              <CalendarDays className="h-4 w-4 text-brand" />
              MoM 비교 기간
            </div>
            <span className="rounded-full border border-border bg-surface px-[9px] py-[5px] text-[11px] font-black text-muted">
              성장 기준 · 매출액
            </span>
            <label className="flex h-[34px] items-center gap-[8px] rounded-[8px] border border-border bg-surface px-[10px] text-[12px] font-black text-ink3">
              <span>기준월</span>
              <select
                data-testid="cross-mom-current-month"
                aria-label="MoM 기준월"
                value={momCurrentMonth}
                onChange={(event) => onMomCurrentMonth(event.target.value)}
                className="h-[26px] min-w-[148px] border-none bg-transparent text-[12px] font-bold text-ink outline-none"
              >
                {[...momMonthOptions].reverse().map((month) => (
                  <option key={month} value={month}>
                    {formatAnalysisMonthLabel(month)}
                    {partialMonths.has(month) ? " · 부분 적재 의심" : observedMonths.has(month) ? "" : " · 데이터 없음"}
                  </option>
                ))}
              </select>
            </label>
            <span className="text-[12px] font-black text-muted2">대비</span>
            <div data-testid="cross-mom-comparison-month" aria-label="MoM 자동 비교월" className="flex h-[34px] items-center gap-[8px] rounded-[8px] border border-border bg-surface px-[12px] text-[12px] font-black text-ink3">
              <span>비교월</span>
              <strong>{formatAnalysisMonthLabel(momComparisonMonth)}</strong>
              <span className="text-muted2">자동</span>
            </div>
            <span
              className={cn(
                "ml-auto rounded-full border px-[10px] py-[5px] text-[11px] font-black",
                !momPeriodReady
                  ? "border-border bg-surface text-muted"
                  : momHasCoverageIssue
                    ? "border-brand/30 bg-brand-50 text-brand"
                    : "border-pos/20 bg-green-50 text-pos"
              )}
            >
              {!momPeriodReady
                ? "비교월 선택 필요"
                : momHasMissingMonth
                  ? "월 데이터 없음"
                  : momHasPartialMonth
                    ? "부분 적재 의심"
                    : "MoM 계산 가능"}
            </span>
          </div>
          {momHasCoverageIssue ? (
            <div aria-live="polite" className="flex flex-wrap items-center gap-[10px] border-b border-brand/15 bg-brand-50 px-[18px] py-[10px] text-[12px] font-bold text-brand">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{momCoverageWarningMessage}. 성장률을 계산하지 않고 표에는 ‘-’로 표시합니다.</span>
              {nearestUsableMonth ? (
                <button
                  type="button"
                  onClick={onApplyNearestMonth}
                  className="ml-auto h-[30px] rounded-[8px] border border-brand/30 bg-surface px-[10px] text-[11px] font-black text-brand hover:bg-white"
                >
                  정상 적재된 {formatAnalysisMonthLabel(nearestUsableMonth)}로 변경
                </button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}

      {yoyCoverageWarningMessage ? (
        <div aria-live="polite" className="flex items-center gap-[10px] border-b border-brand/15 bg-brand-50 px-[18px] py-[10px] text-[12px] font-bold text-brand">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{yoyCoverageWarningMessage} 표에는 ‘-’로 표시합니다.</span>
        </div>
      ) : null}
    </>
  );
}

function CrossSelectionChips({
  rows,
  columns,
  rowLabel,
  columnLabel,
  onRemoveRow,
  onRemoveColumn,
  onClear
}: {
  rows: string[];
  columns: string[];
  rowLabel: string;
  columnLabel: string;
  onRemoveRow: (item: string) => void;
  onRemoveColumn: (item: string) => void;
  onClear: () => void;
}) {
  if (rows.length === 0 && columns.length === 0) return null;

  return (
    <div data-testid="cross-selection-chips" className="flex flex-wrap items-center gap-[8px] border-b border-divider bg-surface-soft px-[18px] py-[10px]">
      {rows.map((item) => (
        <button
          key={`row-${item}`}
          type="button"
          onClick={() => onRemoveRow(item)}
          className="inline-flex h-[28px] items-center gap-[6px] rounded-[7px] border border-border bg-surface px-[9px] text-[12px] font-black text-ink3"
        >
          <span className="text-muted2">{rowLabel}</span>
          {item}
          <X className="h-3.5 w-3.5 text-muted2" />
        </button>
      ))}
      {columns.map((item) => (
        <button
          key={`column-${item}`}
          type="button"
          onClick={() => onRemoveColumn(item)}
          className="inline-flex h-[28px] items-center gap-[6px] rounded-[7px] border border-brand/30 bg-brand-50 px-[9px] text-[12px] font-black text-brand"
        >
          <span>{columnLabel}</span>
          {item}
          <X className="h-3.5 w-3.5" />
        </button>
      ))}
      <button
        type="button"
        data-testid="cross-clear-selection"
        onClick={onClear}
        className="ml-auto h-[28px] rounded-[7px] border border-border bg-surface px-[9px] text-[12px] font-black text-muted2"
      >
        전체 초기화
      </button>
    </div>
  );
}

export { CrossComparisonControls, CrossSelectionChips };
