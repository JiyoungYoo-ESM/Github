"use client";

import { FileText } from "lucide-react";

import type { CrossAxis, CrossMetric, CrossScale } from "@/lib/cross-analysis-matrix";
import { cn } from "@/lib/utils";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";

function CrossTabButton({
  id,
  label,
  active,
  onClick
}: {
  id: CrossAxis;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={`cross-axis-${id}`}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "h-[40px] rounded-[9px] border px-[21px] text-[13px] font-black shadow-soft",
        active ? "border-brand bg-brand text-white shadow-card" : "border-border bg-surface text-ink3"
      )}
    >
      {label}
    </button>
  );
}

function CrossSegmentButton({
  testId,
  label,
  active,
  disabled,
  onClick
}: {
  testId: string;
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "h-[34px] rounded-[8px] px-[16px] text-[12px] font-black",
        active ? "bg-surface text-ink shadow-sm" : "text-muted",
        disabled ? "cursor-not-allowed text-muted2 opacity-40" : ""
      )}
    >
      {label}
    </button>
  );
}

function CrossAnalysisHeader({
  analysisOptions,
  canExportReport,
  exporting,
  reportReady,
  onExport
}: {
  analysisOptions: Record<string, unknown> | null;
  canExportReport: boolean;
  exporting: boolean;
  reportReady: boolean;
  onExport: () => void;
}) {
  return (
    <div className="mb-[18px] flex items-start justify-between gap-4">
      <div>
        <h2 className="text-[18px] font-black leading-none text-ink">교차 분석</h2>
        <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
          국가·브랜드·SKU가 겹치는 정보는 화면을 따로 만들지 않습니다. 하나의 교차표에서 금액/비중 ·
          매출/판매량/YoY/MoM 토글로 같은 데이터 큐브를 다른 각도로 봅니다.
        </p>
        <div className="mt-[12px]">
          <AnalysisPeriodBadge options={analysisOptions} />
          <AnalysisPeriodCaveat options={analysisOptions} />
        </div>
      </div>
      {canExportReport ? <button
        type="button"
        data-testid="cross-export-report"
        onClick={onExport}
        disabled={exporting || !reportReady}
        className="inline-flex h-[38px] shrink-0 items-center gap-2 rounded-[10px] bg-brand px-4 text-[13px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-70"
      >
        <FileText className="h-4 w-4" />
        {exporting ? "PDF 생성 중" : "리포트로 내보내기"}
      </button> : null}
    </div>
  );
}

function CrossAxisTabs({
  axis,
  tabs,
  onChange
}: {
  axis: CrossAxis;
  tabs: Array<[CrossAxis, string]>;
  onChange: (axis: CrossAxis) => void;
}) {
  return (
    <div className="mb-[16px] flex flex-wrap gap-[10px]">
      {tabs.map(([id, label]) => (
        <CrossTabButton key={id} id={id} label={label} active={axis === id} onClick={() => onChange(id)} />
      ))}
    </div>
  );
}

function CrossMetricToolbar({
  metric,
  scale,
  yoyDisabled,
  momDisabled,
  rowOptions,
  columnOptions,
  rowLabel,
  columnLabel,
  selectedRowCount,
  selectedColumnCount,
  rowSelectionLimitReached,
  columnSelectionLimitReached,
  growthBasisLabel,
  canViewAmountData,
  onMetric,
  onScale,
  onAddRow,
  onAddColumn
}: {
  metric: CrossMetric;
  scale: CrossScale;
  yoyDisabled: boolean;
  momDisabled: boolean;
  rowOptions: string[];
  columnOptions: string[];
  rowLabel: string;
  columnLabel: string;
  selectedRowCount: number;
  selectedColumnCount: number;
  rowSelectionLimitReached: boolean;
  columnSelectionLimitReached: boolean;
  growthBasisLabel: string;
  canViewAmountData: boolean;
  onMetric: (metric: CrossMetric) => void;
  onScale: (scale: CrossScale) => void;
  onAddRow: (value: string) => void;
  onAddColumn: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-[12px] border-b border-divider px-[18px] py-[14px]">
      <div className="flex h-[38px] rounded-[10px] bg-segbg p-1">
        <CrossSegmentButton testId="cross-metric-sales" label="매출액" active={metric === "sales"} onClick={() => onMetric("sales")} />
        <CrossSegmentButton testId="cross-metric-quantity" label="판매량" active={metric === "quantity"} onClick={() => onMetric("quantity")} />
        <CrossSegmentButton testId="cross-metric-yoy" label="완료월 누계 (YTD YoY)" active={metric === "yoy"} disabled={yoyDisabled} onClick={() => onMetric("yoy")} />
        <CrossSegmentButton testId="cross-metric-mom" label="전월 대비 (MoM)" active={metric === "mom"} disabled={momDisabled} onClick={() => onMetric("mom")} />
      </div>
      <div className="flex h-[38px] rounded-[10px] bg-segbg p-1">
        {canViewAmountData || metric !== "sales" ? <CrossSegmentButton testId="cross-scale-amount" label={metric === "sales" ? "금액" : "수량"} active={scale === "amount"} disabled={metric === "yoy" || metric === "mom"} onClick={() => onScale("amount")} /> : null}
        <CrossSegmentButton testId="cross-scale-share" label="비중" active={scale === "share"} disabled={metric === "yoy" || metric === "mom"} onClick={() => onScale("share")} />
      </div>
      <BrandSearchSelect
        value=""
        options={rowOptions}
        onChange={onAddRow}
        dropdownAlign="left"
        disabled={rowSelectionLimitReached}
        buttonLabel={rowSelectionLimitReached ? `${rowLabel} 최대 6개 선택됨` : selectedRowCount > 0 ? `${rowLabel} 추가` : `${rowLabel} 선택`}
        searchPlaceholder={`${rowLabel} 검색`}
        testId="cross-row-select"
      />
      <BrandSearchSelect
        value=""
        options={columnOptions}
        onChange={onAddColumn}
        dropdownAlign="left"
        disabled={columnSelectionLimitReached}
        buttonLabel={columnSelectionLimitReached ? `${columnLabel} 최대 6개 선택됨` : selectedColumnCount > 0 ? `${columnLabel} 추가` : `${columnLabel} 선택`}
        searchPlaceholder={`${columnLabel} 검색`}
        testId="cross-column-select"
      />
      <div className="ml-auto flex items-center gap-[14px]">
        <p className="text-[12px] font-semibold text-muted2">
          {metric === "yoy"
            ? `금액 YTD YoY${growthBasisLabel ? ` · ${growthBasisLabel}` : " · 완료월 누계 비교 데이터 없음"} · 초록=성장, 빨강=감소`
            : metric === "mom"
              ? `MoM(직전 월 대비)${growthBasisLabel ? ` · ${growthBasisLabel}` : ""} · 초록=성장, 빨강=감소`
              : "셀 색이 진할수록 규모가 큼"}
        </p>
      </div>
    </div>
  );
}

export { CrossAnalysisHeader, CrossAxisTabs, CrossMetricToolbar };
