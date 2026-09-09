"use client";

import { useState } from "react";
import { displayBrandName } from "@/lib/brand-display";
import { cn, formatNumber } from "@/lib/utils";
import type { ReportBlock, Screen } from "../../lib/types";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import { BrandBar } from "../../shared/BrandBar";
import { InsightAnalysisRequiredState } from "../../shared/AnalysisRequiredState";
import { RankingDetailDialog, RankingDetailOpenButton } from "../../shared/RankingDetailDialog";
import { SkuChoiceCard, SkuSearchSelect } from "./SkuScreenParts";
import { useSkuScreenModel } from "./useSkuScreenModel";
import { useUserPermissions } from "@/lib/use-user-permissions";

export function SkuScreenExact({
  onNavigate,
  reportBlocks,
  onToggleReportBlock
}: {
  onNavigate: (screen: Screen) => void;
  reportBlocks: ReportBlock[];
  onToggleReportBlock: (block: ReportBlock) => void;
}) {
  const { canViewAmountData } = useUserPermissions();
  const {
    ALL_FILTER,
    loading,
    loadFailed,
    skuSummaries,
    brandOptions,
    brandFilter,
    setBrandFilter,
    filteredSkuSummaries,
    skuSearchOptions,
    selectedSku,
    setSelectedSku,
    selectedDetail,
    activeSummary,
    activeSkuTab,
    setActiveSkuTab,
    selectedCategory,
    selectedRank,
    peakMonth,
    peakLabel,
    peakTrendShare,
    peakMetricValueLabel,
    peakMetricKrwLabel,
    peakValueMetricLabel,
    peakValueBasisText,
    preparationLabel,
    preparationValue,
    recommendedOrderMonth,
    hasAmountMetric,
    isShortAnalysisRange,
    analysisMonthCount,
    skuTrendShareAxisMax,
    skuTrendChartRows,
    skuTrendSegments,
    countryShares,
    allCountryShares,
    averageEurKrwRate,
    activeSummaryKrwLabel,
    analysisOptions,
  } = useSkuScreenModel({ reportBlocks, onToggleReportBlock });
  const [countryRankingOpen, setCountryRankingOpen] = useState(false);

  if (loading) {
    return (
      <div className="mx-auto max-w-[1320px] py-[24px]">
        <div className="grid min-h-[360px] place-items-center rounded-[16px] border border-border bg-surface text-[13px] font-black text-muted shadow-soft">
          SKU 분석 데이터를 불러오는 중입니다.
        </div>
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-[1320px] py-[24px]">
        <div className="grid min-h-[360px] place-items-center rounded-[16px] border border-border bg-surface text-center shadow-soft">
          <div>
            <h2 className="text-[20px] font-black text-ink">SKU 분석 데이터를 불러오지 못했습니다.</h2>
            <p className="mt-3 text-[13px] font-semibold text-muted">백엔드 연결 상태와 최신 CMS 분석 결과를 확인해 주세요.</p>
          </div>
        </div>
      </div>
    );
  }

  if (skuSummaries.length === 0) {
    return (
      <InsightAnalysisRequiredState
        title="SKU 분석 결과가 아직 없습니다."
        description="데이터 입력 탭에서 CMS API 분석을 실행하면 SKU별 판매 추이와 국가 분포가 이 화면에 반영됩니다."
        onNavigate={onNavigate}
      />
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px]">
        <h2 className="text-[18px] font-black leading-none text-ink">SKU 기준 분석</h2>
        <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
          CMS API 판매 데이터를 기준으로 개별 SKU의 월별 추이와 국가별 판매 분포를 확인하세요.
        </p>
        <div className="mt-[12px]">
          <AnalysisPeriodBadge options={analysisOptions} />
          <AnalysisPeriodCaveat options={analysisOptions} />
        </div>
      </div>

      <div className="mb-[14px] grid gap-[10px] rounded-[14px] border border-border bg-surface p-[12px] shadow-soft lg:grid-cols-[180px_minmax(320px,1fr)]">
        <BrandSearchSelect
          value={brandFilter}
          options={brandOptions}
          allValue={ALL_FILTER}
          allLabel="전체 브랜드"
          getOptionLabel={displayBrandName}
          fullWidth
          dropdownAlign="left"
          onChange={(brand) => {
            setBrandFilter(brand);
            setSelectedSku("");
          }}
        />
        <SkuSearchSelect
          value={selectedSku}
          options={skuSearchOptions}
          onChange={setSelectedSku}
          disabled={filteredSkuSummaries.length === 0}
        />
      </div>

      <div className="mb-[18px] flex items-center justify-between gap-3">
        <div className="flex flex-wrap gap-[10px]">
          {["판매 TOP 10 SKU"].map((item, index) => (
            <button
              key={item}
              type="button"
              className={cn(
                "h-[40px] rounded-full border px-[20px] text-[13px] font-black shadow-soft",
                index === 0 ? "border-warn bg-warn-bg text-warn" : "border-border bg-surface text-ink3"
              )}
            >
              {item}
            </button>
          ))}
        </div>
        <p className="text-right text-[12px] font-black text-muted2">
          현재 범위 {formatNumber(filteredSkuSummaries.length)} SKU / 전체 {formatNumber(skuSummaries.length)} SKU
          <span className="mt-1 block text-[10.5px] font-semibold">금액 · 선택 기간 합계</span>
        </p>
      </div>

      <div className="mb-[18px] grid grid-cols-2 gap-[12px] xl:grid-cols-5">
        {filteredSkuSummaries.slice(0, 10).map((sku, index) => (
          <SkuChoiceCard
            key={sku.sku}
            title={sku.name}
            sub={`${displayBrandName(sku.brand)} · ${sku.category || "카테고리 미분류"}`}
            growth={undefined}
            rank={index + 1}
            active={sku.sku === activeSummary.sku}
            onClick={() => setSelectedSku(sku.sku)}
          />
        ))}
      </div>

      {!selectedDetail ? (
        <div className="grid min-h-[280px] place-items-center rounded-[14px] border border-dashed border-border bg-surface text-center shadow-soft">
          <div>
            <h3 className="text-[18px] font-black text-ink">SKU를 선택해 주세요.</h3>
            <p className="mt-[10px] text-[13px] font-semibold text-muted2">선택 후 월별 판매 추이와 발주 참고 정보를 확인할 수 있습니다.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="mb-[12px] inline-flex rounded-[12px] bg-segbg p-1 shadow-card">
            {[
              ["trend", "월별 판매 비중"],
              ["detail", "발주·국가 정보"]
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveSkuTab(id as "trend" | "detail")}
                className={cn(
                  "h-9 rounded-[9px] px-[18px] text-[13px] font-black transition",
                  activeSkuTab === id ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"
                )}
              >
                {label}
              </button>
            ))}
          </div>

      {activeSkuTab === "trend" ? (
        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-start justify-between border-b border-divider px-[22px] py-[18px]">
            <div>
              <p className="text-[12px] font-black text-muted2">{selectedCategory}</p>
              <h3 className="mt-[8px] text-[20px] font-black leading-none text-ink">{activeSummary.name}</h3>
              <p className="mt-[7px] text-[11px] font-black leading-none text-muted2">상품코드 {activeSummary.sku}</p>
            </div>
            <div className="flex items-start gap-[34px] text-right">
              <div>
                <p className="text-[12px] font-semibold text-muted2">{peakLabel}</p>
                <p className="mt-[4px] text-[20px] font-black leading-none text-brand">{peakMonth.month}월</p>
                <p className="mt-[5px] whitespace-nowrap text-[11px] font-black text-muted2">{formatNumber(peakTrendShare, 1)}%</p>
              </div>
              <div>
                <p className="text-[12px] font-semibold text-muted2">분석 기준</p>
                <p className="mt-[5px] text-[14px] font-black text-ink">{hasAmountMetric ? "매출 비중" : "판매수량 비중"}</p>
              </div>
            </div>
          </div>

          <div className="px-[22px] pb-[16px] pt-[28px]">
            <p className="mb-4 text-[13px] font-black text-ink">월별 판매 비중</p>
            <svg
              role="img"
              aria-label={`${activeSummary.name} 월별 ${hasAmountMetric ? "매출" : "판매수량"} 비중 꺾은선 그래프`}
              viewBox="0 0 1220 162"
              className="h-auto w-full overflow-visible"
            >
              {[38, 80, 122].map((y, index) => {
                const guideValue = index === 0 ? skuTrendShareAxisMax : index === 1 ? skuTrendShareAxisMax / 2 : 0;
                return (
                  <g key={y}>
                    <line x1="52" x2="1180" y1={y} y2={y} className="stroke-divider" strokeDasharray={index === 2 ? undefined : "4 5"} />
                    <text x="44" y={y + 3} textAnchor="end" className="fill-muted2 text-[9px] font-semibold">
                      {formatNumber(guideValue, index === 1 ? 1 : 0)}%
                    </text>
                  </g>
                );
              })}
              {skuTrendSegments.map((segment, segmentIndex) =>
                segment.length > 1 ? (
                  <polyline
                    key={`sku-trend-segment-${segmentIndex}`}
                    points={segment.map((row) => `${row.x},${row.y}`).join(" ")}
                    fill="none"
                    className="stroke-brand"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    vectorEffect="non-scaling-stroke"
                  />
                ) : null
              )}
              {skuTrendChartRows.map((row) => {
                if (!row.hasData) {
                  return (
                    <g key={row.month}>
                      <circle cx={row.x} cy={122} r={3} className="fill-track stroke-border" strokeWidth="1.5" vectorEffect="non-scaling-stroke">
                        <title>{`${row.month}월 · 분석 기간에 데이터 없음`}</title>
                      </circle>
                      <text x={row.x} y="152" textAnchor="middle" opacity="0.5" className="fill-muted2 text-[9px] font-semibold">{row.month}월</text>
                    </g>
                  );
                }
                return (
                  <g key={row.month}>
                    <circle
                      cx={row.x}
                      cy={row.y}
                      r={row.active ? 5 : 3.5}
                      className={row.active ? "fill-brand" : "fill-surface stroke-brand"}
                      strokeWidth="2"
                      vectorEffect="non-scaling-stroke"
                    >
                      <title>{`${row.month}월 ${hasAmountMetric ? "매출" : "판매수량"} 비중 ${formatNumber(row.share, 1)}%`}</title>
                    </circle>
                    <text x={row.x} y={Math.max(12, row.y - 10)} textAnchor="middle" className={cn("text-[9px] font-black", row.active ? "fill-brand" : "fill-muted2")}>
                      {formatNumber(row.share, 1)}%
                    </text>
                    <text x={row.x} y="152" textAnchor="middle" className="fill-muted2 text-[9px] font-semibold">{row.month}월</text>
                  </g>
                );
              })}
            </svg>
          </div>
        </section>
      ) : (
        <div className="grid grid-cols-2 gap-[18px]">
          <section className="rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <h3 className="mb-[16px] text-[14px] font-black text-ink">발주 참고 정보</h3>
            <div className="grid grid-cols-2 gap-y-[17px]">
              <div>
                <p className="text-[12px] font-semibold text-muted2">{hasAmountMetric ? "매출 순위" : "판매수량 순위"}</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-ink">
                  {selectedRank > 0 ? `${formatNumber(selectedRank)}위 / ${formatNumber(filteredSkuSummaries.length)} SKU` : "-"}
                </p>
              </div>
              <div>
                <p className="text-[12px] font-semibold text-muted2">{preparationLabel}</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-brand">{preparationValue}</p>
              </div>
              <div>
                <p className="text-[12px] font-semibold text-muted2">판매수량</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-ink">{formatNumber(activeSummary.qty)}개</p>
              </div>
              {canViewAmountData || !hasAmountMetric ? <div>
                <p className="text-[12px] font-semibold text-muted2">전체 매출</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-ink">{hasAmountMetric ? wonEok(activeSummary.amount) : "-"}</p>
                {activeSummaryKrwLabel ? <p className="mt-[4px] text-[11px] font-black text-muted2">{activeSummaryKrwLabel}</p> : null}
              </div> : null}
              <div>
                <p className="text-[12px] font-semibold text-muted2">판매 국가</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-ink">{formatNumber(activeSummary.countries.size)}개국</p>
              </div>
              {canViewAmountData || !hasAmountMetric ? <div>
                <p className="text-[12px] font-semibold text-muted2">{peakValueMetricLabel}</p>
                <p className="mt-[5px] text-[18px] font-black leading-none text-ink">{peakMetricValueLabel}</p>
                {peakMetricKrwLabel ? <p className="mt-[4px] text-[11px] font-black text-muted2">{peakMetricKrwLabel}</p> : null}
                <p className="mt-[4px] text-[11px] font-bold text-muted2">{peakValueBasisText}</p>
              </div> : null}
            </div>
            <div className="mt-[18px] rounded-[8px] border border-warn-border bg-warn-bg px-[14px] py-[13px]">
              <p className="text-[12px] font-black text-brand">
                {isShortAnalysisRange
                  ? "12개월 미만 분석에서는 연중 피크월을 판단할 수 없어 선택 기간 내 최고월만 표시합니다."
                  : `${peakMonth.month}월 피크 기준 약 3개월 전인 ${recommendedOrderMonth}월부터 판매/발주 준비가 필요합니다.`}
              </p>
            </div>
            {isShortAnalysisRange ? (
              <p className="mt-[10px] text-[11px] font-bold text-muted2">
                현재 분석 범위가 {analysisMonthCount}개월이라 일부 월은 0 또는 기준값 없음으로 표시될 수 있습니다.
              </p>
            ) : null}
            <p className="mt-[15px] text-[12px] font-semibold text-muted2">
              {activeSummary.sku ? `${displayBrandName(activeSummary.brand)} · ${activeSummary.sku}` : "SKU를 검색하거나 필터를 조정해 주세요"}
            </p>
          </section>

          <section className="rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <div className="mb-[17px] flex items-center justify-between gap-3">
              <h3 className="text-[14px] font-black text-ink">국가별 판매 분포 <span className="font-semibold text-muted2">· TOP 5</span></h3>
              <div className="flex items-center gap-2">
                <RankingDetailOpenButton onClick={() => setCountryRankingOpen(true)} />
              </div>
            </div>
            <div className="grid gap-[12px]">
              {countryShares.length > 0 ? (
                countryShares.map((row, index) => <BrandBar key={`${row.name}-${index}`} name={row.name} value={hasAmountMetric && !canViewAmountData ? `${formatNumber(row.percent, 1)}%` : row.value} width={row.width} />)
              ) : (
                <p className="py-8 text-center text-[13px] font-semibold text-muted2">국가별 판매 데이터가 없습니다.</p>
              )}
            </div>
          </section>
        </div>
      )}
      <RankingDetailDialog
        open={countryRankingOpen}
        title={`${activeSummary.name} 국가별 판매 전체 순위`}
        subtitle={`${hasAmountMetric ? "판매금액" : "판매수량"} 기준`}
        valueLabel={hasAmountMetric ? "매출" : "판매수량"}
        rows={allCountryShares.map((row) => ({
          id: row.name,
          label: row.name,
          ...(hasAmountMetric && !canViewAmountData
            ? {}
            : {
                amount: hasAmountMetric ? wonEok(row.amount) : formatNumber(row.qty),
                amountKrw: hasAmountMetric ? krwEokFromEur(row.amount, averageEurKrwRate) : ""
              }),
          sharePct: row.percent
        }))}
        onClose={() => setCountryRankingOpen(false)}
      />
        </>
      )}
    </div>
  );
}
