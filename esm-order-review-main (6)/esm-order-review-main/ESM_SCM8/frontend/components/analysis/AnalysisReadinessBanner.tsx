"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import {
  ANALYSIS_RESULT_CHANGED_EVENT,
  getCurrentAnalysisJobId,
  getStoredAnalysisResultAsync,
  getStoredSeasonTrendResult,
  hasCurrentSeasonTrendResult
} from "@/lib/api/storage";
import { cn, formatNumber } from "@/lib/utils";
import type { AnalyzeResponse, SeasonTrendAnalyzeResponse } from "@/types/api";

type ReadinessState = {
  analysis: AnalyzeResponse | null;
  season: SeasonTrendAnalyzeResponse | null;
};

function StatusChip({
  ok,
  label,
  detail
}: {
  ok: boolean;
  label: string;
  detail: string;
}) {
  const Icon = ok ? CheckCircle2 : AlertCircle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold",
        ok ? "border-emerald-100 bg-emerald-50 text-emerald-700" : "border-orange-100 bg-orange-50 text-orange-700"
      )}
      title={detail}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </span>
  );
}

export function AnalysisReadinessBanner() {
  const [state, setState] = useState<ReadinessState>({ analysis: null, season: null });

  const refreshState = useCallback((isActive: () => boolean) => {
    Promise.all([getStoredAnalysisResultAsync(), getStoredSeasonTrendResult()])
      .then(([analysis, season]) => {
        if (isActive()) setState({ analysis, season });
      })
      .catch(() => {
        if (isActive()) setState({ analysis: null, season: null });
      });
  }, []);

  useEffect(() => {
    let active = true;
    const isActive = () => active;
    const handleAnalysisResultChanged = () => refreshState(isActive);

    refreshState(isActive);
    window.addEventListener(ANALYSIS_RESULT_CHANGED_EVENT, handleAnalysisResultChanged);

    return () => {
      active = false;
      window.removeEventListener(ANALYSIS_RESULT_CHANGED_EVENT, handleAnalysisResultChanged);
    };
  }, [refreshState]);

  const summary = useMemo(() => {
    const currentAnalysisJobId = getCurrentAnalysisJobId();
    const hasAnalysis = Boolean(state.analysis?.job_id && currentAnalysisJobId && state.analysis.job_id === currentAnalysisJobId);
    const hasCurrentSeason = hasCurrentSeasonTrendResult();
    const seasonUploadedRoles = new Set(state.season?.uploaded_files?.map((file) => file.role) ?? []);
    const mappingRows = state.season?.season_analysis?.uncategorizedSku ?? [];
    const hasSeasonFiles = hasCurrentSeason && seasonUploadedRoles.has("sales_history") && seasonUploadedRoles.has("prod_list");

    return {
      hasAnalysis,
      hasSeasonFiles,
      readyForIntegratedOrder: hasAnalysis && hasSeasonFiles,
      mappingOk: hasSeasonFiles && mappingRows.length === 0,
      missingMappingCount: mappingRows.length
    };
  }, [state]);

  const mappingLabel = summary.mappingOk ? "매핑 정상" : `미분류 ${formatNumber(summary.missingMappingCount)}건`;
  const readinessTitle = summary.readyForIntegratedOrder ? "최종 발주 데이터 산출 가능" : "최종 발주 데이터 산출 전 준비 필요";
  const readinessDetail = summary.readyForIntegratedOrder
    ? "발주 분석과 시즌 분석이 모두 완료되어 통합 발주에서 최종 수량과 발주 시점을 판단할 수 있습니다."
    : "최종 발주 데이터는 발주 분석 결과와 시즌 수요 분석이 모두 완료되어야 산출됩니다.";
  return (
    <section className="mb-5 rounded-2xl border border-line bg-white px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip
              ok={summary.hasAnalysis}
              label={summary.hasAnalysis ? "발주 분석 완료" : "발주 분석 필요"}
              detail={summary.hasAnalysis ? "저장된 발주 분석 결과가 있습니다." : "데이터 준비에서 발주 분석을 먼저 실행해야 합니다."}
            />
            <StatusChip
              ok={summary.hasSeasonFiles}
              label={summary.hasSeasonFiles ? "시즌 분석 완료" : "시즌 분석 필요"}
              detail={
                summary.hasSeasonFiles
                  ? "시즌 분석에 필요한 장기 판매이력과 상품 리스트가 연결되었습니다."
                  : "시즌 분석에서 장기 판매이력과 상품 리스트를 업로드한 뒤 분석해야 합니다."
              }
            />
            {summary.hasSeasonFiles ? <StatusChip ok={summary.mappingOk} label={mappingLabel} detail="성분/카테고리 매핑 상태입니다." /> : null}
          </div>
          <p className="mt-2 text-sm font-black text-ink">{readinessTitle}</p>
          <p className="mt-0.5 text-xs font-semibold text-slate-500">{readinessDetail}</p>
        </div>
      </div>
    </section>
  );
}
