"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarRange, Database, Loader2, RotateCw, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { analyzeSeasonTrendFromApi } from "@/lib/api";
import { readSeasonAnalysisDraft, writeSeasonAnalysisDraft } from "@/lib/storage/repositories/season-analysis-draft";
import { useUserPermissions } from "@/lib/use-user-permissions";
import type { SeasonTrendAnalyzeResponse } from "@/types/api";

type Metric = "qty" | "amount";
type GroupBy = "month" | "quarter" | "year";

type SeasonTrendUploadPanelProps = {
  onAnalyzed: (result: SeasonTrendAnalyzeResponse) => void;
  activeSection?: "global";
  defaultSettingsOpen?: boolean;
};

type AnalysisDraft = {
  startDate: string;
  endDate: string;
  metric: Metric;
  groupBy: GroupBy;
};

// CMS /eu/sales/local(현지판매) 실데이터는 2024-04-11부터 존재한다(CMS팀 확인).
const DATA_MIN_DATE = "2024-04-01";
const MAX_DIRECT_RANGE_MONTHS = 24;
const MIN_SEASON_RANGE_MONTHS = 12;

function dateValue(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parseDateValue(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function addMonths(date: Date, months: number) {
  const next = new Date(date);
  const day = next.getDate();
  next.setDate(1);
  next.setMonth(next.getMonth() + months);
  next.setDate(Math.min(day, new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate()));
  return next;
}

function clampStartDate(value: string) {
  return value < DATA_MIN_DATE ? DATA_MIN_DATE : value;
}

function completeRecentMonthRange(months: number) {
  const today = new Date();
  const end = new Date(today.getFullYear(), today.getMonth(), 0);
  const start = new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
  return {
    startDate: clampStartDate(dateValue(start)),
    endDate: dateValue(end)
  };
}

function yearRange(year: number) {
  const today = new Date();
  const end = year === today.getFullYear() ? today : new Date(year, 11, 31);
  return {
    startDate: clampStartDate(`${year}-01-01`),
    endDate: dateValue(end)
  };
}

function maxRangeEnd(startDate: string) {
  const start = parseDateValue(startDate);
  if (!start) return "";
  return dateValue(addMonths(start, MAX_DIRECT_RANGE_MONTHS));
}

function isRangeTooLong(startDate: string, endDate: string) {
  const end = parseDateValue(endDate);
  const maxEnd = parseDateValue(maxRangeEnd(startDate));
  return Boolean(end && maxEnd && end > maxEnd);
}

const defaultDraft = (): AnalysisDraft => ({
  ...completeRecentMonthRange(MIN_SEASON_RANGE_MONTHS),
  metric: "qty",
  groupBy: "month"
});

function readAnalysisDraft(): AnalysisDraft {
  return readSeasonAnalysisDraft(defaultDraft);
}

function writeAnalysisDraft(patch: Partial<AnalysisDraft>) {
  const next = { ...readAnalysisDraft(), ...patch };
  writeSeasonAnalysisDraft(next);
}

function seasonResultRowCount(result: SeasonTrendAnalyzeResponse) {
  const season = result.season_analysis;
  const ingredient = result.ingredient_analysis;
  return (
    (season.countryCategoryMonthly?.length ?? 0) +
    (season.countryCategory2Monthly?.length ?? 0) +
    (season.countryTopSku?.length ?? 0) +
    (season.countrySkuMonthly?.length ?? 0) +
    (ingredient.countrySummary?.length ?? 0) +
    (ingredient.summary?.length ?? 0)
  );
}

export function SeasonTrendUploadPanel({
  onAnalyzed,
  activeSection = "global",
  defaultSettingsOpen = activeSection === "global"
}: SeasonTrendUploadPanelProps) {
  const { canViewAmountData } = useUserPermissions();
  const [settingsOpen, setSettingsOpen] = useState(defaultSettingsOpen);
  const [initialDraft] = useState(readAnalysisDraft);
  const [startDate, setStartDateState] = useState(() => initialDraft.startDate);
  const [endDate, setEndDateState] = useState(() => initialDraft.endDate);
  const [metric, setMetricState] = useState<Metric>(() => canViewAmountData ? initialDraft.metric : "qty");
  const [groupBy, setGroupByState] = useState<GroupBy>(() => initialDraft.groupBy);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisStatus, setAnalysisStatus] = useState("");
  const [error, setError] = useState("");

  const setStartDate = (value: string) => {
    writeAnalysisDraft({ startDate: value });
    setStartDateState(value);
  };
  const setEndDate = (value: string) => {
    writeAnalysisDraft({ endDate: value });
    setEndDateState(value);
  };
  const setMetric = (value: Metric) => {
    writeAnalysisDraft({ metric: value });
    setMetricState(value);
  };

  useEffect(() => {
    if (canViewAmountData || metric !== "amount") return;
    writeAnalysisDraft({ metric: "qty" });
    setMetricState("qty");
  }, [canViewAmountData, metric]);
  const setGroupBy = (value: GroupBy) => {
    writeAnalysisDraft({ groupBy: value });
    setGroupByState(value);
  };
  const setDateRange = (range: { startDate: string; endDate: string }) => {
    writeAnalysisDraft(range);
    setStartDateState(range.startDate);
    setEndDateState(range.endDate);
  };

  const periodLabel = useMemo(() => `${startDate || "-"} ~ ${endDate || "-"}`, [endDate, startDate]);
  const todayValue = dateValue(new Date());
  const currentYear = new Date().getFullYear();
  const quickRanges = [
    { label: "최근 12개월", range: completeRecentMonthRange(MIN_SEASON_RANGE_MONTHS) },
    { label: `${currentYear - 1}년`, range: yearRange(currentYear - 1) },
    { label: `${currentYear - 2}년`, range: yearRange(currentYear - 2) }
  ];
  const rangeTooLong = isRangeTooLong(startDate, endDate);
  const metricLabel = metric === "qty" ? "판매수량" : "판매금액";
  const groupByLabel = groupBy === "month" ? "월별" : groupBy === "quarter" ? "분기별" : "연도별";

  const handleAnalyze = async () => {
    setAnalysisStatus("CMS API 원천 데이터를 조회하고 있습니다.");
    if (!startDate || !endDate) {
      setError("분석 시작일과 종료일을 선택해 주세요.");
      setAnalysisStatus("");
      return;
    }
    if (startDate > endDate) {
      setError("분석 시작일은 종료일보다 늦을 수 없습니다.");
      setAnalysisStatus("");
      return;
    }
    if (startDate < DATA_MIN_DATE) {
      setError(`CMS 판매이력은 ${DATA_MIN_DATE} 이후부터 분석할 수 있습니다.`);
      setAnalysisStatus("");
      return;
    }
    if (endDate > todayValue) {
      setError("분석 종료일은 오늘 이후로 선택할 수 없습니다.");
      setAnalysisStatus("");
      return;
    }
    if (rangeTooLong) {
      setError("직접 선택 분석 기간은 최대 24개월까지 가능합니다.");
      setAnalysisStatus("");
      return;
    }
    setIsAnalyzing(true);
    setError("");
    try {
      const result = await analyzeSeasonTrendFromApi({
        startDate,
        endDate,
        metric,
        groupBy,
        includeIngredient: true
      });
      setAnalysisStatus("분석 결과를 화면에 반영하고 있습니다.");
      onAnalyzed(result);
      setAnalysisStatus(`분석 완료. ${seasonResultRowCount(result).toLocaleString()}개 결과 행이 아래 수요 분석 화면에 반영되었습니다.`);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "";
      setAnalysisStatus("");
      setError(
        message.includes("Failed to fetch")
          ? "분석 서버에 연결할 수 없습니다. 백엔드 실행 상태를 확인해 주세요."
          : message || "수요 분석 중 오류가 발생했습니다."
      );
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-950">데이터 입력</h2>
          <p className="mt-1 text-sm text-slate-600">
            CMS API의 장기 판매이력과 상품목록을 조회해 국가/권역별 시즌 수요와 성분 트렌드를 분석합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" onClick={() => setSettingsOpen((value) => !value)}>
            <SlidersHorizontal className="h-4 w-4" />
            {settingsOpen ? "기준값 접기" : "기준값 수정"}
          </Button>
          <Button type="button" onClick={handleAnalyze} disabled={isAnalyzing}>
            {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
            {isAnalyzing ? "분석 중입니다" : "분석 시작"}
          </Button>
        </div>
      </div>

      {settingsOpen ? (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid gap-4 xl:grid-cols-[1fr_1.3fr]">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <Database className="h-4 w-4" />
                CMS API 원천 데이터
              </div>
              <p className="mt-2 text-xs font-semibold leading-5 text-slate-500">
                장기 판매이력은 <span className="text-slate-800">/api/v1/eu/sales/local</span>, 상품목록은{" "}
                <span className="text-slate-800">/api/v1/eu/products</span>에서 자동 조회합니다.
              </p>
              <div className="mt-4 grid gap-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                  <p className="text-sm font-bold text-slate-900">장기 판매이력</p>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    {canViewAmountData ? "출고일, 국가, 상품, 브랜드, 판매수량, 판매금액" : "출고일, 국가, 상품, 브랜드, 판매수량"}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                  <p className="text-sm font-bold text-slate-900">상품목록</p>
                  <p className="mt-1 text-xs font-semibold text-slate-500">상품코드, 상품명, 브랜드, 기능구분1/2</p>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
                <CalendarRange className="h-4 w-4" />
                분석 조건
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {quickRanges.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => setDateRange(item.range)}
                    className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 transition hover:border-slate-950 hover:text-slate-950"
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <label className="block">
                  <span className="text-sm font-bold text-slate-900">분석 시작일</span>
                  <input
                    type="date"
                    value={startDate}
                    min={DATA_MIN_DATE}
                    max={todayValue}
                    onChange={(event) => setStartDate(event.target.value)}
                    className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-bold text-slate-900">분석 종료일</span>
                  <input
                    type="date"
                    value={endDate}
                    min={DATA_MIN_DATE}
                    max={todayValue}
                    onChange={(event) => setEndDate(event.target.value)}
                    className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-bold text-slate-900">분석 기준</span>
                  <select
                    value={metric}
                    onChange={(event) => setMetric(event.target.value as Metric)}
                    className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                  >
                    <option value="qty">판매수량</option>
                    {canViewAmountData ? <option value="amount">판매금액</option> : null}
                  </select>
                </label>
                <label className="block">
                  <span className="text-sm font-bold text-slate-900">분석 단위</span>
                  <select
                    value={groupBy}
                    onChange={(event) => setGroupBy(event.target.value as GroupBy)}
                    className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                  >
                    <option value="month">월별</option>
                    <option value="quarter">분기별</option>
                    <option value="year">연도별</option>
                  </select>
                </label>
              </div>

              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
                선택 기간: {periodLabel}
              </div>
              <p
                className={
                  rangeTooLong ? "mt-2 text-xs font-semibold text-red-600" : "mt-2 text-xs font-semibold text-slate-500"
                }
              >
                시즌 캘린더는 1년 미만 기간에서는 조회 불가로 표시되며, 직접 선택 분석 기간은 최대 24개월까지 가능합니다.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {analysisStatus ? (
        <div className={`mt-4 rounded-lg border px-4 py-3 text-sm font-semibold ${
          isAnalyzing ? "border-blue-100 bg-blue-50 text-blue-800" : "border-emerald-100 bg-emerald-50 text-emerald-800"
        }`}>
          <div className="flex items-center gap-2">
            {isAnalyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            <span>{analysisStatus}</span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          {error}
        </div>
      ) : null}
    </section>
  );
}
