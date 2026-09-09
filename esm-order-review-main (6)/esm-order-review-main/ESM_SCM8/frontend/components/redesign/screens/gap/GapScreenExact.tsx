"use client";

import { ChevronDown, ListChecks } from "lucide-react";
import { displayBrandName } from "@/lib/brand-display";
import { formatDate as formatStockGapDate } from "@/lib/stock-gap";
import { cn, formatNumber } from "@/lib/utils";
import { AnalysisStartRequiredState } from "../../shared/AnalysisRequiredState";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import { OrderMetricCard } from "../../shared/OrderMetricCard";
import { OrderSubTabs } from "../../shared/OrderSubTabs";
import { StatusPill } from "../../shared/StatusPill";
import type { Screen } from "../../lib/types";
import {
  gapSortLabels,
  gapTableColumns,
  sortableGapColumns,
  stockGapDisplayStatus,
  stockGapEtaLabel,
  stockGapReason,
  stockGapShortageQty
} from "./gapScreenModel";
import { useGapScreenModel } from "./useGapScreenModel";

// 다른 화면(report/ReportBuilder.tsx, SiliconAnalyticsWorkspace.tsx)이 이 파일에서
// stockGapShortageQty/StockGapComputed를 직접 import하므로 하위 호환을 위해 재수출한다.
export { stockGapShortageQty };
export type { StockGapComputed } from "./gapScreenModel";

export function GapScreenExact({ analysisReady, onNavigate }: { analysisReady: boolean; onNavigate: (screen: Screen) => void }) {
  const {
    rows,
    loadFailed,
    selectedBrand,
    setSelectedBrand,
    brandOptions,
    gapSort,
    toggleGapSort,
    gapExportMenuOpen,
    setGapExportMenuOpen,
    gapExportError,
    gapExportingExcel,
    pageSize,
    setPageSize,
    setPage,
    currentPage,
    totalPages,
    pagedRows,
    visibleRows,
    gapRiskRows,
    longGapRows,
    etaMissingRows,
    noInboundRows,
    showDormantRows,
    setShowDormantRows,
    dormantRowCount,
    totalShortageQty,
    gapColumnWidths,
    startGapColumnResize,
    gapTableWidth,
    exportCurrentGapFilterExcel,
    exportFullGapExcel
  } = useGapScreenModel({ analysisReady });

  // 빈 행을 숨긴 탓에 목록이 비었을 때 "결과 없음"으로만 보이면 데이터가 없는 것으로 오해한다.
  const dormantHiddenAll = !showDormantRows && dormantRowCount > 0 && (rows?.length ?? 0) > 0;
  const emptyRowsMessage = loadFailed
    ? "재고 공백 데이터를 불러오지 못했습니다."
    : dormantHiddenAll
      ? `선택한 조건에 해당하는 SKU가 없습니다. 판매·재고 없는 SKU ${formatNumber(dormantRowCount)}건이 숨겨져 있습니다.`
      : "재고 공백 결과가 없습니다. 데이터 입력에서 분석 시작을 먼저 완료해주세요.";

  if (!analysisReady) {
    return (
      <AnalysisStartRequiredState
        title="재고공백 분석을 시작해야 합니다"
        description="재고공백은 발주 분석 결과를 기준으로 계산됩니다. 데이터 입력 탭에서 분석 시작을 먼저 실행하면 재고공백 SKU와 ETA 위험이 표시됩니다."
        onNavigate={onNavigate}
      />
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px] flex flex-col items-stretch gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-[17px] font-black leading-none text-ink">재고 공백</h2>
          </div>
          <p className="mt-[10px] text-[13px] font-semibold leading-5 text-muted">
            판매 속도 기준 소진 예정일과 입고(ETA)를 비교해 결품 발생 SKU · 공백 일수 · 부족 수량을 보여줍니다. 발주 검토 직전 결품 리스크 점검용입니다.
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-end lg:w-auto">
          <BrandSearchSelect value={selectedBrand} options={brandOptions} allValue="전체" onChange={setSelectedBrand} responsiveFullWidth />
          <div className="relative w-full sm:w-auto">
            <button
              type="button"
              onClick={() => setGapExportMenuOpen((open) => !open)}
              className="inline-flex h-[42px] w-full items-center justify-center gap-2 rounded-[10px] bg-brand px-4 text-[13px] font-black text-white sm:h-[38px] sm:w-auto"
            >
              <ListChecks className="h-4 w-4" />
              {gapExportingExcel ? "엑셀 생성 중…" : "엑셀 내보내기"}
              <ChevronDown className={cn("h-4 w-4 transition", gapExportMenuOpen && "rotate-180")} />
            </button>
            {gapExportMenuOpen ? (
              <div className="absolute left-0 right-0 top-[46px] z-40 overflow-hidden rounded-[12px] border border-border bg-surface py-1 shadow-soft sm:left-auto sm:right-0 sm:top-11 sm:w-[260px]">
                <button
                  type="button"
                  onClick={() => void exportCurrentGapFilterExcel()}
                  disabled={gapExportingExcel}
                  className="block w-full px-4 py-3 text-left text-[13px] font-black text-ink hover:bg-surface-soft disabled:cursor-not-allowed disabled:text-muted2 disabled:opacity-50"
                >
                  {selectedBrand === "전체" ? "전체 브랜드 데이터 내보내기" : `${selectedBrand} 데이터 내보내기`}
                  <span className="mt-1 block text-[11px] font-bold text-muted">
                    {selectedBrand === "전체" ? "전체 브랜드" : `브랜드: ${selectedBrand}`} · {formatNumber(visibleRows.length)} SKU
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void exportFullGapExcel()}
                  disabled={gapExportingExcel}
                  className="block w-full border-t border-divider px-4 py-3 text-left text-[13px] font-black text-ink hover:bg-surface-soft disabled:cursor-not-allowed disabled:opacity-50"
                >
                  발주분석 원본 전체 파일 다운로드
                  <span className="mt-1 block text-[11px] font-bold text-muted">
                    전체 ESM_order 다중 시트 파일
                  </span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
      {gapExportError ? (
        <div className="mb-4 rounded-[10px] border border-brand/20 bg-brand-50 px-4 py-3 text-[12.5px] font-black text-brand">
          {gapExportError}
        </div>
      ) : null}

      <OrderSubTabs active="gap" onNavigate={onNavigate} />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-border bg-surface px-4 py-3 shadow-soft">
        <div>
          <p className="text-[12px] font-black text-ink">
            표시 기준: {gapSortLabels[gapSort.key]} {gapSort.direction === "desc" ? "내림차순" : "오름차순"}
          </p>
          <p className="mt-1 text-[12px] font-semibold text-muted">
            판매 속도 기준 소진 예정일과 최초 ETA를 비교해 재고 공백 리스크를 선택한 기준으로 정렬합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-black text-muted">
          <span className="rounded-full bg-row px-2.5 py-1">브랜드: {selectedBrand}</span>
          <span className="rounded-full bg-row px-2.5 py-1">대상: {formatNumber(gapRiskRows.length)} SKU</span>
          {dormantRowCount > 0 ? (
            <button
              type="button"
              onClick={() => setShowDormantRows((value) => !value)}
              aria-pressed={showDormantRows}
              title="판매 이력·현재고·운송중·미입고가 모두 없어 재고 공백을 판정할 근거가 없는 SKU입니다."
              className={cn(
                "rounded-full px-2.5 py-1 transition",
                showDormantRows ? "bg-ink text-surface" : "bg-row text-muted hover:text-ink"
              )}
            >
              판매·재고 없는 SKU {formatNumber(dormantRowCount)}건 {showDormantRows ? "표시 중" : "숨김"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mb-4 grid gap-[14px] md:grid-cols-2 xl:grid-cols-5">
        <OrderMetricCard label="재고공백 SKU" value={`${formatNumber(gapRiskRows.length)}건`} accent />
        <OrderMetricCard label="7일 이상 공백 SKU" value={`${formatNumber(longGapRows.length)}건`} />
        <OrderMetricCard label="예상 부족 수량" value={`${formatNumber(totalShortageQty)}개`} />
        <OrderMetricCard
          label="입고예정 없는 소진 SKU"
          value={`${formatNumber(noInboundRows.length)}건`}
          sub="발주 검토 필요"
          subTone="muted"
        />
        <OrderMetricCard label="ETA 미확인 SKU" value={`${formatNumber(etaMissingRows.length)}건`} />
      </div>

      <div className="space-y-3 md:hidden">
        {rows === null ? (
          <div className="rounded-[14px] border border-border bg-surface px-4 py-10 text-center text-[13px] font-black text-muted">재고공백 데이터를 불러오는 중입니다.</div>
        ) : visibleRows.length === 0 ? (
          <div className="rounded-[14px] border border-border bg-surface px-4 py-10 text-center text-[13px] font-black text-muted">
            {emptyRowsMessage}
          </div>
        ) : (
          pagedRows.map((row) => {
            const shortageQty = stockGapShortageQty(row);
            const displayName = row.productName && row.productName !== "-" ? row.productName : row.sku;
            const reason = stockGapReason(row);
            return (
              <article key={row.sku} className="rounded-[14px] border border-border bg-surface p-4 shadow-soft">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-black text-ink">{displayName}</p>
                    <p className="mt-1 truncate text-[11.5px] font-bold text-muted">{row.productCode || row.sku} · {displayBrandName(row.brand)}</p>
                  </div>
                  <StatusPill status={stockGapDisplayStatus(row)} />
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-divider py-3 text-[12px]">
                  <div><dt className="text-muted">재고 소진일</dt><dd className="mt-1 tnum font-black text-ink">{formatStockGapDate(row.stockoutDate)}</dd></div>
                  <div><dt className="text-muted">최초 ETA</dt><dd className="mt-1 tnum font-black text-ink">{stockGapEtaLabel(row)}</dd></div>
                  <div><dt className="text-muted">공백 일수</dt><dd className="mt-1 tnum font-black text-brand">{row.gapDays === null ? "-" : `${formatNumber(row.gapDays)}일`}</dd></div>
                  <div><dt className="text-muted">예상 부족수량</dt><dd className="mt-1 tnum font-black text-brand">{formatNumber(shortageQty)}</dd></div>
                </dl>
                {reason ? <p className="mt-3 line-clamp-2 text-[12px] font-bold leading-5 text-muted">{reason}</p> : null}
              </article>
            );
          })
        )}
        {visibleRows.length > 0 ? (
          <div className="flex items-center justify-between rounded-[12px] border border-border bg-surface px-3 py-2.5">
            <button type="button" onClick={() => setPage((value) => Math.max(value - 1, 1))} disabled={currentPage <= 1} className="h-9 rounded-[9px] px-3 text-[12px] font-black text-ink disabled:opacity-40">이전</button>
            <span className="text-[12px] font-black text-muted">{currentPage} / {totalPages}</span>
            <button type="button" onClick={() => setPage((value) => Math.min(value + 1, totalPages))} disabled={currentPage >= totalPages} className="h-9 rounded-[9px] px-3 text-[12px] font-black text-ink disabled:opacity-40">다음</button>
          </div>
        ) : null}
      </div>

      <div className="hidden overflow-hidden rounded-[16px] border border-border bg-surface shadow-soft md:block">
        <div className="overflow-x-auto">
          <table className="table-fixed border-collapse" style={{ minWidth: gapTableWidth, width: gapTableWidth }}>
            <colgroup>
              {gapTableColumns.map((column) => (
                <col key={column.key} style={{ width: gapColumnWidths[column.key] }} />
              ))}
            </colgroup>
            <thead className="bg-surface-soft">
              <tr>
                {gapTableColumns.map((column) => {
                  const columnSortKey = sortableGapColumns[column.key];
                  const sortActive = columnSortKey === gapSort.key;
                  return (
                    <th
                      key={column.key}
                      aria-sort={sortActive ? (gapSort.direction === "desc" ? "descending" : "ascending") : undefined}
                      className={cn(
                        "relative border-b border-divider px-4 py-[13px] text-[12px] font-black text-muted",
                        column.align === "left" ? "text-left" : "text-center"
                      )}
                    >
                      {columnSortKey ? (
                        <button
                          type="button"
                          onClick={() => toggleGapSort(columnSortKey)}
                          className={cn("inline-flex whitespace-nowrap items-center gap-1 transition hover:text-ink", sortActive && "text-ink")}
                          title={`${column.label} 기준 정렬`}
                        >
                          <span>{column.label}</span>
                          <ChevronDown
                            className={cn(
                              "h-3.5 w-3.5 transition",
                              sortActive ? "text-brand" : "text-muted2/50",
                              sortActive && gapSort.direction === "asc" && "rotate-180"
                            )}
                          />
                        </button>
                      ) : (
                        <span>{column.label}</span>
                      )}
                      <button
                        type="button"
                        aria-label={`${column.label} 컬럼 너비 조절`}
                        title="드래그해서 컬럼 너비 조절"
                        onPointerDown={(event) => startGapColumnResize(column.key, event)}
                        className="absolute right-0 top-0 h-full w-2 cursor-col-resize touch-none border-r border-transparent hover:border-brand/50 hover:bg-brand/10"
                      />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows === null ? (
                <tr>
                  <td colSpan={11} className="px-4 py-10 text-center text-[13px] font-black text-muted">
                    재고 공백 데이터를 불러오는 중입니다.
                  </td>
                </tr>
              ) : visibleRows.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-4 py-10 text-center text-[13px] font-black text-muted">
                    {emptyRowsMessage}
                  </td>
                </tr>
              ) : (
                pagedRows.map((row) => {
                  const shortageQty = stockGapShortageQty(row);
                  const displayName = row.productName && row.productName !== "-" ? row.productName : "";
                  const reason = stockGapReason(row);
                  return (
                    <tr key={row.sku} className="border-b border-rowline last:border-b-0">
                      <td
                        className="truncate px-4 py-[15px] text-[13px] font-semibold text-ink3"
                        title={row.productCode || row.sku}
                      >
                        {row.productCode || row.sku}
                      </td>
                      <td className="truncate px-4 py-[15px] text-[13px] font-black text-ink" title={displayName || row.sku}>
                        {displayName || row.sku}
                      </td>
                      <td className="px-4 py-[15px] text-center text-[13px] font-semibold text-ink3">{displayBrandName(row.brand)}</td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-black text-ink">{row.availableQty === null ? "-" : formatNumber(row.availableQty)}</td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-semibold text-muted">
                        {row.dailySalesQty === null ? "-" : `${formatNumber(row.dailySalesQty, 1)}/일`}
                      </td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-black text-ink">{formatStockGapDate(row.stockoutDate)}</td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-semibold text-ink3">{stockGapEtaLabel(row)}</td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-black text-brand">
                        {row.gapDays === null ? "-" : `${formatNumber(row.gapDays)}일`}
                      </td>
                      <td className="tnum px-4 py-[15px] text-center text-[13px] font-black text-brand">{formatNumber(shortageQty)}</td>
                      <td className="max-w-[260px] truncate px-4 py-[15px] text-[12px] font-semibold text-muted" title={reason || undefined}>
                        {reason || "-"}
                      </td>
                      <td className="px-4 py-[15px] text-center">
                        <StatusPill status={stockGapDisplayStatus(row)} />
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {visibleRows.length > 0 ? (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-divider px-5 py-4">
            <div className="text-[12px] font-bold text-muted">
              {formatNumber((currentPage - 1) * pageSize + 1)}
              {"-"}
              {formatNumber(Math.min(currentPage * pageSize, visibleRows.length))}
              {" / "}
              {formatNumber(visibleRows.length)}
              {" SKU"}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={pageSize}
                onChange={(event) => setPageSize(Number(event.target.value))}
                className="h-9 rounded-[9px] border border-border bg-surface px-3 text-[12px] font-black text-ink outline-none"
              >
                {[20, 50, 100].map((size) => (
                  <option key={size} value={size}>
                    {size}개씩
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => setPage((value) => Math.max(value - 1, 1))}
                disabled={currentPage <= 1}
                className="h-9 rounded-[9px] border border-border bg-surface px-3 text-[12px] font-black text-ink disabled:opacity-40"
              >
                이전
              </button>
              <span className="min-w-[70px] text-center text-[12px] font-black text-muted">
                {formatNumber(currentPage)}
                {" / "}
                {formatNumber(totalPages)}
              </span>
              <button
                type="button"
                onClick={() => setPage((value) => Math.min(value + 1, totalPages))}
                disabled={currentPage >= totalPages}
                className="h-9 rounded-[9px] border border-border bg-surface px-3 text-[12px] font-black text-ink disabled:opacity-40"
              >
                다음
              </button>
            </div>
          </div>
        ) : null}
        <p className="border-t border-divider px-5 py-3 text-[12px] font-semibold text-muted2">
          소진 예정일보다 최초 ETA가 늦으면 공백 발생 · 공백 일수 × 판매 속도 = 부족 수량. 발주분석으로 연결됩니다.
        </p>
      </div>
    </div>
  );
}
