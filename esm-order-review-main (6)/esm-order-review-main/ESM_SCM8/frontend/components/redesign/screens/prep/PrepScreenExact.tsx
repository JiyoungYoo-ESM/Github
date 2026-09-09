"use client";

import type { AnalyzeResponse } from "@/types/api";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import type {
  Screen,
  SharedAnalysisRuntime,
  SharedAnalysisSettings,
  SharedAnalysisSettingsPatch
} from "../../lib/types";
import { useAnalysisElapsedLabel } from "../../shared/use-analysis-elapsed";
import { FieldBox } from "./PrepScreenParts";
import { usePrepScreenModel } from "./usePrepScreenModel";

export function PrepScreenExact({
  onAnalysisComplete,
  onNavigate,
  analysisSettings,
  onAnalysisSettingsChange,
  analysisDate
}: {
  onAnalysisComplete: (result: AnalyzeResponse) => void;
  onNavigate: (screen: Screen) => void;
  analysisSettings: SharedAnalysisSettings;
  onAnalysisSettingsChange: (patch: SharedAnalysisSettingsPatch) => void;
} & Pick<SharedAnalysisRuntime, "analysisDate">) {
  const { selectedEntity } = useAuthSession();
  const {
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
  } = usePrepScreenModel({ onAnalysisComplete, onNavigate, analysisSettings, analysisDate });
  const analysisElapsedLabel = useAnalysisElapsedLabel(analysisRunning);

  if (selectedEntity === "HQ") {
    return (
      <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
        <div className="rounded-[16px] border border-border bg-surface p-[22px] shadow-soft">
          <h2 className="text-[17px] font-black text-ink">본사 발주 분석은 제공하지 않습니다</h2>
          <p className="mt-3 text-[13px] font-semibold leading-6 text-muted">
            본사는 전체 판매이력과 상품마스터를 이용한 분석 탭만 연동되어 있습니다.
            왼쪽 분석 메뉴의 데이터 입력에서 기간을 선택하고 분석을 시작해 주세요.
          </p>
          <button
            type="button"
            onClick={() => onNavigate("idata")}
            className="mt-5 h-10 rounded-[10px] bg-sidebar px-5 text-[13px] font-black text-white"
          >
            분석 데이터 입력으로 이동
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px]">
        <div className="flex items-center gap-2">
          <h2 className="text-[17px] font-black leading-none text-ink">데이터 입력</h2>
        </div>
        <p className="mt-[10px] text-[13px] font-semibold leading-none text-muted">
          판매·재고·미입고·운송중 데이터는 API로 자동 연동됩니다. 엑셀 업로드 없이 분석 기준값만 확인하고 분석을 시작하세요.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="rounded-[16px] border border-border bg-surface p-[22px] shadow-soft">
          <h3 className="text-[15px] font-black text-ink">분석 기준값</h3>
          <p className="mt-1 text-[12.5px] font-semibold text-muted">발주 수량과 운송 검토에 사용할 기준값입니다.</p>

          <div className="mt-5 max-w-[460px]">
            <FieldBox label="분석 기준일" value={analysisDate} />
          </div>

          <div className="my-5 h-px bg-divider" />

          <h3 className="text-[15px] font-black text-ink">재고 목표</h3>
          <p className="mt-1 text-[12.5px] font-semibold text-muted">월평균 판매량 대비 유지할 목표 재고 개월수를 입력합니다.</p>
          <div className="mt-5 max-w-[260px]">
            <FieldBox label="안전재고 개월수" value={safetyMonths} caption="입력한 개월수가 발주 필요수량 계산에 적용됩니다." onChange={(value) => onAnalysisSettingsChange({ safetyMonths: value })} step={0.1} min={0.1} />
          </div>

          <div className="my-5 h-px bg-divider" />

          <h3 className="text-[15px] font-black text-ink">운송 리드타임</h3>
          <p className="mt-1 text-[12.5px] font-semibold text-muted">
            선택한 법인이 지원하는 운송수단의 기본값입니다. 입력값은 계정과 법인별로 분리해 저장됩니다.
          </p>
          {leadTimeLoading ? (
            <p className="mt-5 text-[12.5px] font-semibold text-muted">법인별 운송 리드타임을 불러오는 중입니다.</p>
          ) : leadTimeError ? (
            <p className="mt-5 rounded-[10px] border border-brand/20 bg-brand-50 p-3 text-[12.5px] font-black text-brand">
              {leadTimeError}
            </p>
          ) : leadTimeMethods.length === 0 ? (
            <p className="mt-5 rounded-[10px] border border-border bg-surface-soft p-3 text-[12.5px] font-semibold text-muted">
              본사는 해외 운송 리드타임을 적용하지 않습니다.
            </p>
          ) : (
            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {leadTimeMethods.map((method) => (
                <FieldBox
                  key={method.code}
                  label={`${method.label} L/T(일)`}
                  value={leadTimeValues[method.code] ?? ""}
                  caption={`법인 기본값 ${method.lead_time_days}일`}
                  onChange={(value) => onAnalysisSettingsChange({
                    leadTimeValues: { [method.code]: value }
                  })}
                  min={1}
                />
              ))}
            </div>
          )}
        </div>

        <aside className="h-fit rounded-[16px] border border-border bg-surface p-[22px] shadow-soft">
          <h3 className="text-[15px] font-black text-ink">분석 실행</h3>
          <p className="mt-2 text-[12.5px] font-semibold leading-5 text-muted">
            분석 시작을 눌러야 기준값이 다른 탭에 반영됩니다.
          </p>
          {analysisError ? (
            <div className="mt-5 rounded-[10px] border border-brand/20 bg-brand-50 p-4">
              <p className="text-[12.5px] font-black leading-5 text-brand">{analysisError}</p>
            </div>
          ) : null}
          {/* 시작/중단을 한 버튼에 겹치면 연타가 방금 시작한 분석을 취소한다. */}
          <button
            type="button"
            onClick={startAnalysis}
            disabled={analysisRunning || analysisStopping}
            className="mt-[14px] h-11 w-full rounded-[10px] bg-sidebar text-[14px] font-black text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-60"
          >
            {analysisRunning ? `분석 중… ${analysisElapsedLabel}` : "▶ 분석 시작"}
          </button>
          {analysisRunning ? (
            <button
              type="button"
              onClick={stopAnalysis}
              disabled={analysisStopping}
              className="mt-2 h-11 w-full rounded-[10px] bg-brand text-[14px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {analysisStopping ? "■ 분석 중단 중…" : "■ 분석 중단"}
            </button>
          ) : null}
          {analysisMessage ? (
            <p className="mt-3 text-[12px] font-bold text-muted">{analysisMessage}</p>
          ) : null}
          <p className="mt-4 text-[11.5px] font-semibold text-muted2">
            {analysisSyncText} · {analysisDate}
          </p>
        </aside>
      </div>
    </div>
  );
}
