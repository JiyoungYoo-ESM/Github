"use client";

import { AlertCircle, Loader2, PlayCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AnalysisProgress } from "./AnalysisProgress";
import { AnalysisResultPanel } from "./AnalysisResultPanel";
import { AnalysisSettingsCard } from "./AnalysisSettingsCard";
import { useUploadWorkflow } from "./useUploadWorkflow";

export function UploadWorkflow() {
  const {
    safetyMonths,
    setSafetyMonths,
    leadTimeMethods,
    leadTimeValues,
    leadTimeLoading,
    leadTimeError,
    setLeadTime,
    error,
    result,
    exchangeRate,
    exchangeRateError,
    exchangeRateInput,
    setExchangeRateInput,
    loading,
    cmsAsOf,
    cmsLoading,
    handleCmsSubmit
  } = useUploadWorkflow();

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      <AnalysisSettingsCard
        cmsAsOf={cmsAsOf}
        exchangeRate={exchangeRate}
        exchangeRateError={exchangeRateError}
        exchangeRateInput={exchangeRateInput}
        onExchangeRateInputChange={setExchangeRateInput}
        safetyMonths={safetyMonths}
        onSafetyMonthsChange={setSafetyMonths}
        leadTimeMethods={leadTimeMethods}
        leadTimeValues={leadTimeValues}
        leadTimeLoading={leadTimeLoading}
        leadTimeError={leadTimeError}
        onLeadTimeChange={setLeadTime}
      />

      <div className="space-y-5">
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle>분석 실행</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm leading-6 text-slate-600">분석 시작을 눌러야 다른 탭에 반영됩니다.</p>

            <AnalysisProgress loading={cmsLoading} />

            <button
              type="button"
              onClick={() => void handleCmsSubmit()}
              disabled={cmsLoading || loading}
              className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-black px-5 text-sm font-semibold text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {cmsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {cmsLoading ? "분석 중입니다" : "분석 시작"}
            </button>

            {error ? (
              <div className="flex items-start gap-2 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-brand">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            {result ? <AnalysisResultPanel result={result} /> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
