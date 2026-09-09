"use client";

import { ChevronDown, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { formatCalendarDuration } from "@/lib/format-calendar-duration";
import { cn } from "@/lib/utils";

import type { NewOrderLogicPolicySettings, NewOrderPolicyMode } from "./types";

type FormulaSectionId =
  | "leadTimeDemand"
  | "safetyStock"
  | "coverBuffer"
  | "inventory"
  | "decision";

const FORMULA_SECTIONS: Array<{
  id: FormulaSectionId;
  title: string;
  summary: string;
  formula: string;
  description: string;
}> = [
  {
    id: "leadTimeDemand",
    title: "① 리드타임수요",
    summary: "입고까지의 보호기간 동안 판매될 것으로 예상되는 수량",
    formula: "P = L + R\n리드타임수요 = d̄ × L",
    description: "d̄는 최근 13주 판매량의 주평균, L은 리드타임, R은 4주 정기 검토주기이며 P는 L+R 보호기간입니다."
  },
  {
    id: "safetyStock",
    title: "② 안전재고",
    summary: "수요와 조달기간의 변동에 대비한 완충 재고",
    formula: "SS원값 = Z × √(P × σ_d² + d̄² × σ_L²)\nSS = MIN(MAX(SS원값, d̄ × 2), d̄ × 13)",
    description: "최종 Z와 판매·리드타임 변동성을 반영한 원값을 주평균 2주분에서 13주분 사이로 제한합니다."
  },
  {
    id: "coverBuffer",
    title: "③ 검토주기수요",
    summary: "다음 정기 검토까지 필요한 주평균 4주분",
    formula: "검토주기수요 = d̄ × R = d̄ × 4",
    description: "4주 정기 검토주기 동안 필요한 수요를 목표재고에 포함합니다."
  },
  {
    id: "inventory",
    title: "④ 보유전체(IP)",
    summary: "미입고·본사창고 가용·운송중·현지가용의 합",
    formula: "IP = 미입고 + 본사창고 가용 + 운송중 + 현지가용",
    description: "교과서의 '보유전체'는 예정대로 들어올 미입고 수량까지 인정한 재고 위치입니다."
  },
  {
    id: "decision",
    title: "⑤ 발주 결정",
    summary: "목표재고 부족분을 낱개 단위로 산출",
    formula: "S = d̄ × L + SS + d̄ × R\nQ = CEILING(MAX(0, S - IP), 1)",
    description: "발주점 게이트 없이 목표재고 부족분을 낱개 단위로 올림해 미입고를 인정한 제안수량을 산출합니다."
  }
];

function scenarioMeta(
  mode: NewOrderPolicyMode,
  settings: NewOrderLogicPolicySettings,
  entityCode?: string | null
) {
  const isHq = String(entityCode || "").trim().toUpperCase() === "HQ";
  if (isHq) {
    const domestic = settings.domesticLeadTime;
    const unavailable = !domestic || domestic.valueUnavailable === true;
    const sampleSize = domestic?.measuredSampleSize;
    const measured = typeof sampleSize === "number" && sampleSize > 0;
    const measuredMonths = domestic?.measuredWindowMonths ?? 12;
    return {
      label: mode === "SHORTAGE" ? "쇼티지 방어" : "현금흐름 우선",
      transport: "국내조달",
      leadTime: unavailable
        ? "확인 필요"
        : formatCalendarDuration(domestic.meanDays, { showWeeks: true }),
      protectionWeeks: unavailable
        ? "확인 필요"
        : formatCalendarDuration(domestic.meanDays + domestic.reviewDays, {
            showWeeks: true
          }),
      sigmaLeadTime: unavailable
        ? "확인 필요"
        : formatCalendarDuration(domestic.sigmaDays, { showWeeks: true }),
      leadTimeBasis: unavailable
        ? "국내조달 리드타임 원천을 확인하려면 분석을 실행해야 합니다"
        : measured
          ? `최근 ${measuredMonths}개월 실측 · 표본 ${sampleSize}건의 산술평균`
          : "국내조달 실측값",
      sigmaBasis: unavailable
        ? "국내조달 리드타임 원천을 확인하려면 분석을 실행해야 합니다"
        : measured
          ? `최근 ${measuredMonths}개월 실측 · 표본 ${sampleSize}건의 STDEV.S`
          : "국내조달 실측값",
      zMajor: (mode === "SHORTAGE"
        ? settings.zMatrix.shortageMajor
        : settings.zMatrix.cashMajor
      ).toFixed(2),
      zMinor: (mode === "SHORTAGE"
        ? settings.zMatrix.shortageMinor
        : settings.zMatrix.cashMinor
      ).toFixed(2)
    };
  }

  const transportCode = settings.policyTransports[mode];
  const leadTime = settings.leadTimes.find((item) => item.code === transportCode);
  const meanDays = leadTime?.meanDays ?? 0;
  const transportLabels = { AIR: "항공", RAIL: "철송", SEA: "해운" } as const;
  const sampleSize = leadTime?.measuredSampleSize;
  const measured = typeof sampleSize === "number" && sampleSize > 0;
  // 응답에 값이 없으면 숫자를 단정하지 않는다. 화면 기본값으로 메우면
  // 실측 연결 실패가 정상 표시와 구분되지 않는다.
  const unavailable = leadTime?.valueUnavailable === true;
  const window =
    leadTime?.measuredWindowFrom && leadTime?.measuredWindowTo
      ? `${leadTime.measuredWindowFrom} ~ ${leadTime.measuredWindowTo}`
      : null;
  const measuredBasis = (suffix: string) =>
    window
      ? `최근 12개월 실측 · 표본 ${sampleSize}건 · 입고완료 ${window}${suffix}`
      : `최근 12개월 실측 · 표본 ${sampleSize}건${suffix}`;
  return {
    label: mode === "SHORTAGE" ? "쇼티지 방어" : "현금흐름 우선",
    transport: `${transportLabels[transportCode]} ${transportCode}`,
    // 실측값은 소수 2자리까지 보여준다. 한 자리로 줄이면 72.79일이 명세
    // 고정값 72.9일과 같아 보여 근거를 구분할 수 없다.
    leadTime: unavailable
      ? "확인 필요"
      : formatCalendarDuration(meanDays, { showWeeks: true }),
    protectionWeeks: unavailable
      ? "확인 필요"
      : formatCalendarDuration(meanDays + settings.coverWeeks * 7, {
          showWeeks: true
        }),
    sigmaLeadTime: unavailable
      ? "확인 필요"
      : formatCalendarDuration((leadTime?.sigmaWeeks ?? 0) * 7, {
          showWeeks: true
        }),
    leadTimeBasis: unavailable
      ? "리드타임 원천을 확인할 수 없어 분석을 다시 실행해야 합니다"
      : measured
        ? measuredBasis("의 산술평균")
        : "기술명세 고정값(실측 대상 아님)",
    sigmaBasis: unavailable
      ? "리드타임 원천을 확인할 수 없어 분석을 다시 실행해야 합니다"
      : measured
        ? measuredBasis("의 STDEV.S ÷ 7")
        : "기술명세 고정값(실측 대상 아님)",
    zMajor: (mode === "SHORTAGE"
      ? settings.zMatrix.shortageMajor
      : settings.zMatrix.cashMajor
    ).toFixed(2),
    zMinor: (mode === "SHORTAGE"
      ? settings.zMatrix.shortageMinor
      : settings.zMatrix.cashMinor
    ).toFixed(2)
  };
}

export function OrderFormulaDrawer({
  open,
  policyMode,
  settings,
  entityCode = null,
  hasAnalysisResult = false,
  onClose
}: {
  open: boolean;
  policyMode: NewOrderPolicyMode;
  settings: NewOrderLogicPolicySettings;
  entityCode?: string | null;
  hasAnalysisResult?: boolean;
  onClose: () => void;
}) {
  const [expandedSection, setExpandedSection] = useState<FormulaSectionId | null>(
    "leadTimeDemand"
  );
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const isHq = String(entityCode || "").trim().toUpperCase() === "HQ";
  const isUsa = String(entityCode || "").trim().toUpperCase() === "USA";
  const domestic = settings.domesticLeadTime;
  const reviewDays = domestic?.reviewDays ?? 28;
  const floorDays = domestic?.safetyStockFloorDays ?? 14;
  const capDays = domestic?.safetyStockCapDays ?? 35;
  const scenario = scenarioMeta(policyMode, settings, entityCode);
  const formulaSections = FORMULA_SECTIONS.map((section) => {
    if (section.id === "leadTimeDemand") {
      return {
        ...section,
        description: isHq
          ? `d̄는 최근 91일 판매량의 일평균, L은 국내조달 리드타임, R은 ${formatCalendarDuration(reviewDays, { showWeeks: true })} 정기 검토주기이며 P=L+R입니다. L/T 근거는 ${scenario.leadTimeBasis}입니다.`
          : `d̄는 최근 91일(13주) 판매량의 주평균이며, L은 운송 리드타임, R은 ${formatCalendarDuration(settings.coverWeeks * 7, { showWeeks: true })} 정기 검토주기입니다. P=L+R이고 L/T 근거는 ${scenario.leadTimeBasis}입니다.`
      };
    }
    if (section.id === "safetyStock") {
      return {
        ...section,
        formula: isHq
          ? `SS원값 = Z × √(P × σ_d² + d̄² × σ_L²)\nSS = MIN(MAX(SS원값, d̄ × ${floorDays}), d̄ × ${capDays})`
          : `SS원값 = Z × √(P × σ_d² + d̄² × σ_L²)\nSS = MIN(MAX(SS원값, d̄ × ${settings.safetyStockFloorWeeks}), d̄ × ${settings.safetyStockCapWeeks})`,
        description: isHq
          ? `최종 Z와 판매·리드타임 변동성을 반영한 원값을 일평균 ${formatCalendarDuration(floorDays, { showWeeks: true })}분에서 ${formatCalendarDuration(capDays, { showWeeks: true })}분 사이로 제한합니다. σ_L 근거는 ${scenario.sigmaBasis}입니다.`
          : `최종 Z와 판매·리드타임 변동성을 반영한 원값을 주평균 ${formatCalendarDuration(settings.safetyStockFloorWeeks * 7, { showWeeks: true })}분에서 ${formatCalendarDuration(settings.safetyStockCapWeeks * 7, { showWeeks: true })}분 사이로 제한합니다. σ_L 근거는 ${scenario.sigmaBasis}입니다.`
      };
    }
    if (section.id === "coverBuffer") {
      return {
        ...section,
        summary: isHq
          ? `다음 정기 검토까지 필요한 일평균 ${formatCalendarDuration(reviewDays, { showWeeks: true })}분`
          : `다음 정기 검토까지 필요한 주평균 ${formatCalendarDuration(settings.coverWeeks * 7, { showWeeks: true })}분`,
        formula: `검토주기수요 = d̄ × R = d̄ × ${isHq ? reviewDays : settings.coverWeeks}`,
        description: isHq
          ? `${formatCalendarDuration(reviewDays, { showWeeks: true })} 정기 검토주기 동안 필요한 수요를 목표재고에 포함합니다.`
          : `${settings.coverWeeks}주 정기 검토주기 동안 필요한 수요를 목표재고에 포함합니다.`
      };
    }
    if (section.id === "inventory" && isHq) {
      return {
        ...section,
        summary: "입고예정(①+②+③)과 OPO 가용재고의 합",
        formula:
          "입고예정 = ① 미입고 + ② PNFM확정 + ③ 입고진행중\nIP = 입고예정 + OPO 가용재고 (shipping 운송중 제외)",
        description:
          "④ 입고완료는 OPO 가용재고에 반영된 값이므로 표시만 하고, 본사는 shipping 운송중도 IP에 더하지 않습니다."
      };
    }
    if (section.id === "inventory" && !isHq) {
      const entityWarehouse = isUsa ? "본사 미주창고" : "본사 EU창고";
      const localWarehouse = isUsa ? "미주 현지" : "EU 현지";
      return {
        ...section,
        summary: `입고예정·${entityWarehouse} 가용·운송중·${localWarehouse}가용의 합`,
        formula:
          `입고예정 = ① 미입고 + ② PNFM확정 + ③ 입고진행중\nIP = 입고예정 + ${entityWarehouse} 가용 + 운송중 + ${localWarehouse}가용`,
        description:
          "④ 입고완료는 이미 재고에 반영된 값이므로 Excel 원천 확인용으로만 표시하고 IP에는 더하지 않습니다."
      };
    }
    return section;
  });

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    return () => {
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus();
    };
  }, [open]);

  useEffect(() => {
    if (open) setExpandedSection("leadTimeDemand");
  }, [open]);

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      ) ?? []
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        aria-label="발주 산식 패널 닫기"
        className="fixed inset-0 z-[70] cursor-default bg-black/20"
        onClick={onClose}
      />
      <aside
        id="order-formula-dialog"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="order-formula-title"
        aria-describedby="order-formula-description"
        onKeyDown={handleDialogKeyDown}
        className="fixed inset-y-0 right-0 z-[80] flex w-full max-w-[520px] flex-col border-l border-border bg-surface shadow-panel"
      >
        <header className="shrink-0 border-b border-border px-5 py-5 sm:px-7">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 id="order-formula-title" className="text-[20px] font-black text-ink">
                발주 산식
              </h2>
              <p
                id="order-formula-description"
                className="mt-1 text-[12px] font-semibold leading-5 text-muted"
              >
                제안 수량이 계산되는 기준을 확인합니다.
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              aria-label="발주 산식 패널 닫기"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-[8px] border border-border text-muted transition hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="inline-flex h-7 items-center rounded-[7px] border border-border bg-surface-soft px-2.5 text-[10px] font-bold text-muted">
              현재 선택 · <strong className="ml-1 text-ink">{scenario.label}</strong>
            </span>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
          <section aria-labelledby="order-formula-summary-title">
            <p
              id="order-formula-summary-title"
              className="text-[14px] font-black text-ink"
            >
              최종 발주량은 이렇게 계산됩니다
            </p>
            <p className="mt-2 text-[24px] font-black tracking-normal text-ink">
              목표재고(S) - 보유전체(IP)
            </p>
            <p className="mt-2 text-[11px] font-semibold leading-4 text-muted">
              발주점 게이트 없이 목표재고에서 보유전체를 뺀 부족분을 계산하고,
              결과는 낱개 단위로 올림합니다.
            </p>

            <div className="mt-5 flex items-stretch gap-1.5 overflow-x-auto pb-2">
              {[
                ["리드타임", "수요"],
                ["안전재고", ""],
                ["검토주기", isHq ? `${reviewDays}일` : `${settings.coverWeeks}주`],
                ["보유전체", ""]
              ].map(([first, second], index) => (
                <div key={first} className="contents">
                  {index > 0 ? (
                    <span className="self-center text-[14px] font-black text-muted">
                      {index === 3 ? "−" : "+"}
                    </span>
                  ) : null}
                  <div
                    className={cn(
                      "flex h-[70px] w-[92px] shrink-0 flex-col items-center justify-center rounded-[8px] border px-2 text-center text-[11px] font-black leading-4",
                      index === 3
                        ? "border-blue-200 bg-blue-50 text-blue-800"
                        : "border-border bg-surface-soft text-ink"
                    )}
                  >
                    <span>{first}</span>
                    {second ? <span>{second}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="my-6 border-t border-border" />

          <section aria-label="레이어별 상세 산식" className="space-y-3">
            {formulaSections.map((section) => {
              const expanded = expandedSection === section.id;
              const panelId = `order-formula-${section.id}-panel`;
              return (
                <div
                  key={section.id}
                  className={cn(
                    "overflow-hidden rounded-[8px] border",
                    expanded ? "border-blue-200 bg-blue-50/40" : "border-border bg-surface"
                  )}
                >
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    onClick={() =>
                      setExpandedSection((current) =>
                        current === section.id ? null : section.id
                      )
                    }
                    className="flex min-h-[62px] w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40"
                  >
                    <span className="min-w-0">
                      <span
                        className={cn(
                          "block text-[12px] font-black",
                          expanded ? "text-blue-800" : "text-ink"
                        )}
                      >
                        {section.title}
                      </span>
                      <span className="mt-1 block text-[10.5px] font-semibold leading-4 text-muted">
                        {section.summary}
                      </span>
                    </span>
                    <ChevronDown
                      className={cn(
                        "h-4 w-4 shrink-0 text-muted transition-transform",
                        expanded && "rotate-180"
                      )}
                      aria-hidden="true"
                    />
                  </button>
                  {expanded ? (
                    <div id={panelId} className="border-t border-blue-100 px-4 py-4">
                      <code className="block whitespace-pre overflow-x-auto rounded-[7px] bg-ink px-3 py-3 font-mono text-[11px] font-bold leading-5 text-white">
                        {section.formula}
                      </code>
                      <p className="mt-3 text-[10.5px] font-semibold leading-5 text-muted">
                        {section.description}
                      </p>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </section>

          {hasAnalysisResult ? (
            <section className="mt-6" aria-labelledby="order-formula-policy-title">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p
                    id="order-formula-policy-title"
                    className="text-[12px] font-black text-ink"
                  >
                    기준 적용값
                  </p>
                  <p className="mt-1 text-[10.5px] font-semibold text-muted">
                    {scenario.label} · 주력/일반 등급에 따라 최종 Z 적용
                  </p>
                </div>
                <span className="text-[10px] font-bold text-muted">
                  P {scenario.protectionWeeks}
                </span>
              </div>
              <dl className="mt-3 divide-y divide-border border-y border-border text-[10.5px]">
                <div className="grid grid-cols-[110px_1fr] gap-3 py-2.5">
                  <dt className="font-bold text-muted">운송 기준</dt>
                  <dd className="text-right font-black text-ink">
                    {scenario.transport} · L/T {scenario.leadTime}
                    <span className="mt-0.5 block text-[9.5px] font-semibold text-muted">
                      {scenario.leadTimeBasis}
                    </span>
                  </dd>
                </div>
                <div className="grid grid-cols-[110px_1fr] gap-3 py-2.5">
                  <dt className="font-bold text-muted">보호기간 / σ_L</dt>
                  <dd className="text-right font-black text-ink">
                    {scenario.protectionWeeks} / {scenario.sigmaLeadTime}
                    <span className="mt-0.5 block text-[9.5px] font-semibold text-muted">
                      {scenario.sigmaBasis}
                    </span>
                  </dd>
                </div>
                <div className="grid grid-cols-[110px_1fr] gap-3 py-2.5">
                  <dt className="font-bold text-muted">최종 Z</dt>
                  <dd className="text-right font-black text-ink">
                    주력 {scenario.zMajor} · 일반 {scenario.zMinor}
                  </dd>
                </div>
                <div className="grid grid-cols-[110px_1fr] gap-3 py-2.5">
                  <dt className="font-bold text-muted">재고·발주 기준</dt>
                  <dd className="text-right font-black text-ink">
                    {isHq
                      ? `SS ${floorDays}~${capDays}일 · 검토주기 ${reviewDays}일`
                      : `SS ${settings.safetyStockFloorWeeks}~${settings.safetyStockCapWeeks}주 · 검토주기 ${settings.coverWeeks}주`}
                  </dd>
                </div>
              </dl>
            </section>
          ) : null}

        </div>
      </aside>
    </>
  );
}
