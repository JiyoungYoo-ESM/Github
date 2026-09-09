"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { LeadTimeInputValues, LeadTimeMethod } from "@/lib/lead-times";
import type { ExchangeRateResponse } from "@/types/api";
import { ExchangeRateField } from "./ExchangeRateField";

type AnalysisSettingsCardProps = {
  cmsAsOf: string;
  exchangeRate: ExchangeRateResponse | null;
  exchangeRateError: string;
  exchangeRateInput: string;
  onExchangeRateInputChange: (value: string) => void;
  safetyMonths: string;
  onSafetyMonthsChange: (value: string) => void;
  leadTimeMethods: LeadTimeMethod[];
  leadTimeValues: LeadTimeInputValues;
  leadTimeLoading: boolean;
  leadTimeError: string;
  onLeadTimeChange: (transportCode: string, value: string) => void;
};

export function AnalysisSettingsCard({
  cmsAsOf,
  exchangeRate,
  exchangeRateError,
  exchangeRateInput,
  onExchangeRateInputChange,
  safetyMonths,
  onSafetyMonthsChange,
  leadTimeMethods,
  leadTimeValues,
  leadTimeLoading,
  leadTimeError,
  onLeadTimeChange
}: AnalysisSettingsCardProps) {
  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>분석 기준값</CardTitle>
        <CardDescription>발주 수량과 운송 검토에 사용할 기준값입니다.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <section className="grid gap-4 lg:grid-cols-[240px_1fr]">
          <label>
            <span className="text-sm font-semibold text-slate-700">분석 기준일</span>
            <Input
              className="mt-2 cursor-not-allowed bg-slate-100 text-slate-500"
              type="date"
              value={cmsAsOf}
              readOnly
              aria-readonly="true"
            />
          </label>
          <ExchangeRateField
            exchangeRate={exchangeRate}
            exchangeRateError={exchangeRateError}
            exchangeRateInput={exchangeRateInput}
            onExchangeRateInputChange={onExchangeRateInputChange}
          />
        </section>

        <section className="space-y-3 border-t border-slate-200 pt-5">
          <div>
            <h3 className="text-sm font-bold text-ink">재고 목표</h3>
            <p className="mt-1 text-xs text-slate-500">월평균 판매량 대비 유지할 목표 재고 개월수를 입력합니다.</p>
          </div>
          <div className="max-w-md">
            <label>
              <span className="text-sm font-semibold text-slate-700">안전재고 개월수</span>
              <Input
                className="mt-2"
                type="number"
                value={safetyMonths}
                onChange={(event) => onSafetyMonthsChange(event.target.value)}
                inputMode="decimal"
                min="0.1"
                step="0.1"
              />
              <span className="mt-2 block text-xs text-slate-500">입력한 개월수가 발주 필요수량 계산에 적용됩니다.</span>
            </label>
          </div>
        </section>

        <section className="space-y-3 border-t border-slate-200 pt-5">
          <div>
            <h3 className="text-sm font-bold text-ink">운송 리드타임</h3>
            <p className="mt-1 text-xs text-slate-500">
              선택한 법인이 지원하는 운송수단의 기본값이며, 법인별로 분리해 저장됩니다.
            </p>
          </div>
          {leadTimeLoading ? (
            <p className="text-sm font-semibold text-slate-500">법인별 운송 리드타임을 불러오는 중입니다.</p>
          ) : leadTimeError ? (
            <p className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
              {leadTimeError}
            </p>
          ) : leadTimeMethods.length === 0 ? (
            <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-600">
              본사는 해외 운송 리드타임을 적용하지 않습니다.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {leadTimeMethods.map((method) => (
                <label key={method.code}>
                  <span className="text-sm font-semibold text-slate-700">{method.label} L/T(일)</span>
                  <Input
                    className="mt-2"
                    type="number"
                    value={leadTimeValues[method.code] ?? ""}
                    onChange={(event) => onLeadTimeChange(method.code, event.target.value)}
                    inputMode="numeric"
                    min="1"
                    step="1"
                  />
                  <span className="mt-2 block text-xs text-slate-500">법인 기본값 {method.lead_time_days}일</span>
                </label>
              ))}
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
