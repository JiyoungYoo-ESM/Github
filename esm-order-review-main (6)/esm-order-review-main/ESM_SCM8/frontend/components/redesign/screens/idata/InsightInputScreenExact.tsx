"use client";

import { CalendarDays, Database } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Screen } from "../../lib/types";
import { DEMAND_DATA_MIN_DATE, todayKst } from "../../lib/workspace-format";
import { useAnalysisElapsedLabel } from "../../shared/use-analysis-elapsed";
import { InputDateBoxV2, SourceDataRowV2 } from "./InsightInputScreenParts";
import { HQ_WAREHOUSE_OPTIONS, useInsightInputScreenModel } from "./useInsightInputScreenModel";

export function InsightInputScreenExact({
  onAnalysisComplete,
  onAnalysisInvalidated,
  onNavigate
}: {
  onAnalysisComplete: () => void;
  onAnalysisInvalidated: () => void;
  onNavigate: (screen: Screen) => void;
}) {
  const {
    demandDates,
    analysisRunning,
    analysisPhase,
    analysisStopping,
    analysisError,
    analysisMessage,
    latestSyncText,
    rangeTooLong,
    rangeWarning,
    comparisonPreviewLabel,
    selectedEntity,
    selectedWarehouse,
    hasLongHistoryApi,
    maxDemandEndDate,
    updateDemandDates,
    updateWarehouse,
    startAnalysis,
    stopAnalysis
  } = useInsightInputScreenModel({ onAnalysisComplete, onAnalysisInvalidated, onNavigate });
  const analysisElapsedLabel = useAnalysisElapsedLabel(analysisRunning);
  const isHeadquarters = selectedEntity === "HQ";
  const isUsa = selectedEntity === "USA";

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[22px]">
        <h2 className="text-[22px] font-black leading-none text-ink">데이터 입력</h2>
        <p className="mt-[12px] text-[13px] font-semibold leading-none text-muted">
          CMS 판매이력과 상품목록을 자동 조회해 국가/권역별 수요와 성분 트렌드를 분석합니다.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <section className="rounded-[16px] border border-border bg-surface p-[24px] shadow-soft">
          <div className="flex items-center gap-2">
            <Database className="h-4 w-4 text-brand" />
            <h3 className="text-[15px] font-black text-ink">CMS 원천 데이터</h3>
          </div>
          <p className="mt-3 text-[12.5px] font-semibold leading-[1.5] text-muted">
            파일 업로드 없이 CMS API에서 분석에 필요한 판매이력과 상품 마스터를 조회합니다.
          </p>
          <div className="mt-5 grid gap-3.5">
            <SourceDataRowV2
              title={isHeadquarters ? "본사 장기 판매이력" : "장기 판매이력"}
              description="출고일, 국가/거래처, 상품, 브랜드, 판매수량, 판매금액을 기간 기준으로 조회합니다."
            />
            <SourceDataRowV2
              title="상품목록"
              description={
                hasLongHistoryApi
                  ? "전체 COSMETIC 상품마스터에서 상품코드, 상품명, 브랜드, 기능구분1/2를 조회합니다."
                  : "상품코드, 상품명, 브랜드, 기능구분1/2를 EU 판매 SKU 기준으로 조회합니다."
              }
            />
          </div>
          <div className="mt-4 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-[12px] font-black text-amber-900">조회 기준</p>
            <p className="mt-1 text-[12px] font-semibold leading-[1.5] text-amber-800">
              {isHeadquarters
                ? "본사 장기 판매이력 API는 조회 시작일 제한이 없으며, 한 번에 최대 24개월까지 조회할 수 있습니다."
                : isUsa
                  ? "미주 현지판매 API는 현재 2015년 11월 7일부터 데이터가 확인되며, 한 번에 최대 24개월까지 조회할 수 있습니다."
                  : "판매이력은 2024년 4월부터 현재까지 조회 가능하며, 직접 선택 기간은 최대 24개월까지 가능합니다."}
            </p>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3 rounded-[10px] border border-green-200 bg-green-50 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-green-600" />
              <span className="text-[13px] font-black text-green-800">CMS API 연결됨</span>
            </div>
            <div className="text-right text-[11px] font-semibold leading-[1.45] text-green-700">
              <p>마지막 동기화: {latestSyncText}</p>
              <p>판매이력 184,302건 · 상품 1,284종</p>
            </div>
          </div>
        </section>

        <section className="overflow-visible rounded-[16px] border border-border bg-surface shadow-soft">
          <div className="flex h-[49px] items-center gap-2 border-b border-divider px-[22px]">
            <CalendarDays className="h-4 w-4 text-brand" />
            <h3 className="text-[15px] font-black text-ink">분석 조건</h3>
          </div>
          <div className="p-[22px]">
            {isHeadquarters ? (
              <div className="mb-4">
                <label htmlFor="hq-warehouse" className="mb-2 block text-[12px] font-black text-ink">
                  분석 창고
                </label>
                <select
                  id="hq-warehouse"
                  value={selectedWarehouse}
                  onChange={(event) => updateWarehouse(event.target.value)}
                  disabled={analysisRunning}
                  className="h-10 w-full rounded-[9px] border border-border bg-surface px-3 text-[13px] font-bold text-ink outline-none transition focus:border-sidebar disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {HQ_WAREHOUSE_OPTIONS.map((warehouse) => (
                    <option key={warehouse.value || "all"} value={warehouse.value}>
                      {warehouse.label}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-[11.5px] font-semibold text-muted2">
                  선택한 창고에서 출고된 본사 판매이력만 분석합니다.
                </p>
              </div>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2">
              <InputDateBoxV2
                label="분석 시작일"
                value={demandDates.startDate}
                min={hasLongHistoryApi ? "" : DEMAND_DATA_MIN_DATE}
                max={demandDates.endDate || todayKst}
                onChange={(startDate) => updateDemandDates({ startDate })}
              />
              <InputDateBoxV2
                label="분석 종료일"
                value={demandDates.endDate}
                min={demandDates.startDate || DEMAND_DATA_MIN_DATE}
                max={maxDemandEndDate < todayKst ? maxDemandEndDate : todayKst}
                onChange={(endDate) => updateDemandDates({ endDate })}
              />
            </div>
            <div className="mt-4 rounded-[9px] border border-border bg-row px-4 py-3 text-[12.5px] font-black text-ink">
              선택 기간: {demandDates.startDate} ~ {demandDates.endDate}
            </div>
            <p className="mt-2 text-[12px] font-semibold text-muted2">{comparisonPreviewLabel}</p>
            <p className={cn("mt-2 text-[12px] font-semibold leading-[1.5]", rangeTooLong ? "text-brand" : "text-muted2")}>
              {rangeWarning ||
                (isHeadquarters
                  ? "본사 판매이력은 선택한 기간을 월별·페이지 단위로 조회하며, 한 번에 최대 24개월까지 분석할 수 있습니다."
                  : isUsa
                    ? "미주 판매이력은 선택한 기간을 월별·페이지 단위로 조회하며, 한 번에 최대 24개월까지 분석할 수 있습니다."
                    : "CMS 판매이력은 2024년 4월부터 현재까지 조회되며, 직접 선택 분석 기간은 최대 24개월까지 가능합니다.")}
            </p>
            <p className="mt-2 text-[12px] font-semibold leading-[1.5] text-muted2">
              선택 기간이 12개월 미만이면 결과는 선택 기간 내 집계와 최고월 기준으로 표시되며, 연간 시즌성 판단에는 제한이 있습니다.
            </p>
            {/*
              시작과 중단은 반드시 별도 버튼이어야 한다. 하나의 버튼이 상태에 따라
              시작/중단을 번갈아 맡으면, 연타 중 시작에 성공한 순간 다음 클릭이
              방금 시작한 분석을 취소한다(2026-07-30 실제 사고).
            */}
            <button
              type="button"
              onClick={startAnalysis}
              disabled={analysisRunning || analysisStopping || rangeTooLong}
              className="mt-4 inline-flex h-[44px] w-full items-center justify-center gap-2 rounded-[9px] bg-sidebar px-4 text-[14px] font-black text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className={cn("text-[16px]", !analysisRunning && "leading-none")}>↻</span>
              {analysisRunning
                ? `${analysisPhase === "queued" ? "대기 중" : "분석 중"}… ${analysisElapsedLabel}`
                : rangeTooLong
                  ? "기간을 다시 선택해 주세요"
                  : "분석 시작"}
            </button>
            {analysisRunning ? (
              <button
                type="button"
                onClick={stopAnalysis}
                disabled={analysisStopping}
                className="mt-2 inline-flex h-[44px] w-full items-center justify-center gap-2 rounded-[9px] bg-brand px-4 text-[14px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="text-[16px]">■</span>
                {analysisStopping ? "분석 중단 중…" : "분석 중단"}
              </button>
            ) : null}
            {analysisError ? <p className="mt-3 text-[12px] font-bold text-brand">{analysisError}</p> : null}
            {analysisMessage ? <p className="mt-3 text-[12px] font-bold text-muted">{analysisMessage}</p> : null}
          </div>
        </section>
      </div>

    </div>
  );
}
