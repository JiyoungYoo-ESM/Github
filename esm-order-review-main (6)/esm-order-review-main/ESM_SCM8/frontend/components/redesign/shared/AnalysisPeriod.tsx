"use client";

import { analysisPeriodLabel } from "../lib/workspace-format";
import { monthsBetweenInclusive } from "../lib/yoy-comparison";
import { exchangeRateBasisLabel } from "../lib/currency-format";

export function AnalysisPeriodBadge({ options }: { options?: Record<string, unknown> | null }) {
  const averageEurKrwRate =
    Number(options?.average_eur_krw_rate) > 0
      ? Number(options?.average_eur_krw_rate)
      : null;
  const exchangeBasis = exchangeRateBasisLabel(options, averageEurKrwRate);
  return (
    <>
      <span className="inline-flex h-[30px] items-center rounded-full border border-border bg-surface px-[14px] text-[13px] font-black text-muted2">
        분석 기간: {analysisPeriodLabel(options)}
      </span>
      {exchangeBasis ? (
        <p className="mt-[9px] text-[12px] font-semibold leading-[1.5] text-muted2">{exchangeBasis}</p>
      ) : null}
    </>
  );
}

export function AnalysisPeriodCaveat({ options }: { options?: Record<string, unknown> | null }) {
  const monthCount = monthsBetweenInclusive(String(options?.start_date ?? ""), String(options?.end_date ?? ""));
  if (monthCount <= 0 || monthCount >= 12) return null;
  return (
    <p className="mt-[8px] text-[12px] font-semibold leading-[1.5] text-muted2">
      12개월 미만 기간은 선택 기간 내 집계와 최고월 기준으로 표시되며, 연간 시즌성 판단에는 제한이 있습니다.
    </p>
  );
}


