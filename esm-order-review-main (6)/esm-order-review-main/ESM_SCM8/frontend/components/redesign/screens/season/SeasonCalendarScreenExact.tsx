"use client";

import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ReportBlock } from "../../lib/types";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { SeasonDemandCell, SeasonMetricCard } from "./SeasonScreenParts";
import { useSeasonScreenModel } from "./useSeasonScreenModel";
import { daysUntilSeasonMonth } from "@/lib/season-calendar";

export function SeasonCalendarScreenExact({
  reportBlocks
}: {
  reportBlocks: ReportBlock[];
}) {
  const {
    monthLabels,
    category2RowsByParent,
    visibleRows,
    focusedGroup,
    toggleFocusedGroup,
    setFocusedGroup,
    averageEurKrwRate,
    currentMonth,
    referenceMonth,
    currentTopGroup,
    currentTopMetricLabel,
    upcomingPeak,
    followingPeak,
    completeMonthCount,
    effectiveMonthCount,
    seasonCalendarUnavailable,
    excludedMonthCount,
    seasonMetricLabel,
    analysisOptions,
    loading,
    loadFailed,
    category1Rows
  } = useSeasonScreenModel({ reportBlocks });

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[18px]">
        <div className="flex items-center gap-[8px]">
          <h2 className="text-[18px] font-black leading-none text-ink">시즌 캘린더</h2>
        </div>
        <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
          기능군별 월별 수요 패턴과 피크월을 완료월의 {seasonMetricLabel} 기준으로 확인합니다.
        </p>
        <div className="mt-[12px]">
          <AnalysisPeriodBadge options={analysisOptions} />
          {effectiveMonthCount > 0 && effectiveMonthCount < 12 ? null : <AnalysisPeriodCaveat options={analysisOptions} />}
          {!loading && !loadFailed && excludedMonthCount > 0 ? (
            <span className="ml-[8px] text-[11px] font-bold text-muted2">
              부분·누락월 {excludedMonthCount}개월 제외 · 완료월 {completeMonthCount}개월 반영
            </span>
          ) : null}
        </div>
      </div>

      {seasonCalendarUnavailable ? (
        <section className="rounded-[14px] border border-dashed border-border bg-surface px-[20px] py-[46px] text-center shadow-soft">
          <p className="text-[16px] font-black text-ink">분석 조회 불가</p>
          <p className="mt-[10px] text-[13px] font-semibold text-muted2">
            시즌 캘린더는 완료된 판매월이 12개월 이상일 때 표시됩니다. 현재 완료월은 {completeMonthCount}개월입니다.
          </p>
        </section>
      ) : (
        <>
      {loading || loadFailed ? null : (
      <div className="mb-[18px] grid grid-cols-3 gap-[14px]">
        <SeasonMetricCard
          label={
            referenceMonth > 0 && referenceMonth !== currentMonth
              ? `최근월(${referenceMonth}월) 수요 상위 기능군`
              : `현재월(${currentMonth}월) 수요 상위 기능군`
          }
          value={currentTopGroup?.group ?? "-"}
          sub={
            currentTopGroup
              ? [
                  currentTopMetricLabel,
                  currentTopGroup.peakMonth === referenceMonth
                    ? referenceMonth === currentMonth
                      ? "지금이 피크월"
                      : `${referenceMonth}월이 피크월`
                    : `${currentTopGroup.peak} 피크 패턴`
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "월별 실적 데이터 없음"
          }
        />
        <SeasonMetricCard
          label="다가오는 피크"
          value={upcomingPeak ? `${upcomingPeak.peak} · ${upcomingPeak.group}` : "-"}
          sub={
            upcomingPeak
              ? `D-${daysUntilSeasonMonth(upcomingPeak.peakMonth)} · ${daysUntilSeasonMonth(upcomingPeak.peakMonth) <= 120 ? "지금 발주 권장" : "발주 시점 여유"}`
              : "분석 시작 후 표시"
          }
        />
        <SeasonMetricCard
          label="그 다음 피크"
          value={followingPeak ? `${followingPeak.peak} · ${followingPeak.group}` : "-"}
          sub={
            followingPeak
              ? `D-${daysUntilSeasonMonth(followingPeak.peakMonth)}${upcomingPeak ? ` · ${upcomingPeak.group} 피크 이후 준비` : ""}`
              : "추가 예정 피크 없음"
          }
        />
      </div>
      )}

      <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
        <div className="flex items-center justify-between border-b border-divider px-[20px] py-[17px]">
          <div className="flex items-center gap-[10px]">
            <h3 className="text-[15px] font-black text-ink">기능군 × 월별 수요 지수</h3>
            {focusedGroup ? (
              <button
                type="button"
                onClick={() => setFocusedGroup(null)}
                className="inline-flex h-[26px] items-center gap-[5px] rounded-full border border-brand/30 bg-brand-50 px-[10px] text-[11px] font-black text-brand transition hover:border-brand"
              >
                {focusedGroup} 하위 보기 중 · 전체 보기
              </button>
            ) : (
              <span className="text-[12px] font-semibold text-muted2">기능군을 클릭하면 하위 기능이 펼쳐집니다</span>
            )}
          </div>
          <div className="flex items-center gap-[10px] text-[12px] font-semibold text-muted2">
            <span>낮음</span>
            <span className="inline-flex h-[8px] w-[54px] overflow-hidden rounded-full">
              <span className="h-full flex-1 bg-brand/35" />
              <span className="h-full flex-1 bg-brand/60" />
              <span className="h-full flex-1 bg-brand/80" />
              <span className="h-full flex-1 bg-brand" />
            </span>
            <span>높음</span>
            <span className="ml-[6px] inline-flex h-[10px] w-[10px] rounded-[3px] border-2 border-ink bg-brand" />
            <span>피크월</span>
          </div>
        </div>

        <div className="grid grid-cols-[420px_1fr_220px] border-b border-divider bg-surface-soft text-[12px] font-black text-muted2">
          <div className="px-[16px] py-[11px]">기능군</div>
          <div className="grid grid-cols-12 gap-[8px] px-[10px] py-[11px] text-center">
            {monthLabels.map((month) => (
              <span key={month}>{month}</span>
            ))}
          </div>
          <div className="px-[16px] py-[11px] text-center">피크</div>
        </div>

        {loading ? (
          <div className="px-[20px] py-[34px] text-center text-[13px] font-semibold text-muted2">
            CMS 시즌 분석 결과를 불러오는 중입니다.
          </div>
        ) : loadFailed || category1Rows.length === 0 ? (
          <div className="px-[20px] py-[34px] text-center text-[13px] font-semibold text-muted2">
            시즌 캘린더에 표시할 CMS 분석 결과가 없습니다. 데이터 입력 탭에서 분석 시작을 실행해 주세요.
          </div>
        ) : (
          visibleRows.map((row) => {
            const children = category2RowsByParent.get(row.group) ?? [];
            const isCategory1 = row.level === "기능1";
            const expandable = isCategory1 && children.length > 0;
            const focused = isCategory1 && row.group === focusedGroup;
            const dimmed = isCategory1 && focusedGroup !== null && !focused;
            const rowPeakRaw = Math.max(...row.rawValues, 0);
            return (
              <div
                key={`${row.level}-${row.parentGroup}-${row.group}`}
                onClick={expandable ? () => toggleFocusedGroup(row.group) : undefined}
                className={cn(
                  "grid min-h-[41px] grid-cols-[420px_1fr_220px] items-center border-b border-rowline transition last:border-b-0",
                  row.level === "기능2" && "bg-surface-soft/70",
                  focused && "bg-brand-50/60",
                  expandable && "cursor-pointer",
                  expandable && !focused && !dimmed && "hover:bg-surface-soft",
                  dimmed && "opacity-45 grayscale hover:opacity-100 hover:grayscale-0 focus-within:opacity-100 focus-within:grayscale-0"
                )}
              >
                <div
                  className={cn(
                    "flex items-center gap-[8px] px-[16px] text-[13px] font-black text-ink",
                    row.level === "기능2" && "pl-[54px] text-[12px] font-bold text-ink3"
                  )}
                >
                  {expandable ? (
                    <button
                      type="button"
                      aria-expanded={focused}
                      aria-label={`${row.group} 하위 기능 ${focused ? "접기" : "펼치기"}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleFocusedGroup(row.group);
                      }}
                      className={cn(
                        "grid h-[24px] w-[24px] place-items-center rounded-[6px] border bg-surface transition hover:border-brand hover:text-brand focus-visible:ring-2 focus-visible:ring-brand/40",
                        focused ? "border-brand text-brand" : "border-border text-muted2"
                      )}
                    >
                      <ChevronDown className={cn("h-4 w-4 transition", !focused && "-rotate-90")} />
                    </button>
                  ) : (
                    <span className="h-[24px] w-[24px]" />
                  )}
                  <span
                    className={cn(
                      "rounded-[6px] border border-border px-[7px] py-[3px] text-[11px] font-black",
                      row.level === "기능1"
                        ? "bg-surface-soft text-muted2"
                        : "border-brand/20 bg-brand-50 text-brand"
                    )}
                  >
                    {row.level === "기능1" ? "기능1" : "하위"}
                  </span>
                  {row.level === "기능2" ? <span className="h-[1px] w-[16px] bg-border" /> : null}
                  <span>{row.group}</span>
                  {expandable ? <span className="text-[11px] font-bold text-muted2">{children.length}개</span> : null}
                </div>
                <div className="grid grid-cols-12 gap-[8px] px-[10px] py-[4px]">
                  {row.values.map((value, index) => (
                    <SeasonDemandCell
                      key={`${row.group}-${index}`}
                      value={value}
                      raw={row.rawValues[index] ?? 0}
                      peakRaw={rowPeakRaw}
                      month={index + 1}
                      metricKind={row.metricKind}
                      averaged={row.metricAveraged}
                      eurKrwRate={averageEurKrwRate}
                      peak={`${index + 1}월` === row.peak}
                    />
                  ))}
                </div>
                <div className="px-[16px] text-center text-[13px] font-black text-ink">{row.peak}</div>
              </div>
            );
          })
        )}
      </section>
        </>
      )}
    </div>
  );
}
