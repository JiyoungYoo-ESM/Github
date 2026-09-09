"use client";

import { ChevronDown, ListChecks } from "lucide-react";
import { formatNumber } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { displayBrandName } from "@/lib/brand-display";
import type { AnalyzeResponse } from "@/types/api";
import type { Screen } from "../../lib/types";
import { AnalysisStartRequiredState } from "../../shared/AnalysisRequiredState";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import { OrderMetricCard } from "../../shared/OrderMetricCard";
import { OrderSubTabs } from "../../shared/OrderSubTabs";
import { StatusPill } from "../../shared/StatusPill";
import {
  compactKrw,
  displayedInboundQty,
  formatMoiDisplay,
  orderMoi,
  orderReason,
  orderReasonDisplay,
  orderSortLabels,
  orderStatus,
  orderTableColumns,
  productDisplayName,
  scenarioStockQty,
  sortableOrderColumns,
  adjustedOrderQty,
  adjustedOrderAmount,
  type InboundScenario
} from "./orderScreenModel";
import { useOrderScreenModel } from "./useOrderScreenModel";

export function OrderScreenExact({
  analysisReady,
  currentAnalysisResult,
  onNavigate
}: {
  analysisReady: boolean;
  currentAnalysisResult: AnalyzeResponse | null;
  onNavigate: (screen: Screen) => void;
}) {
  const {
    rows,
    loadFailed,
    latestRunLabel,
    latestRunMeta,
    exportError,
    exportingExcel,
    exportMenuOpen,
    setExportMenuOpen,
    inboundScenario,
    setInboundScenario,
    selectedBrand,
    setSelectedBrand,
    brandOptions,
    orderSort,
    toggleOrderSort,
    pageSize,
    setPageSize,
    setPage,
    currentPage,
    totalPages,
    pagedRows,
    visibleRows,
    actionableRows,
    totalOrderQty,
    totalOrderAmount,
    visibleOrderTableColumns,
    columnWidths,
    startColumnResize,
    tableWidth,
    exportFullOrderReviewExcel,
    exportCurrentFilterExcel
  } = useOrderScreenModel({ analysisReady, currentAnalysisResult });

  if (!analysisReady) {
    return (
      <AnalysisStartRequiredState
        title="발주 분석을 시작해야 합니다"
        description="아직 이번 세션에서 발주 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 발주 추천 SKU와 재고공백 결과가 이 화면에 반영됩니다."
        onNavigate={onNavigate}
      />
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px] flex flex-col items-stretch gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-[17px] font-black leading-none text-ink">발주 분석</h2>
          </div>
          <p className="mt-[10px] text-[13px] font-semibold leading-none text-muted">
            실제 발주 필요 수량 · 재고 · MOI · 미입고 · 운송중 반영. 분석 결과 기반 실행용 화면입니다.
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end lg:w-auto">
          <div className="flex w-full rounded-[16px] bg-segbg p-1 shadow-card sm:w-auto">
            {[
              ["before", "미입고 해소 전"],
              ["after", "미입고 해소 후"]
            ].map(([value, label]) => {
              const active = inboundScenario === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => setInboundScenario(value as InboundScenario)}
                  className={cn(
                    "h-[42px] flex-1 rounded-[10px] px-3 text-[13px] font-black transition sm:h-[38px] sm:px-5",
                    active ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <BrandSearchSelect value={selectedBrand} options={brandOptions} allValue="all" onChange={setSelectedBrand} responsiveFullWidth />
          <div className="relative w-full sm:w-auto">
            <button
              type="button"
              onClick={() => setExportMenuOpen((open) => !open)}
              className="inline-flex h-[42px] w-full items-center justify-center gap-2 rounded-[10px] bg-brand px-4 text-[13px] font-black text-white sm:h-[38px] sm:w-auto"
            >
              <ListChecks className="h-4 w-4" />
              {exportingExcel ? "엑셀 생성 중…" : "엑셀 내보내기"}
              <ChevronDown className={cn("h-4 w-4 transition", exportMenuOpen && "rotate-180")} />
            </button>
            {exportMenuOpen ? (
              <div className="absolute left-0 right-0 top-[46px] z-40 overflow-hidden rounded-[12px] border border-border bg-surface py-1 shadow-soft sm:left-auto sm:right-0 sm:top-11 sm:w-[260px]">
                <button
                  type="button"
                  onClick={() => void exportCurrentFilterExcel()}
                  disabled={exportingExcel}
                  className="block w-full px-4 py-3 text-left text-[13px] font-black text-ink hover:bg-surface-soft disabled:cursor-not-allowed disabled:text-muted2 disabled:opacity-50"
                >
                  {selectedBrand === "all" ? "전체 브랜드 데이터 내보내기" : `${selectedBrand} 데이터 내보내기`}
                  <span className="mt-1 block text-[11px] font-bold text-muted">
                    {selectedBrand === "all" ? "전체 브랜드" : `브랜드: ${selectedBrand}`} · {formatNumber(visibleRows.length)} SKU
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => void exportFullOrderReviewExcel()}
                  disabled={exportingExcel}
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
      {exportError ? (
        <div className="mb-4 rounded-[10px] border border-brand/20 bg-brand-50 px-4 py-3 text-[12.5px] font-black text-brand">
          {exportError}
        </div>
      ) : null}

      <OrderSubTabs active="order" onNavigate={onNavigate} />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-border bg-surface px-4 py-3 shadow-soft">
        <div>
          <p className="text-[12px] font-black text-ink">
            표시 기준: {orderSortLabels[orderSort.key]} {orderSort.direction === "desc" ? "내림차순" : "오름차순"}
          </p>
          <p className="mt-1 text-[12px] font-semibold text-muted">
            발주 권장 SKU는 미입고 · 운송중 · 현재고 · MOI를 반영한 뒤 선택한 기준으로 정렬됩니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-black text-muted">
          {latestRunLabel ? (
            <span className="rounded-full bg-row px-2.5 py-1" title={latestRunMeta?.jobId ?? undefined}>
              분석 실행: {latestRunLabel}
            </span>
          ) : null}
          <span className="rounded-full bg-row px-2.5 py-1">브랜드: {selectedBrand === "all" ? "전체" : selectedBrand}</span>
          <span className="rounded-full bg-row px-2.5 py-1">대상: {formatNumber(visibleRows.length)} SKU</span>
        </div>
      </div>

      <div className="mb-4 grid gap-[14px] md:grid-cols-2 xl:grid-cols-4">
        <OrderMetricCard label={"발주필요 SKU"} value={formatNumber(actionableRows.length)} />
        <OrderMetricCard label={"긴급 SKU"} value={formatNumber(actionableRows.filter((row) => orderMoi(row, inboundScenario) < 1.5).length)} accent sub={"MOI 1.5개월 미만"} />
        <OrderMetricCard label={"총 발주필요수량"} value={formatNumber(totalOrderQty)} />
        <OrderMetricCard label={"총 발주필요금액"} value={compactKrw(totalOrderAmount)} />
      </div>

      <div className="space-y-3 md:hidden">
        {rows === null ? (
          <div className="rounded-[14px] border border-border bg-surface px-4 py-10 text-center text-[13px] font-black text-muted">발주 분석 데이터를 불러오는 중입니다.</div>
        ) : visibleRows.length === 0 ? (
          <div className="rounded-[14px] border border-border bg-surface px-4 py-10 text-center text-[13px] font-black text-muted">
            {loadFailed ? "발주 분석 데이터를 불러오지 못했습니다." : "분석 결과가 없습니다."}
          </div>
        ) : (
          pagedRows.map((row) => {
            const status = orderStatus(row, inboundScenario);
            const moi = orderMoi(row, inboundScenario);
            const orderQty = adjustedOrderQty(row, inboundScenario);
            const orderAmount = adjustedOrderAmount(row, inboundScenario);
            const stockQty = scenarioStockQty(row, inboundScenario);
            const reasonDisplay = orderReasonDisplay(row, inboundScenario);
            return (
              <article key={row.sku} className="rounded-[14px] border border-border bg-surface p-4 shadow-soft">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-black text-ink">{productDisplayName(row)}</p>
                    <p className="mt-1 truncate text-[11.5px] font-bold text-muted">{row.productCode || row.sku} · {displayBrandName(row.brand)}</p>
                  </div>
                  <StatusPill status={status} />
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-divider py-3 text-[12px]">
                  <div><dt className="text-muted">현재 재고</dt><dd className="mt-1 tnum font-black text-ink">{formatNumber(stockQty)}</dd></div>
                  <div><dt className="text-muted">현재 MOI</dt><dd className="mt-1 tnum font-black text-ink">{formatMoiDisplay(moi, stockQty)}</dd></div>
                  <div><dt className="text-muted">발주 필요수량</dt><dd className="mt-1 tnum font-black text-brand">{formatNumber(orderQty)}</dd></div>
                  <div><dt className="text-muted">발주 필요금액</dt><dd className="mt-1 tnum font-black text-ink">{compactKrw(orderAmount)}</dd></div>
                </dl>
                {reasonDisplay.headline ? <p className="mt-3 text-[12px] font-bold leading-5 text-ink3">{reasonDisplay.headline}</p> : null}
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
          <table className="table-fixed border-collapse" style={{ minWidth: tableWidth, width: tableWidth }}>
            <colgroup>
              {visibleOrderTableColumns.map((column) => (
                <col key={column.key} style={{ width: columnWidths[column.key] }} />
              ))}
            </colgroup>
            <thead className="bg-surface-soft">
              <tr>
                {visibleOrderTableColumns.map((column) => {
                  const columnLabel = column.key === "stock" && inboundScenario === "after" ? "해소 후 재고" : column.label;
                  const columnSortKey = sortableOrderColumns[column.key];
                  const sortActive = columnSortKey === orderSort.key;
                  return (
                    <th
                      key={column.key}
                      aria-sort={sortActive ? (orderSort.direction === "desc" ? "descending" : "ascending") : undefined}
                      className={cn(
                        "relative border-b border-divider px-4 py-[13px] text-[12px] font-black text-muted",
                        column.align === "left" ? "text-left" : "text-center"
                      )}
                    >
                      {columnSortKey ? (
                        <button
                          type="button"
                          onClick={() => toggleOrderSort(columnSortKey)}
                          className={cn("inline-flex whitespace-nowrap items-center gap-1 transition hover:text-ink", sortActive && "text-ink")}
                          title={`${columnLabel} 기준 정렬`}
                        >
                          <span>{columnLabel}</span>
                          <ChevronDown
                            className={cn(
                              "h-3.5 w-3.5 transition",
                              sortActive ? "text-brand" : "text-muted2/50",
                              sortActive && orderSort.direction === "asc" && "rotate-180"
                            )}
                          />
                        </button>
                      ) : (
                        <span>{columnLabel}</span>
                      )}
                      <button
                        type="button"
                        aria-label={`${columnLabel} 컬럼 너비 조절`}
                        title="드래그해서 컬럼 너비 조절"
                        onPointerDown={(event) => startColumnResize(column.key, event)}
                        className={cn(
                          "absolute right-0 top-0 h-full w-2 cursor-col-resize touch-none border-r border-transparent hover:border-brand/50 hover:bg-brand/10"
                        )}
                      />
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows === null ? (
                <tr>
                  <td colSpan={visibleOrderTableColumns.length} className="px-4 py-10 text-center text-[13px] font-black text-muted">
                    발주 분석 데이터를 불러오는 중입니다.
                  </td>
                </tr>
              ) : visibleRows.length === 0 ? (
                <tr>
                  <td colSpan={visibleOrderTableColumns.length} className="px-4 py-10 text-center text-[13px] font-black text-muted">
                    {loadFailed ? "발주 분석 데이터를 불러오지 못했습니다." : "분석 결과가 없습니다. 데이터 입력에서 발주 분석을 먼저 실행해 주세요."}
                  </td>
                </tr>
              ) : (
                pagedRows.map((row) => {
                  const status = orderStatus(row, inboundScenario);
                  const moi = orderMoi(row, inboundScenario);
                  const orderQty = adjustedOrderQty(row, inboundScenario);
                  const orderAmount = adjustedOrderAmount(row, inboundScenario);
                  const stockQty = scenarioStockQty(row, inboundScenario);
                  const reason = orderReason(row, inboundScenario);
                  const reasonDisplay = orderReasonDisplay(row, inboundScenario);
                  return (
                    <tr key={row.sku} className="border-b border-rowline last:border-b-0">
                      <td
                        className="truncate px-4 py-[15px] text-[13px] font-semibold text-ink3"
                        title={row.productCode || row.sku}
                      >
                        {row.productCode || row.sku}
                      </td>
                      <td className="truncate px-4 py-[15px] text-[13px] font-black text-ink" title={row.productName || row.sku}>{productDisplayName(row)}</td>
                      <td className="truncate px-4 py-[15px] text-center text-[13px] font-semibold text-ink3" title={row.brand}>{displayBrandName(row.brand)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-black text-ink">{formatNumber(stockQty)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-black text-ink">{formatNumber(row.recentSalesQty)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-black text-ink">{formatMoiDisplay(moi, stockQty)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-black text-brand">{formatNumber(orderQty)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-black text-ink">{compactKrw(orderAmount)}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-semibold text-muted">{formatNumber(displayedInboundQty(row, inboundScenario))}</td>
                      <td className="tnum whitespace-nowrap px-4 py-[15px] text-center text-[13px] font-semibold text-muted">{formatNumber(row.shippingQty)}</td>
                      <td className="px-4 py-[12px] text-left" title={reason || undefined}>
                        {reasonDisplay.headline ? (
                          <div className="max-w-[420px]">
                            <p className="whitespace-normal break-keep text-[12.5px] font-bold leading-[1.35] text-ink3">{reasonDisplay.headline}</p>
                            {reasonDisplay.detail ? (
                              <p className="mt-1 whitespace-normal break-keep text-[11.5px] font-semibold leading-[1.35] text-muted">{reasonDisplay.detail}</p>
                            ) : null}
                          </div>
                        ) : (
                          <span className="text-[12px] font-semibold text-muted">-</span>
                        )}
                      </td>
                      <td className="px-4 py-[15px] text-center">
                        <StatusPill status={status} />
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
      </div>
    </div>
  );
}
