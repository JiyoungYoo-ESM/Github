"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";
import {
  buildSeasonCalendarRows,
  completeSeasonMonthKeys,
  daysUntilSeasonMonth,
  seasonPeakDistance,
  type SeasonCalendarRow,
  type SeasonMetricKind
} from "@/lib/season-calendar";
import { formatNumber } from "@/lib/utils";
import type { ReportBlock } from "../../lib/types";
import { analysisRangeMonthCount, reportAnalysisPeriodParams } from "../../lib/workspace-format";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { useUserPermissions } from "@/lib/use-user-permissions";

const monthLabels = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];
const EMPTY_SEASON_MONTH_COVERAGE: never[] = [];

export function useSeasonScreenModel({ reportBlocks }: { reportBlocks: ReportBlock[] }) {
  const { canViewAmountData } = useUserPermissions();
  const [focusedGroup, setFocusedGroup] = useState<string | null>(null);
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const analysisOptions = result?.analysisOptions ?? null;
  const seasonMonthCoverage = result?.seasonAnalysis.monthCoverage ?? EMPTY_SEASON_MONTH_COVERAGE;
  const completeMonthKeys = useMemo(() => completeSeasonMonthKeys(seasonMonthCoverage), [seasonMonthCoverage]);
  const metricKind: SeasonMetricKind = analysisOptions?.metric === "amount" ? "amount" : "qty";
  const category1Rows = useMemo(
    () => buildSeasonCalendarRows(result?.seasonAnalysis.category1Monthly ?? [], "기능1", metricKind, completeMonthKeys),
    [completeMonthKeys, metricKind, result?.seasonAnalysis.category1Monthly]
  );
  const category2Rows = useMemo(
    () => buildSeasonCalendarRows(result?.seasonAnalysis.category2Monthly ?? [], "기능2", metricKind, completeMonthKeys),
    [completeMonthKeys, metricKind, result?.seasonAnalysis.category2Monthly]
  );

  useEffect(() => {
    setFocusedGroup(null);
  }, [result]);

  const category2RowsByParent = useMemo(() => {
    const groups = new Map<string, SeasonCalendarRow[]>();
    category2Rows.forEach((row) => {
      const items = groups.get(row.parentGroup) ?? [];
      items.push(row);
      groups.set(row.parentGroup, items);
    });
    groups.forEach((items) => items.sort((a, b) => b.peakStrength - a.peakStrength));
    return groups;
  }, [category2Rows]);
  const visibleRows = useMemo(
    () =>
      category1Rows.flatMap((row) => {
        if (row.group !== focusedGroup) return [row];
        const children = category2RowsByParent.get(row.group) ?? [];
        return [row, ...children];
      }),
    [category1Rows, category2RowsByParent, focusedGroup]
  );
  const toggleFocusedGroup = (group: string) => {
    setFocusedGroup((current) => (current === group ? null : group));
  };
  const averageEurKrwRate =
    Number(analysisOptions?.average_eur_krw_rate) > 0 ? Number(analysisOptions?.average_eur_krw_rate) : null;
  const currentMonth = new Date().getMonth() + 1;
  // 분석 기간이 현재 달을 포함하지 않으면 기간 종료월을 기준으로 잡는다 (작년 동월 실적을 "현재월"로 표기하는 오류 방지)
  const seasonEndDateText = String(analysisOptions?.end_date ?? "");
  const seasonEndYear = Number(seasonEndDateText.slice(0, 4));
  const seasonEndMonth = Number(seasonEndDateText.slice(5, 7));
  const seasonEndValid = seasonEndYear > 0 && seasonEndMonth >= 1 && seasonEndMonth <= 12;
  const windowIncludesCurrentMonth = seasonEndValid
    ? seasonEndYear > new Date().getFullYear() || (seasonEndYear === new Date().getFullYear() && seasonEndMonth >= currentMonth)
    : true;
  const anchorMonth = windowIncludesCurrentMonth ? currentMonth : seasonEndMonth;
  // 기준월 실적이 없으면(진행 중인 달 등) 데이터가 있는 가장 최근 월로 폴백
  const monthHasSales = (month: number) => category1Rows.some((row) => (row.rawValues[month - 1] ?? 0) > 0);
  let referenceMonth = 0;
  for (let offset = 0; offset < 12; offset += 1) {
    const candidate = ((anchorMonth - 1 - offset + 12) % 12) + 1;
    if (monthHasSales(candidate)) {
      referenceMonth = candidate;
      break;
    }
  }
  const currentTopGroup = referenceMonth
    ? category1Rows
        .filter((row) => (row.rawValues[referenceMonth - 1] ?? 0) > 0)
        .sort((a, b) => (b.rawValues[referenceMonth - 1] ?? 0) - (a.rawValues[referenceMonth - 1] ?? 0))[0]
    : undefined;
  const currentTopRaw = currentTopGroup?.rawValues[referenceMonth - 1] ?? 0;
  const currentTopKrw =
    canViewAmountData && currentTopGroup?.metricKind === "amount" && currentTopRaw > 0 ? krwEokFromEur(currentTopRaw, averageEurKrwRate) : "";
  const currentTopMetricLabel =
    currentTopGroup && currentTopRaw > 0
      ? currentTopGroup.metricKind === "amount"
        ? canViewAmountData
          ? `${referenceMonth}월${currentTopGroup.metricAveraged ? " 평균" : ""} 매출 ${wonEok(currentTopRaw)}${currentTopKrw ? ` (${currentTopKrw})` : ""}`
          : `${referenceMonth}월 매출 비중 상위`
        : `${referenceMonth}월${currentTopGroup.metricAveraged ? " 평균" : ""} 판매 ${formatNumber(currentTopRaw, 0)}`
      : "";
  const peaksByDistance = [...category1Rows].sort(
    (a, b) => seasonPeakDistance(a.peakMonth, currentMonth) - seasonPeakDistance(b.peakMonth, currentMonth)
  );
  const upcomingPeak = peaksByDistance[0];
  const followingPeak = peaksByDistance.find((row) => row.peakMonth !== upcomingPeak?.peakMonth);
  const analyzedMonthCount = analysisRangeMonthCount(analysisOptions?.start_date, analysisOptions?.end_date);
  const completeMonthCount = completeSeasonMonthKeys(seasonMonthCoverage).size;
  const effectiveMonthCount = seasonMonthCoverage.length > 0 ? completeMonthCount : analyzedMonthCount;
  const seasonCalendarUnavailable = !loading && !loadFailed && effectiveMonthCount > 0 && effectiveMonthCount < 12;
  const excludedMonthCount = seasonMonthCoverage.filter((item) => item.status !== "complete").length;
  const seasonMetricLabel = analysisOptions?.metric === "amount" ? "판매금액" : "판매수량";
  const savedReportBlockIds = useMemo(() => new Set(reportBlocks.map((block) => block.id)), [reportBlocks]);
  const seasonCalendarBlock: ReportBlock = {
    id: "season:calendar:function-groups",
    title: "시즌 캘린더 — 기능군별 수요 지수",
    subtitle: `${formatNumber(category1Rows.length)}개 기능군 · 완료월 ${formatNumber(completeMonthCount)}개월 · ${seasonMetricLabel} 수요 지수(2~11)`,
    meta: "시즌 캘린더",
    type: "season_calendar",
    kind: "matrix",
    section: "season",
    size: "full",
    params: {
      rowLabel: "기능군",
      columnLabel: "월",
      metricLabel: `${seasonMetricLabel} 수요지수 (완료월 기준)`,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["기능군", "피크", "피크강도", "SKU수", ...monthLabels.map((month) => `${month}월`)],
      rows: category1Rows.map((row) => ({
        기능군: row.group,
        피크: row.peak,
        피크강도: row.peakStrength,
        SKU수: row.skuCount,
        ...Object.fromEntries(row.values.map((value, index) => [`${index + 1}월`, value]))
      }))
    }
  };
  const seasonBlockSaved = savedReportBlockIds.has(seasonCalendarBlock.id);
  const seasonBlockReady = !loading && !loadFailed && category1Rows.length > 0;

  return {
    monthLabels,
    category1Rows,
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
    seasonCalendarBlock,
    seasonBlockSaved,
    seasonBlockReady
  };
}
