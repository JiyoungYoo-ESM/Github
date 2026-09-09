"use client";

import { useRef, useState } from "react";

import {
  analyzeFromCms,
  cancelCmsAnalysis,
  clearLastAnalysisResult,
  isAbortError,
  saveLastAnalysisResult,
  type AnalyzeOptions
} from "@/lib/api";
import { buildLeadTimeOverrides } from "@/lib/lead-times";
import type { AnalyzeResponse } from "@/types/api";
import type { Screen, SharedAnalysisRuntime, SharedAnalysisSettings } from "../../lib/types";

export function usePrepScreenModel({
  onAnalysisComplete,
  onNavigate,
  analysisSettings,
  analysisDate
}: {
  onAnalysisComplete: (result: AnalyzeResponse) => void;
  onNavigate: (screen: Screen) => void;
  analysisSettings: SharedAnalysisSettings;
} & Pick<SharedAnalysisRuntime, "analysisDate">) {
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisStopping, setAnalysisStopping] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [analysisMessage, setAnalysisMessage] = useState("");
  const analysisControllerRef = useRef<AbortController | null>(null);
  const analysisJobIdRef = useRef<string | null>(null);
  const cancellationRequestedRef = useRef(false);
  const {
    safetyMonths,
    leadTimeMethods,
    leadTimeValues,
    leadTimeLoading,
    leadTimeError
  } = analysisSettings;

  const analysisSyncText = analysisError
    ? "마지막 확인 실패"
    : analysisStopping
      ? "분석 중단 중"
    : analysisRunning
      ? "CMS API 조회 중"
      : "분석 시작 대기";

  const cancelStartedAnalysis = async (jobId: string) => {
    try {
      await cancelCmsAnalysis(jobId);
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
    const safetyMonthsValue = Number(safetyMonths);
    const valuesAreValid = Number.isFinite(safetyMonthsValue) && safetyMonthsValue > 0;

    if (!valuesAreValid) {
      setAnalysisError("안전재고 개월수는 0보다 큰 숫자로 입력해 주세요.");
      return;
    }
    if (leadTimeLoading) {
      setAnalysisError("선택한 법인의 운송 리드타임을 불러오는 중입니다.");
      return;
    }
    if (leadTimeError) {
      setAnalysisError(leadTimeError);
      return;
    }

    let leadTimeOverrides: AnalyzeOptions["leadTimeOverrides"];
    try {
      leadTimeOverrides = buildLeadTimeOverrides(leadTimeMethods, leadTimeValues);
    } catch (caught) {
      setAnalysisError(caught instanceof Error ? caught.message : "운송 리드타임을 확인해 주세요.");
      return;
    }
    const options: AnalyzeOptions = {
      safetyMonths: safetyMonthsValue,
      leadTimeOverrides
    };

    setAnalysisRunning(true);
    setAnalysisStopping(false);
    setAnalysisError("");
    setAnalysisMessage("");
    cancellationRequestedRef.current = false;
    analysisJobIdRef.current = null;
    const controller = new AbortController();
    analysisControllerRef.current = controller;
    try {
      const result = await analyzeFromCms(analysisDate, options, {
        signal: controller.signal,
        onJobStarted: (jobId) => {
          analysisJobIdRef.current = jobId;
          if (cancellationRequestedRef.current) {
            void cancelStartedAnalysis(jobId);
          }
        }
      });
      if (cancellationRequestedRef.current) return;
      clearLastAnalysisResult();
      await saveLastAnalysisResult(result, { markExecuted: true });
      onAnalysisComplete(result);
      onNavigate("order");
    } catch (caught) {
      if (cancellationRequestedRef.current || isAbortError(caught)) {
        setAnalysisError("");
        setAnalysisMessage("분석이 중단되었습니다. 입력값은 그대로 유지됩니다.");
        return;
      }
      const message = caught instanceof Error ? caught.message : "CMS 분석 요청 중 오류가 발생했습니다.";
      setAnalysisError(message.includes("Failed to fetch") ? "분석 서버와 연결되지 않았습니다. 잠시 후 다시 시도해주세요." : message);
    } finally {
      analysisControllerRef.current = null;
      analysisJobIdRef.current = null;
      cancellationRequestedRef.current = false;
      setAnalysisRunning(false);
      setAnalysisStopping(false);
    }
  };

  return {
    analysisRunning,
    analysisStopping,
    analysisError,
    analysisMessage,
    safetyMonths,
    leadTimeMethods,
    leadTimeValues,
    leadTimeLoading,
    leadTimeError,
    analysisSyncText,
    startAnalysis,
    stopAnalysis
  };
}
