"use client";

import { useEffect, useRef, useState } from "react";

import { useAuthSession } from "@/components/auth/AuthSessionContext";
import {
  analyzeSeasonTrendFromApi,
  cancelSeasonTrendAnalysis,
  clearSeasonTrendResult,
  isAbortError,
  saveSeasonTrendResult
} from "@/lib/api";
import type { Screen } from "../../lib/types";
import {
  addMonthsForDate,
  DEMAND_DATA_MIN_DATE,
  koreaDateString,
  MAX_DEMAND_DIRECT_RANGE_MONTHS,
  MAX_LONG_HISTORY_DIRECT_RANGE_MONTHS,
  seasonOptionsFromDates,
  todayKst
} from "../../lib/workspace-format";
import { automaticComparisonBasis, comparisonPeriodLabel } from "../../lib/yoy-comparison";

export const HQ_DEFAULT_WAREHOUSE = "OPO";

export const HQ_WAREHOUSE_OPTIONS = [
  { value: "", label: "전체 창고" },
  { value: "OPO", label: "오포창고 (OPO)" },
  { value: "BR-US", label: "BR-US" },
  { value: "SK-WH", label: "SK-WH" },
  { value: "BR-EU", label: "BR-EU" },
  { value: "KR-W", label: "KR-W" },
  { value: "SC-WH", label: "SC-WH" },
  { value: "BR-MY", label: "BR-MY" },
  { value: "BR-IN", label: "BR-IN" },
  { value: "BR-ME", label: "BR-ME" },
  { value: "BR-VT", label: "BR-VT" },
  { value: "MOIDA", label: "MOIDA" },
  { value: "MK-WH", label: "MK-WH" },
  { value: "HM", label: "HM" },
  { value: "BR-MX", label: "BR-MX" },
  { value: "Qoo10-WH", label: "Qoo10-WH" }
] as const;

function currentDayRange() {
  const today = koreaDateString();
  return { startDate: today, endDate: today };
}

export function useInsightInputScreenModel({
  onAnalysisComplete,
  onAnalysisInvalidated,
  onNavigate
}: {
  onAnalysisComplete: () => void;
  onAnalysisInvalidated: () => void;
  onNavigate: (screen: Screen) => void;
}) {
  const { selectedEntity } = useAuthSession();
  const hasLongHistoryApi = selectedEntity === "HQ" || selectedEntity === "USA";
  const currentYear = new Date().getFullYear();
  const [demandDates, setDemandDates] = useState(currentDayRange);
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisPhase, setAnalysisPhase] = useState<"queued" | "running">("running");
  const [analysisStopping, setAnalysisStopping] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [analysisMessage, setAnalysisMessage] = useState("");
  const analysisControllerRef = useRef<AbortController | null>(null);
  const analysisJobIdRef = useRef<string | null>(null);
  const cancellationRequestedRef = useRef(false);
  const [selectedWarehouse, setSelectedWarehouse] = useState(
    selectedEntity === "HQ" ? HQ_DEFAULT_WAREHOUSE : ""
  );

  useEffect(() => {
    setDemandDates(currentDayRange());
    setAnalysisError("");
    setAnalysisMessage("");
    setSelectedWarehouse(selectedEntity === "HQ" ? HQ_DEFAULT_WAREHOUSE : "");
  }, [currentYear, hasLongHistoryApi, selectedEntity]);

  const latestSyncText = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  })
    .format(new Date())
    .replace(/\.\s?/g, "-")
    .replace(/-$/, "");

  const maxDirectRangeMonths = hasLongHistoryApi
    ? MAX_LONG_HISTORY_DIRECT_RANGE_MONTHS
    : MAX_DEMAND_DIRECT_RANGE_MONTHS;
  const maxDemandEndDate = koreaDateString(
    addMonthsForDate(new Date(`${demandDates.startDate}T00:00:00`), maxDirectRangeMonths)
  );
  const rangeTooLong = demandDates.endDate > maxDemandEndDate;
  const rangeWarning = rangeTooLong
    ? hasLongHistoryApi
      ? `본사·미주 판매이력은 한 번에 최대 24개월까지 조회할 수 있습니다. 종료일은 ${maxDemandEndDate} 이내로 선택해 주세요.`
      : `직접 선택 분석 기간은 최대 24개월까지 가능합니다. 종료일은 ${maxDemandEndDate} 이내로 선택해 주세요.`
    : "";
  const comparisonBasis = automaticComparisonBasis(demandDates.startDate, demandDates.endDate);
  const comparisonPreviewLabel = comparisonPeriodLabel(comparisonBasis, [], demandDates.endDate);
  const updateDemandDates = (patch: Partial<{ startDate: string; endDate: string }>) => {
    setAnalysisError("");
    setAnalysisMessage("분석 기간이 변경되었습니다. 새 기간으로 다시 분석을 시작해 주세요.");
    clearSeasonTrendResult();
    onAnalysisInvalidated();
    setDemandDates((current) => ({ ...current, ...patch }));
  };
  const updateWarehouse = (warehouse: string) => {
    setAnalysisError("");
    setAnalysisMessage("분석 창고가 변경되었습니다. 선택한 창고로 다시 분석을 시작해 주세요.");
    clearSeasonTrendResult();
    onAnalysisInvalidated();
    setSelectedWarehouse(warehouse);
  };

  const cancelStartedAnalysis = async (jobId: string) => {
    try {
      await cancelSeasonTrendAnalysis(jobId);
      analysisControllerRef.current?.abort();
    } catch (caught) {
      cancellationRequestedRef.current = false;
      setAnalysisStopping(false);
      setAnalysisError(
        caught instanceof Error
          ? caught.message
          : "분석 작업을 중단하지 못했습니다. 다시 시도해 주세요."
      );
      setAnalysisMessage("분석은 계속 진행 중입니다.");
    }
  };

  const stopAnalysis = async () => {
    if (!analysisRunning || analysisStopping) return;
    cancellationRequestedRef.current = true;
    setAnalysisStopping(true);
    setAnalysisError("");
    setAnalysisMessage("분석을 중단하고 있습니다.");
    const jobId = analysisJobIdRef.current;
    if (jobId) {
      await cancelStartedAnalysis(jobId);
    }
  };

  const startAnalysis = async () => {
    if (analysisRunning) return;
    if (!demandDates.startDate || !demandDates.endDate) {
      setAnalysisError("분석 시작일과 종료일을 선택해 주세요.");
      return;
    }
    if (demandDates.startDate > demandDates.endDate) {
      setAnalysisError("분석 시작일은 종료일보다 늦을 수 없습니다.");
      return;
    }
    if (!hasLongHistoryApi && demandDates.startDate < DEMAND_DATA_MIN_DATE) {
      setAnalysisError(`분석 시작일은 ${DEMAND_DATA_MIN_DATE} 이후로 선택해 주세요.`);
      return;
    }
    if (demandDates.endDate > todayKst) {
      setAnalysisError("분석 종료일은 오늘 이후로 선택할 수 없습니다.");
      return;
    }
    if (rangeTooLong) {
      setAnalysisError(rangeWarning);
      return;
    }
    setAnalysisRunning(true);
    setAnalysisPhase("queued");
    setAnalysisStopping(false);
    setAnalysisError("");
    setAnalysisMessage("CMS 데이터를 조회하고 분석 중입니다.");
    cancellationRequestedRef.current = false;
    analysisJobIdRef.current = null;
    const controller = new AbortController();
    analysisControllerRef.current = controller;
    try {
      const requestOptions = {
        ...seasonOptionsFromDates(demandDates),
        warehouse: selectedEntity === "HQ" ? selectedWarehouse || null : null
      };
      const result = await analyzeSeasonTrendFromApi(requestOptions, {
        signal: controller.signal,
        onJobStarted: (jobId) => {
          analysisJobIdRef.current = jobId;
          if (cancellationRequestedRef.current) {
            void cancelStartedAnalysis(jobId);
          }
        },
        onStatusChange: (status) => {
          setAnalysisPhase(status);
          setAnalysisMessage(
            status === "queued"
              ? "분석 요청이 접수되었습니다. 앞선 작업이 있으면 순서대로 시작합니다."
              : "CMS 데이터를 조회하고 분석 중입니다."
          );
        }
      });
      if (cancellationRequestedRef.current) return;
      const resultWithComparison = {
        ...result,
        analysis_options: {
          ...result.analysis_options,
          comparison_basis: comparisonBasis
        }
      };
      await saveSeasonTrendResult(resultWithComparison);
      onAnalysisComplete();
      setAnalysisMessage("분석 완료. 국가 분석 화면으로 이동합니다.");
      onNavigate("country");
    } catch (caught) {
      if (cancellationRequestedRef.current || isAbortError(caught)) {
        setAnalysisError("");
        setAnalysisMessage("분석이 중단되었습니다. 입력값은 그대로 유지됩니다.");
        return;
      }
      const message = caught instanceof Error ? caught.message : "수요 분석 중 오류가 발생했습니다.";
      setAnalysisError(message.includes("Failed to fetch") ? "분석 서버와 연결되지 않았습니다. 백엔드 실행 상태를 확인해 주세요." : message);
      setAnalysisMessage("");
    } finally {
      analysisControllerRef.current = null;
      analysisJobIdRef.current = null;
      cancellationRequestedRef.current = false;
      setAnalysisRunning(false);
      setAnalysisStopping(false);
    }
  };

  return {
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
  };
}
