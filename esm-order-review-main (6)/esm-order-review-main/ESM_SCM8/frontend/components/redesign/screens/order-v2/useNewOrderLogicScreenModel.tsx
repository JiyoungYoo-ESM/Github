"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiRequestError,
  cancelOrderLogicV2,
  exportOrderLogicV2Excel,
  isAbortError,
  runOrderLogicV2,
  type OrderLogicV2ApiRow,
  type OrderLogicV2LeadTimeAudit,
  type OrderLogicV2PolicyMode,
  type OrderLogicV2Result,
  type OrderLogicV2SettingsPayload
} from "@/lib/api";
import { useAuthSession } from "@/components/auth/AuthSessionContext";

import { sampleNewOrderLogicSettings } from "./fixtures";
import type {
  NewOrderDataStatus,
  NewOrderExportContext,
  NewOrderLeadTimeSetting,
  NewOrderLogicDataset,
  NewOrderLogicPolicySettings,
  NewOrderLogicRow,
  NewOrderModeResult,
  NewOrderPolicyMode,
  NewOrderSignal,
  NewOrderSimulationResult,
  NewOrderSimulationSummary,
  NewOrderTransportCode
} from "./types";

function numberOr(value: unknown, fallback = 0) {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizedDataStatus(row: OrderLogicV2ApiRow): NewOrderDataStatus {
  if (row.check_required === true || row.data_status === "확인필요") return "확인필요";
  if (row.calculable === false || row.data_status === "계산불가" || row.data_status === "데이터부족") {
    return "이력부족";
  }
  const status = String(row.data_status || "정상").replace(/^⚠/, "");
  if (status === "판매없음") return "판매없음";
  if (status === "확인(간헐)") return "확인(간헐)";
  if (status === "대량포함") return "대량포함";
  return "정상";
}

function normalizedSignal(row: OrderLogicV2ApiRow): NewOrderSignal {
  if (row.calculable === false) return "-";
  const signal = String(row.order_signal || "").trim();
  if (signal.includes("확인")) return "확인후발주";
  if (signal.includes("발주")) return "발주";
  if (signal.includes("충분")) return "충분";
  return "-";
}

function modeResult(row: OrderLogicV2ApiRow): NewOrderModeResult {
  return {
    transportMode: row.transport_mode,
    zApplied: nullableNumber(row.z_applied),
    leadTimeDays: nullableNumber(row.lead_time_days),
    leadTimeSigmaWeeks: nullableNumber(row.lead_time_sigma_weeks),
    safetyStock: nullableNumber(row.safety_stock),
    reorderPoint: nullableNumber(row.reorder_point),
    targetStock: nullableNumber(row.target_stock),
    suggestedQty: nullableNumber(row.suggested_qty),
    upperSuggestedQty: nullableNumber(row.upper_suggested_qty),
    signal: normalizedSignal(row),
    referenceAmountEur: nullableNumber(
      row.suggested_amount_local ?? row.suggested_amount_eur
    ),
    referenceAmountKrw: nullableNumber(row.suggested_amount_krw)
  };
}

function rowsBySku(rows: OrderLogicV2ApiRow[] | undefined) {
  return new Map((rows || []).map((row) => [row.sku_code, row]));
}

function isExcludedOrderItem(row: OrderLogicV2ApiRow) {
  return row.sku_code.trim().toLocaleLowerCase() === "delivery charge";
}

function comparisonReasons(
  official: OrderLogicV2ApiRow,
  other: OrderLogicV2ApiRow
) {
  const reasons: string[] = [];
  if (official.lead_time_days !== other.lead_time_days) {
    reasons.push(
      `${official.transport_mode || "운송수단"} 리드타임 적용`
    );
  }
  if (official.z_applied !== other.z_applied) {
    reasons.push(`서비스 수준 Z ${numberOr(official.z_applied).toFixed(2)} 적용`);
  }
  if (official.data_status && official.data_status !== "정상") {
    reasons.push(String(official.data_status).replace(/^⚠/, ""));
  }
  if (official.validation_error) reasons.push(official.validation_error);
  return reasons;
}

export function mapOrderLogicV2Result(result: OrderLogicV2Result): NewOrderLogicDataset {
  const isHqEntity = String(result.entity_code || "").trim().toUpperCase() === "HQ";
  const cashRows = rowsBySku(result.scenarios?.CASH?.rows);
  const shortageRows = rowsBySku(result.scenarios?.SHORTAGE?.rows);
  const officialRows = result.scenarios?.[result.applied_mode]?.rows || result.rows || [];
  const rows: NewOrderLogicRow[] = officialRows.filter((row) => !isExcludedOrderItem(row)).map((official) => {
    const cash = cashRows.get(official.sku_code) || official;
    const shortage = shortageRows.get(official.sku_code) || official;
    return {
      id: official.sku_code,
      productCode: official.sku_code,
      productName: official.product_name || "",
      brand: official.brand || "",
      dataStatus: normalizedDataStatus(official),
      grade:
        official.grade === "MAJOR"
          ? "주력"
          : official.grade === "MINOR"
            ? "일반"
            : null,
      isCalculable: official.calculable !== false,
      decisionLockReason:
        official.calculable === false
          ? official.check_required_reason ||
            official.validation_error ||
            "입력값 검증에 실패해 계산할 수 없습니다."
          : undefined,
      weeklyMean: nullableNumber(official.demand_avg),
      cv: nullableNumber(official.cv),
      inboundQty: numberOr(official.incoming_qty),
      euAvailableQty: numberOr(official.eu_available_qty),
      inTransitQty: numberOr(official.transit_qty),
      localAvailableQty: numberOr(official.local_available_qty),
      inventoryPosition: numberOr(official.inventory_position),
      inventoryPositionWithoutIncoming: numberOr(
        official.inventory_position_without_incoming,
        numberOr(official.inventory_position) - numberOr(official.incoming_qty)
      ),
      nextEta: official.next_eta || null,
      nextEtaStatus:
        official.next_eta_status === "원천 ETA" ||
        official.next_eta_status === "출고일 추정 ETA" ||
        official.next_eta_status === "원천·추정 ETA"
          ? official.next_eta_status
          : official.next_eta
            ? "원천 ETA"
            : !isHqEntity &&
                (numberOr(official.incoming_qty) > 0 ||
                  numberOr(official.transit_qty) > 0)
              ? "ETA 미확인"
              : "입고 예정 없음",
      stockoutWeeks: nullableNumber(official.depletion_weeks),
      confirmedQty: nullableNumber(official.confirmed_qty ?? official.suggested_qty),
      memo: official.memo || "",
      unitPriceEur: nullableNumber(
        official.unit_price_local ?? official.unit_price_eur
      ),
      unitPriceKrw: nullableNumber(official.unit_price_krw),
      modes: {
        CASH: modeResult(cash),
        SHORTAGE: modeResult(shortage)
      },
      comparisonReasonsByMode: {
        CASH: comparisonReasons(cash, shortage),
        SHORTAGE: comparisonReasons(shortage, cash)
      }
    };
  });
  return {
    meta: {
      jobId: result.job_id,
      logicVersion: result.logic_version,
      currencyCode:
        result.currency_code === "USD"
          ? "USD"
          : result.currency_code === "KRW"
            ? "KRW"
            : "EUR",
      appliedMode: result.applied_mode,
      sourceAsOf: result.source_fetched_at || result.as_of,
      calculatedAt: result.calculated_at,
      demandPeriod: {
        from: result.period_start,
        to: result.period_end,
        completedWeeks: result.demand_period_count ?? 13,
        observationWindowDays:
          result.observation_window_days ??
          (result.period_unit === "day"
            ? result.demand_period_count ?? 91
            : (result.demand_period_count ?? 13) * 7),
        demandGrain: result.demand_grain
      },
      periodUnit: result.period_unit === "day" ? "day" : "week",
      entityCode: result.entity_code,
      warehouseCode: result.warehouse_code,
      sourceSnapshotId: result.source_snapshot_id,
      warnings: result.warnings || []
    },
    rows
  };
}

function apiSettings(settings: NewOrderLogicPolicySettings): OrderLogicV2SettingsPayload {
  return {
    grade_cutoff: settings.gradeCutoffPct / 100,
    cover_weeks: settings.coverWeeks,
    ss_floor_weeks: settings.safetyStockFloorWeeks,
    ss_cap_weeks: settings.safetyStockCapWeeks,
    // 리드타임과 정책 운송수단은 화면에서 되돌려 보내지 않는다. 서버가 매
    // 실행마다 법인 리드타임 API 실측으로 덮어쓰므로, 화면 표시값을 실어
    // 보내면 실측 이전 값이 요청에 섞여 감사 추적이 흐려진다.
    z_cash_major: settings.zMatrix.cashMajor,
    z_cash_minor: settings.zMatrix.cashMinor,
    z_shortage_major: settings.zMatrix.shortageMajor,
    z_shortage_minor: settings.zMatrix.shortageMinor
  };
}

// 발주분석 데이터 입력이 쓰는 core/lead_times.py의 법인별 운송수단 구성과 같은
// 범위를 V2 화면에 적용한다. 법인이 운영하지 않는 운송수단(미주 철송)은
// 설정 카드에 노출하지 않는다.
const ENTITY_TRANSPORT_CODES: Record<string, NewOrderTransportCode[]> = {
  PL: ["AIR", "RAIL", "SEA"],
  USA: ["AIR", "SEA"],
  // 본사는 국내조달 리드타임(실입고일 - PO 생성일) 하나만 사용한다.
  // 운송수단 카드를 남기면 값이 없어 0으로 채워지고, 그 0이 설정 검증에서
  // 오류로 잡혀 분석 실행까지 막힌다.
  HQ: []
};

function entityLeadTimeSettings(
  leadTimes: NewOrderLeadTimeSetting[],
  entityCode?: string | null
): NewOrderLeadTimeSetting[] {
  const supported = ENTITY_TRANSPORT_CODES[String(entityCode || "").trim().toUpperCase()];
  if (!supported) return leadTimes;
  return leadTimes.filter((item) => supported.includes(item.code));
}

// 본사 응답은 일 단위 정책 필드를 담고 주 단위 필드를 담지 않는다. 통화나
// 법인 코드로 추정하지 않고 실제 필드 유무로 판별한다.
function isDayUnitPayload(payload: OrderLogicV2SettingsPayload): boolean {
  return payload.lt_days !== undefined || payload.review_days !== undefined;
}

// 서버는 본사 시나리오 운송수단으로 `HQ_DOMESTIC`을 내려준다. 이 값은 항공·
// 철송·해운 카드와 대응되지 않으므로 화면 운송수단 코드로 승격하지 않는다.
function transportCodeOrNull(
  value: string | undefined
): NewOrderTransportCode | null {
  return value === "AIR" || value === "RAIL" || value === "SEA" ? value : null;
}

function settingsFromApi(
  payload: OrderLogicV2SettingsPayload | undefined,
  mode: NewOrderPolicyMode,
  entityCode?: string | null,
  leadTimeAudit?: OrderLogicV2LeadTimeAudit | null
): NewOrderLogicPolicySettings {
  if (!payload) {
    const base = { ...sampleNewOrderLogicSettings, policyMode: mode };
    if (String(entityCode || "").trim().toUpperCase() !== "HQ") return base;
    return {
      ...base,
      leadTimes: [],
      domesticLeadTime: {
        meanDays: Number.NaN,
        sigmaDays: Number.NaN,
        reviewDays: 28,
        safetyStockFloorDays: 14,
        safetyStockCapDays: 35,
        valueUnavailable: true
      }
    };
  }
  // 리드타임 감사값은 실측 집계에 성공한 운송수단만 담고 있다. V2 엔진은
  // 해운을 SEA로, 감사값은 원천 코드를 그대로 쓰므로 코드로 직접 대조한다.
  const measured = leadTimeAudit?.modes || {};
  // 실측·명세값 구분과 별개로, 응답에 값이 없으면 화면 기본값으로 메우지
  // 않는다. 과거에는 픽스처 기본값(해운 72.9일/2.18주)으로 조용히 떨어져
  // 실측 연결 실패가 정상 표시와 구분되지 않았다.
  const leadTimeFields: Record<
    NewOrderTransportCode,
    { mean?: number | null; sigma?: number | null }
  > = {
    AIR: { mean: payload.lt_air_days, sigma: payload.sigma_l_air_weeks },
    RAIL: { mean: payload.lt_rail_days, sigma: payload.sigma_l_rail_weeks },
    SEA: { mean: payload.lt_sea_days, sigma: payload.sigma_l_sea_weeks }
  };
  return {
    ...sampleNewOrderLogicSettings,
    policyMode: mode,
    gradeCutoffPct: numberOr(payload.grade_cutoff, 0.8) * 100,
    coverWeeks: numberOr(payload.cover_weeks, 4),
    safetyStockFloorWeeks: numberOr(payload.ss_floor_weeks, 2),
    safetyStockCapWeeks: numberOr(payload.ss_cap_weeks, 13),
    // 본사는 일 단위 정책값을 쓴다. 주 단위 필드가 응답에 없으므로 화면
    // 기본값(4주/2주/13주)이 남지 않도록 일 단위 값을 그대로 담는다.
    domesticLeadTime: isDayUnitPayload(payload)
      ? {
          meanDays: numberOr(payload.lt_days, 0),
          sigmaDays: numberOr(payload.sigma_l_days, 0),
          reviewDays: numberOr(payload.review_days, 28),
          safetyStockFloorDays: numberOr(payload.ss_floor_days, 14),
          safetyStockCapDays: numberOr(payload.ss_cap_days, 35),
          measuredSampleSize:
            typeof leadTimeAudit?.sample_size === "number"
              ? leadTimeAudit.sample_size
              : undefined,
          measuredWindowMonths:
            typeof leadTimeAudit?.observation_months === "number"
              ? leadTimeAudit.observation_months
              : undefined,
          valueUnavailable:
            nullableNumber(payload.lt_days) === null ||
            nullableNumber(payload.sigma_l_days) === null
        }
      : undefined,
    zMatrix: {
      cashMajor: numberOr(payload.z_cash_major, 1.28),
      cashMinor: numberOr(payload.z_cash_minor, 1.08),
      shortageMajor: numberOr(payload.z_shortage_major, 1.68),
      shortageMinor: numberOr(payload.z_shortage_minor, 1.28)
    },
    policyTransports: {
      // 본사 시나리오 운송수단은 `HQ_DOMESTIC`이며 항공·철송·해운 카드와
      // 대응되지 않는다. 운송수단 배지는 표시 대상이 아니라 강조하지 않는다.
      CASH: transportCodeOrNull(payload.cash_transport_mode) ?? "RAIL",
      SHORTAGE: transportCodeOrNull(payload.shortage_transport_mode) ?? "SEA"
    },
    leadTimes: entityLeadTimeSettings(sampleNewOrderLogicSettings.leadTimes, entityCode).map((item) => {
      const sampleSize = measured[item.code]?.sample_size;
      const measuredSampleSize =
        typeof sampleSize === "number" && Number.isFinite(sampleSize)
          ? sampleSize
          : undefined;
      const field = leadTimeFields[item.code];
      const mean = nullableNumber(field?.mean);
      const sigma = nullableNumber(field?.sigma);
      const valueUnavailable = mean === null || sigma === null;
      return {
        ...item,
        measuredSampleSize,
        measuredWindowFrom: measuredSampleSize
          ? leadTimeAudit?.completion_date_from
          : undefined,
        measuredWindowTo: measuredSampleSize
          ? leadTimeAudit?.completion_date_to
          : undefined,
        valueUnavailable,
        // 실측값이 없을 때는 0으로 오인시키지 않고 화면에서 확인 필요로 알린다.
        meanDays: mean ?? Number.NaN,
        sigmaWeeks: sigma ?? Number.NaN
      };
    })
  };
}

function todayInZone(timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value || "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

// Use HQ's Korean date cutoff; the backend applies calendar-day windows, including weekends.
function entityToday(entityCode: string | null | undefined) {
  const code = String(entityCode ?? "").trim().toUpperCase();
  return todayInZone(code === "HQ" ? "Asia/Seoul" : "Europe/Warsaw");
}

function summarizeDataset(
  dataset: NewOrderLogicDataset,
  mode: NewOrderPolicyMode
): NewOrderSimulationSummary {
  let orderSkuCount = 0;
  let confirmSkuCount = 0;
  let totalSuggestedQty = 0;
  let totalReferenceAmountEur = 0;
  let hasAmount = false;
  for (const row of dataset.rows) {
    const outcome = row.modes[mode];
    if (outcome.signal === "발주") orderSkuCount += 1;
    if (outcome.signal === "확인후발주") confirmSkuCount += 1;
    totalSuggestedQty += outcome.suggestedQty ?? 0;
    if (outcome.referenceAmountEur !== null && outcome.referenceAmountEur !== undefined) {
      totalReferenceAmountEur += outcome.referenceAmountEur;
      hasAmount = true;
    }
  }
  return {
    mode,
    orderSkuCount,
    confirmSkuCount,
    totalSuggestedQty,
    totalReferenceAmountEur: hasAmount ? totalReferenceAmountEur : null
  };
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

export function useNewOrderLogicScreenModel() {
  const { selectedEntity } = useAuthSession();
  const [data, setData] = useState<NewOrderLogicDataset | null>(null);
  const [settings, setSettings] = useState<NewOrderLogicPolicySettings>(() =>
    settingsFromApi(undefined, "SHORTAGE", selectedEntity)
  );
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const currentJobIdRef = useRef<string | null>(null);
  const selectedEntityRef = useRef(selectedEntity);
  const entityGenerationRef = useRef(0);
  const [simulating, setSimulating] = useState(false);
  const [applyingSettings, setApplyingSettings] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [simulation, setSimulation] = useState<NewOrderSimulationResult | null>(null);
  const [decisionDirtyIds, setDecisionDirtyIds] = useState<Set<string>>(
    () => new Set()
  );

  useEffect(() => {
    selectedEntityRef.current = selectedEntity;
    entityGenerationRef.current += 1;
    currentJobIdRef.current = null;
    setData(null);
    setSettings(settingsFromApi(undefined, "SHORTAGE", selectedEntity));
    setSimulation(null);
    setError(null);
    setRunning(false);
    setCancelling(false);
  }, [selectedEntity]);

  const executeRun = useCallback(async (nextSettings: NewOrderLogicPolicySettings) => {
    const runEntity = selectedEntity;
    const runGeneration = entityGenerationRef.current;
    const isCurrentEntityRun = () => (
      selectedEntityRef.current === runEntity &&
      entityGenerationRef.current === runGeneration
    );
    setError(null);
    currentJobIdRef.current = null;
    try {
      const result = await runOrderLogicV2({
        as_of: entityToday(selectedEntity),
        applied_mode: nextSettings.policyMode,
        settings: apiSettings(nextSettings)
      }, (jobId) => {
        if (isCurrentEntityRun()) currentJobIdRef.current = jobId;
      });
      if (!isCurrentEntityRun()) return;
      setData(mapOrderLogicV2Result(result));
      setSettings(
        settingsFromApi(
          result.settings,
          result.applied_mode,
          result.entity_code,
          result.lead_time_audit
        )
      );
      setDecisionDirtyIds(new Set());
      setSimulation(null);
      setError(null);
    } catch (caught) {
      if (isCurrentEntityRun() && !isAbortError(caught)) {
        setError(caught instanceof Error ? caught.message : "발주 계산에 실패했습니다.");
      }
    }
  }, [selectedEntity]);

  // "분석 실행" 버튼 전용 - 이 버튼을 눌렀을 때만 running을 켜서
  // "분석 실행 중…" 표시가 이 버튼 클릭에만 반응하게 한다.
  const run = useCallback(
    async (nextSettings: NewOrderLogicPolicySettings) => {
      const runEntity = selectedEntity;
      const runGeneration = entityGenerationRef.current;
      const isCurrentEntityRun = () => (
        selectedEntityRef.current === runEntity &&
        entityGenerationRef.current === runGeneration
      );
      setRunning(true);
      try {
        await executeRun(nextSettings);
      } finally {
        if (isCurrentEntityRun()) setRunning(false);
      }
    },
    [executeRun, selectedEntity]
  );

  const cancelRun = useCallback(async () => {
    const jobId = currentJobIdRef.current;
    if (!jobId) return;
    setCancelling(true);
    try {
      await cancelOrderLogicV2(jobId);
      setError("분석을 중단했습니다.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석 중단에 실패했습니다.");
    } finally {
      currentJobIdRef.current = null;
      setCancelling(false);
      setRunning(false);
    }
  }, []);

  const simulate = useCallback(
    async (candidateSettings: NewOrderLogicPolicySettings) => {
      if (!data) return;
      setSimulating(true);
      setError(null);
      try {
        const result = await runOrderLogicV2({
          as_of: entityToday(selectedEntity),
          applied_mode: candidateSettings.policyMode,
          settings: apiSettings(candidateSettings),
          preview: true
        });
        const candidate = mapOrderLogicV2Result(result);
        setSimulation({
          jobId: result.job_id,
          simulatedAt: result.calculated_at,
          baseline: summarizeDataset(data, data.meta.appliedMode),
          candidate: summarizeDataset(candidate, candidateSettings.policyMode),
          changedSkuCount: candidate.rows.filter((row) => {
            const previous = data.rows.find((item) => item.id === row.id);
            const previousOutcome = previous?.modes[data.meta.appliedMode];
            const candidateOutcome = row.modes[candidateSettings.policyMode];
            return (
              !previous ||
              previousOutcome?.suggestedQty !== candidateOutcome.suggestedQty ||
              previousOutcome.signal !== candidateOutcome.signal
            );
          }).length
        });
      } catch (caught) {
        if (!isAbortError(caught)) {
          setError(caught instanceof Error ? caught.message : "시뮬레이션에 실패했습니다.");
        }
      } finally {
        setSimulating(false);
      }
    },
    [data, selectedEntity]
  );

  const applySettings = useCallback(
    async (nextSettings: NewOrderLogicPolicySettings) => {
      setApplyingSettings(true);
      try {
        // 설정 적용은 다음 분석에 사용할 세션 설정만 확정한다.
        // 실제 계산은 상단 "분석 실행" 버튼의 run 경로에서만 수행한다.
        setSettings(nextSettings);
        setData(null);
        setDecisionDirtyIds(new Set());
        setSimulation(null);
        setError(null);
      } finally {
        setApplyingSettings(false);
      }
    },
    []
  );

  const updateRow = useCallback(
    (rowId: string, patch: Partial<Pick<NewOrderLogicRow, "confirmedQty" | "memo">>) => {
      setData((current) =>
        current
          ? {
              ...current,
              rows: current.rows.map((row) =>
                row.id === rowId ? { ...row, ...patch } : row
              )
            }
          : current
      );
    },
    []
  );

  const exportExcel = useCallback(
    async (context: NewOrderExportContext) => {
      if (!data || !context.jobId) return;
      setExportingExcel(true);
      setError(null);
      try {
        const visibleIds = new Set(context.rowIds);
        const overrides = data.rows
          .filter(
            (row) =>
              visibleIds.has(row.id) &&
              decisionDirtyIds.has(row.id) &&
              row.isCalculable &&
              row.confirmedQty !== null &&
              row.confirmedQty !== undefined
          )
          .map((row) => ({
            sku_code: row.productCode,
            confirmed_qty: row.confirmedQty as number,
            memo: row.memo || undefined
          }));
        const exported = await exportOrderLogicV2Excel(
          context.jobId,
          context.appliedMode,
          context.rowIds,
          overrides
        );
        triggerDownload(exported.blob, exported.filename);
      } catch (caught) {
        if (!isAbortError(caught)) {
          if (caught instanceof ApiRequestError && caught.status === 404) {
            setError(`${caught.message} 분석 실행을 다시 눌러 새로 계산해 주세요.`);
          } else {
            setError(caught instanceof Error ? caught.message : "Excel 내보내기에 실패했습니다.");
          }
        }
      } finally {
        setExportingExcel(false);
      }
    },
    [data, decisionDirtyIds]
  );

  return useMemo(
    () => ({
      entityCode: selectedEntity,
      data,
      settings,
      defaultSettings: sampleNewOrderLogicSettings,
      // Current FX is intentionally not requested. V2 receives the CMS
      // query-date KRW unit price per SKU and uses that actual amount directly.
      exchangeRateKrw: null,
      exchangeRateDate: null,
      exchangeRateSource: null,
      simulation,
      loading,
      running,
      cancelling,
      onCancelRun: cancelRun,
      simulating,
      applyingSettings,
      exportingExcel,
      error,
      onRun: run,
      onExportExcel: exportExcel,
      onSimulate: simulate,
      onApplySettings: applySettings,
      onConfirmedQtyChange: (rowId: string, quantity: number | null) => {
        setDecisionDirtyIds((current) => new Set(current).add(rowId));
        updateRow(rowId, { confirmedQty: quantity });
      },
      onMemoChange: (rowId: string, memo: string) => {
        setDecisionDirtyIds((current) => new Set(current).add(rowId));
        updateRow(rowId, { memo });
      }
    }),
    [
      applyingSettings,
      cancelRun,
      cancelling,
      data,
      error,
      exportExcel,
      exportingExcel,
      loading,
      run,
      running,
      selectedEntity,
      settings,
      simulate,
      simulating,
      simulation,
      applySettings,
      updateRow
    ]
  );
}
