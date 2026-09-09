"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { AnalyzeResponse } from "@/types/api";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { useSharedLeadTimes } from "@/lib/shared-lead-times";
import type { SharedAnalysisSettings, SharedAnalysisSettingsPatch } from "../lib/types";
import { DEFAULT_SHARED_ANALYSIS_SETTINGS } from "../lib/nav-config";
import { koreaDateString } from "../lib/workspace-format";

export function useWorkspaceAnalysisSession() {
  const { selectedEntity } = useAuthSession();
  const [orderAnalysisState, setOrderAnalysisState] = useState<{
    entityCode: string | null;
    result: AnalyzeResponse | null;
  }>(() => ({ entityCode: selectedEntity, result: null }));
  const [insightAnalysisState, setInsightAnalysisState] = useState<{
    entityCode: string | null;
    ready: boolean;
  }>(() => ({ entityCode: selectedEntity, ready: false }));
  const [safetyMonthsState, setSafetyMonthsState] = useState<{
    entityCode: string | null;
    value: string;
  }>(() => ({
    entityCode: selectedEntity,
    value: DEFAULT_SHARED_ANALYSIS_SETTINGS.safetyMonths
  }));
  const currentAnalysisResult = orderAnalysisState.entityCode === selectedEntity
    ? orderAnalysisState.result
    : null;
  const insightAnalysisReady = insightAnalysisState.entityCode === selectedEntity
    ? insightAnalysisState.ready
    : false;
  const safetyMonths = safetyMonthsState.entityCode === selectedEntity
    ? safetyMonthsState.value
    : DEFAULT_SHARED_ANALYSIS_SETTINGS.safetyMonths;
  const {
    methods: leadTimeMethods,
    values: leadTimeValues,
    loading: leadTimeLoading,
    error: leadTimeError,
    setLeadTime
  } = useSharedLeadTimes();
  const analysisSettings = useMemo<SharedAnalysisSettings>(() => ({
    safetyMonths,
    leadTimeMethods,
    leadTimeValues,
    leadTimeLoading,
    leadTimeError
  }), [leadTimeError, leadTimeLoading, leadTimeMethods, leadTimeValues, safetyMonths]);
  const analysisDate = useMemo(() => koreaDateString(), []);

  useEffect(() => {
    setOrderAnalysisState({ entityCode: selectedEntity, result: null });
    setInsightAnalysisState({ entityCode: selectedEntity, ready: false });
    setSafetyMonthsState({
      entityCode: selectedEntity,
      value: DEFAULT_SHARED_ANALYSIS_SETTINGS.safetyMonths
    });
  }, [selectedEntity]);

  const completeOrderAnalysis = useCallback((result: AnalyzeResponse) => {
    setOrderAnalysisState({ entityCode: selectedEntity, result });
  }, [selectedEntity]);

  const markInsightAnalysisReady = useCallback(() => {
    setInsightAnalysisState({ entityCode: selectedEntity, ready: true });
  }, [selectedEntity]);

  const invalidateInsightAnalysis = useCallback(() => {
    setInsightAnalysisState({ entityCode: selectedEntity, ready: false });
  }, [selectedEntity]);

  const updateAnalysisSettings = useCallback((patch: SharedAnalysisSettingsPatch) => {
    if (patch.safetyMonths !== undefined) {
      setSafetyMonthsState({ entityCode: selectedEntity, value: patch.safetyMonths });
    }
    for (const [transportCode, value] of Object.entries(patch.leadTimeValues ?? {})) {
      setLeadTime(transportCode, value);
    }
  }, [selectedEntity, setLeadTime]);

  return {
    analysisDate,
    analysisReady: Boolean(currentAnalysisResult),
    analysisSettings,
    completeOrderAnalysis,
    currentAnalysisResult,
    insightAnalysisReady,
    invalidateInsightAnalysis,
    markInsightAnalysisReady,
    updateAnalysisSettings
  };
}
