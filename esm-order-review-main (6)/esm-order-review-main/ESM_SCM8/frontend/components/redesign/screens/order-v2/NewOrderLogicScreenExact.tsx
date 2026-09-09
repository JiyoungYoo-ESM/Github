"use client";

import {
  AlertCircle,
  Calculator,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Info,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2
} from "lucide-react";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode
} from "react";

import { cn } from "@/lib/utils";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import { OrderFormulaDrawer } from "./OrderFormulaDrawer";
import { useAnalysisElapsedLabel } from "../../shared/use-analysis-elapsed";

import type {
  NewOrderCurrencyCode,
  NewOrderDataStatus,
  NewOrderExportContext,
  NewOrderFilterState,
  NewOrderLeadTimeSetting,
  NewOrderLogicPolicySettings,
  NewOrderLogicRow,
  NewOrderLogicScreenProps,
  NewOrderLogicTab,
  NewOrderModeResult,
  NewOrderPolicyMode,
  NewOrderSignal
} from "./types";

const TAB_ITEMS: Array<{ id: NewOrderLogicTab; label: string }> = [
  { id: "proposal", label: "발주 제안" },
  { id: "comparison", label: "시나리오 비교" },
  { id: "settings", label: "설정" }
];

const EMPTY_FILTERS: NewOrderFilterState = {
  brand: "all"
};

const EXCLUDED_BRANDS = new Set(["기타제조사"]);

const numberFormatter = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 1
});

const integerFormatter = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 0
});

function cloneSettings(settings: NewOrderLogicPolicySettings): NewOrderLogicPolicySettings {
  return {
    ...settings,
    zMatrix: { ...settings.zMatrix },
    policyTransports: { ...settings.policyTransports },
    leadTimes: settings.leadTimes.map((item) => ({ ...item }))
  };
}

function restoreEditableSettings(
  current: NewOrderLogicPolicySettings,
  defaults: NewOrderLogicPolicySettings
): NewOrderLogicPolicySettings {
  return {
    ...current,
    policyMode: defaults.policyMode,
    gradeCutoffPct: defaults.gradeCutoffPct,
    coverWeeks: defaults.coverWeeks,
    safetyStockFloorWeeks: defaults.safetyStockFloorWeeks,
    safetyStockCapWeeks: defaults.safetyStockCapWeeks,
    zMatrix: { ...defaults.zMatrix },
    policyTransports: { ...defaults.policyTransports },
    leadTimes: defaults.leadTimes.map((item) => ({ ...item }))
  };
}

function modeLabel(mode: NewOrderPolicyMode) {
  return mode === "SHORTAGE" ? "쇼티지 방어" : "현금흐름 우선";
}

function otherMode(mode: NewOrderPolicyMode): NewOrderPolicyMode {
  return mode === "SHORTAGE" ? "CASH" : "SHORTAGE";
}

function quantityOrZero(value: number | null | undefined) {
  return value ?? 0;
}

function decisionValidationMessage(
  row: NewOrderLogicRow,
  quantityValue: string
) {
  if (!row.isCalculable) return null;
  if (quantityValue.trim() === "") return "확정수량을 입력해 주세요.";
  const quantity = Number(quantityValue);
  if (!Number.isFinite(quantity) || quantity < 0) {
    return "확정수량은 0 이상의 숫자여야 합니다.";
  }
  if (!Number.isInteger(quantity)) {
    return "확정수량은 낱개 단위의 정수여야 합니다.";
  }
  return null;
}

function decisionMessageId(
  instanceId: string,
  rowId: string,
  surface: "mobile" | "desktop"
) {
  return `${instanceId}-decision-${surface}-${rowId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function formatInteger(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "-"
    : integerFormatter.format(Math.round(value));
}

function formatDecimal(value: number | null | undefined, suffix = "") {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "-"
    : `${numberFormatter.format(value)}${suffix}`;
}

function formatCurrency(
  value: number | null | undefined,
  currencyCode: NewOrderCurrencyCode
) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  // KRW has no minor unit, so it is shown as a whole-won amount.
  if (currencyCode === "KRW") {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency: "KRW",
      maximumFractionDigits: 0
    }).format(value);
  }
  return new Intl.NumberFormat(currencyCode === "USD" ? "en-US" : "en-IE", {
    style: "currency",
    currency: currencyCode,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function formatCompactKrw(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const sign = value < 0 ? "-" : "";
  const absoluteValue = Math.abs(value);
  if (absoluteValue >= 100_000_000) {
    return `${sign}₩${numberFormatter.format(absoluteValue / 100_000_000)}억`;
  }
  if (absoluteValue >= 10_000) {
    return `${sign}₩${numberFormatter.format(absoluteValue / 10_000)}만`;
  }
  return `${sign}₩${integerFormatter.format(Math.round(absoluteValue))}`;
}

// 원천 금액을 원화로 바꾸는 계수. 본사(KRW)는 원천이 이미 원화라 환산이
// 없으므로 1이며, 환율 조회 실패와 구분해야 한다. 이 값이 null이면 원화
// 금액을 만들 수 없다는 뜻이다.
function krwConversionFactor(
  currencyCode: NewOrderCurrencyCode,
  exchangeRateKrw: number | null
): number | null {
  if (currencyCode === "KRW") return 1;
  return exchangeRateKrw;
}

function resolvedKrwAmount(
  result: NewOrderModeResult,
  fallbackFactor: number | null
) {
  if (
    result.referenceAmountKrw !== null &&
    result.referenceAmountKrw !== undefined &&
    Number.isFinite(result.referenceAmountKrw)
  ) {
    return result.referenceAmountKrw;
  }
  if (
    result.referenceAmountEur === null ||
    result.referenceAmountEur === undefined ||
    !Number.isFinite(result.referenceAmountEur) ||
    fallbackFactor === null
  ) {
    return null;
  }
  return result.referenceAmountEur * fallbackFactor;
}

function priceMissingModesForComparison(
  row: NewOrderLogicRow,
  modes: readonly NewOrderPolicyMode[],
  fallbackFactor: number | null
): NewOrderPolicyMode[] {
  return modes.filter((mode) => {
    const result = getModeResult(row, mode);
    return (
      quantityOrZero(result.suggestedQty) > 0 &&
      resolvedKrwAmount(result, fallbackFactor) === null
    );
  });
}

function formatTimestamp(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatPeriodDate(value);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "-";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatPeriodDate(value: string) {
  if (!value) return "-";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[1]}.${match[2]}.${match[3]}` : value;
}

function dataStatusClass(status: NewOrderDataStatus) {
  if (status === "정상") return "border-pos-border bg-pos-bg text-pos-strong";
  if (status === "확인필요") return "border-warn-border bg-warn-bg text-warn-strong";
  if (status === "판매없음") return "border-border bg-row text-muted";
  if (status === "확인(간헐)") return "border-warn-border bg-warn-bg text-warn-strong";
  if (status === "대량포함") return "border-brand/20 bg-brand-50 text-brand";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function signalClass(signal: NewOrderSignal) {
  if (signal === "발주") return "border-brand/20 bg-brand-50 text-brand";
  if (signal === "확인후발주") return "border-warn-border bg-warn-bg text-warn-strong";
  if (signal === "-") return "border-border bg-row text-muted";
  return "border-pos-border bg-pos-bg text-pos-strong";
}

function modeClass(mode: NewOrderPolicyMode, official = false) {
  if (mode === "SHORTAGE") {
    return official
      ? "border-brand bg-brand text-white"
      : "border-brand/20 bg-brand-50 text-brand";
  }
  return official
    ? "border-blue-700 bg-blue-700 text-white"
    : "border-blue-200 bg-blue-50 text-blue-700";
}

function DataStatusBadge({ status }: { status: NewOrderDataStatus }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-[7px] border px-2 text-[11px] font-black",
        dataStatusClass(status)
      )}
    >
      {status}
    </span>
  );
}

function SignalBadge({ signal }: { signal: NewOrderSignal }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-[7px] border px-2 text-[11px] font-black",
        signalClass(signal)
      )}
      aria-label={signal === "-" ? "발주신호 없음" : undefined}
      title={signal === "-" ? "계산불가 또는 판매없음" : undefined}
    >
      {signal === "-" ? "–" : signal}
    </span>
  );
}

function PolicyModeBadge({
  mode,
  official = false
}: {
  mode: NewOrderPolicyMode;
  official?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-full border px-2.5 text-[11px] font-black",
        modeClass(mode, official)
      )}
    >
      {modeLabel(mode)}
      {official ? " · 적용" : " · 비교"}
    </span>
  );
}

function MetricCard({
  label,
  value,
  caption,
  title,
  assistiveText,
  tone = "default"
}: {
  label: string;
  value: string;
  caption?: string;
  title?: string;
  assistiveText?: string;
  tone?: "default" | "brand" | "amber" | "green";
}) {
  const toneClass =
    tone === "brand"
      ? "text-brand"
      : tone === "amber"
        ? "text-warn-strong"
        : tone === "green"
          ? "text-pos-strong"
          : "text-ink";
  return (
    <section
      className="min-h-[116px] rounded-[14px] border border-border bg-surface px-5 py-[18px] shadow-card"
      title={title}
    >
      <p className="text-[12px] font-black text-muted">{label}</p>
      <p className={cn("mt-[10px] tnum text-[27px] font-black leading-none", toneClass)}>
        {value}
      </p>
      {caption ? (
        <p className="mt-[9px] text-[11.5px] font-semibold text-muted2">{caption}</p>
      ) : null}
      {assistiveText ? <span className="sr-only">{assistiveText}</span> : null}
    </section>
  );
}

function MetaChip({
  label,
  value,
  title,
  emphasized = false
}: {
  label: string;
  value: string;
  title?: string;
  emphasized?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex min-h-8 items-center gap-1.5 rounded-[9px] border px-3 text-[11.5px] font-bold",
        emphasized ? "border-brand/20 bg-brand-50 text-brand" : "border-border bg-surface text-ink3"
      )}
      title={title}
    >
      <span className={emphasized ? "text-brand/70" : "text-muted2"}>{label}</span>
      <span className={cn("font-black", emphasized ? "text-brand" : "text-ink")}>{value}</span>
    </span>
  );
}

function StatePanel({
  title,
  description,
  tone = "default",
  action
}: {
  title: string;
  description: string;
  tone?: "default" | "error" | "loading";
  action?: ReactNode;
}) {
  const Icon = tone === "error" ? AlertCircle : tone === "loading" ? Loader2 : FileSpreadsheet;
  return (
    <section
      className={cn(
        "rounded-[16px] border bg-surface px-5 py-16 text-center shadow-soft",
        tone === "error" ? "border-brand/20" : "border-border"
      )}
      role={tone === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <Icon
        className={cn(
          "mx-auto h-8 w-8",
          tone === "error" ? "text-brand" : "text-muted2",
          tone === "loading" && "animate-spin"
        )}
        aria-hidden="true"
      />
      <h3 className="mt-4 text-[15px] font-black text-ink">{title}</h3>
      <p className="mx-auto mt-2 max-w-[560px] text-[12.5px] font-semibold leading-5 text-muted">
        {description}
      </p>
      {action ? <div className="mt-5 flex justify-center">{action}</div> : null}
    </section>
  );
}

function NumberField({
  label,
  value,
  onChange,
  caption,
  unit,
  min,
  max,
  step = 1,
  disabled = false
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  caption?: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  const fieldId = useId();
  return (
    <label htmlFor={fieldId} className="block">
      <span className="block text-[12px] font-black text-ink3">{label}</span>
      {caption ? (
        <span className="mt-1 block text-[11px] font-semibold leading-4 text-muted2">
          {caption}
        </span>
      ) : null}
      <span className="relative mt-2 block">
        <input
          id={fieldId}
          type="number"
          inputMode="decimal"
          value={Number.isFinite(value) ? value : ""}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(event) => {
            const parsed = Number(event.target.value);
            if (Number.isFinite(parsed)) onChange(parsed);
          }}
          className="h-10 w-full rounded-[9px] border border-border bg-surface px-3 pr-12 text-right text-[13px] font-black text-ink outline-none transition disabled:cursor-not-allowed disabled:bg-surface-soft disabled:text-muted focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/20"
        />
        {unit ? (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[11px] font-black text-muted2">
            {unit}
          </span>
        ) : null}
      </span>
    </label>
  );
}

// 서비스 수준(Z) 선택지. 회사 표준 Z-테이블의 등급·Z값·서비스 수준(%)을
// 그대로 옮긴 고정 목록이며, 사용자는 이 목록 안에서만 고를 수 있다.
// 임의의 소수값 입력은 여기 없는 산식 기준값을 만들 수 있어 막는다.
const Z_SERVICE_LEVEL_OPTIONS: { z: number; servicePct: number; grade: string }[] = [
  { z: 0.84, servicePct: 80.0, grade: "C급 (저가·저회전)" },
  { z: 1.04, servicePct: 85.0, grade: "C+급 (일반 자재)" },
  { z: 1.08, servicePct: 86.0, grade: "현금흐름 우선 · 일반 SKU 기존 기준값" },
  { z: 1.28, servicePct: 90.0, grade: "B급 (표준 품목)" },
  { z: 1.34, servicePct: 91.0, grade: "B급 중상위" },
  { z: 1.41, servicePct: 92.0, grade: "B급 중상위 관리" },
  { z: 1.48, servicePct: 93.0, grade: "B급 준핵심 관리" },
  { z: 1.55, servicePct: 94.0, grade: "B급 준핵심 관리" },
  { z: 1.65, servicePct: 95.0, grade: "A급 (주력·핵심)" },
  { z: 1.68, servicePct: 95.35, grade: "A급 (현장 표준)" },
  { z: 1.75, servicePct: 96.0, grade: "A급 고변동성 품목" },
  { z: 1.88, servicePct: 97.0, grade: "A급 고변동성 품목" },
  { z: 2.05, servicePct: 98.0, grade: "A+급 (고가·히트)" },
  { z: 2.33, servicePct: 99.0, grade: "S급 (전략 품목)" },
  { z: 3.09, servicePct: 99.9, grade: "SS급 (절대 품절 불가)" }
];

function formatZValue(z: number) {
  return z.toFixed(2);
}

function formatServicePct(pct: number) {
  // 95.35%처럼 소수 둘째 자리가 의미 있는 값은 그대로 보여주고, 90%처럼
  // 소수부가 없는 값은 불필요한 0을 남기지 않는다.
  return pct.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function zServiceLevelLabel(z: number) {
  const match = Z_SERVICE_LEVEL_OPTIONS.find((option) => option.z === z);
  return match ? `${formatServicePct(match.servicePct)}%` : "목록 외 값";
}

function ZLevelSelect({
  label,
  value,
  onChange,
  defaultZ
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  defaultZ?: number;
}) {
  const fieldId = useId();
  // 기존 저장값이 표준 목록에 없으면(예: 과거 기본값 1.08) 그 값도 선택지에
  // 끼워 넣어 데이터를 잃지 않고 그대로 보여준다.
  const options = Z_SERVICE_LEVEL_OPTIONS.some((option) => option.z === value)
    ? Z_SERVICE_LEVEL_OPTIONS
    : [...Z_SERVICE_LEVEL_OPTIONS, { z: value, servicePct: NaN, grade: "" }].sort(
        (a, b) => a.z - b.z
      );
  return (
    <label htmlFor={fieldId} className="block">
      <span className="block text-[12px] font-black text-ink3">{label}</span>
      <span className="relative mt-2 block">
        <select
          id={fieldId}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="h-10 w-full appearance-none rounded-[9px] border border-border bg-surface px-3 pr-9 text-right text-[13px] font-black text-ink outline-none transition focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/20"
        >
          {options.map((option) => (
            <option key={option.z} value={option.z}>
              {formatZValue(option.z)}
              {Number.isFinite(option.servicePct)
                ? ` · 서비스 수준 ${formatServicePct(option.servicePct)}%`
                : " · 목록 외 값"}
              {option.z === defaultZ ? " (기본값)" : ""}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted2"
          aria-hidden="true"
        />
      </span>
      <span className="mt-1 block text-[11px] font-semibold leading-4 text-muted2">
        서비스 수준 {zServiceLevelLabel(value)}
        {value === defaultZ ? " (기본값)" : ""}
      </span>
    </label>
  );
}

function Pagination({
  page,
  totalPages,
  pageSize,
  totalRows,
  onPageChange,
  onPageSizeChange
}: {
  page: number;
  totalPages: number;
  pageSize: number;
  totalRows: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-divider bg-surface-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2 text-[11.5px] font-bold text-muted">
        <span>총 {integerFormatter.format(totalRows)}개</span>
        <label className="inline-flex items-center gap-2">
          <span>페이지당</span>
          <select
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className="h-8 rounded-[8px] border border-border bg-surface px-2 text-[11.5px] font-black text-ink outline-none focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/20"
            aria-label="페이지당 행 수"
          >
            {[20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex items-center justify-between gap-2 sm:justify-end">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(page - 1, 1))}
          disabled={page <= 1}
          className="inline-flex h-9 items-center gap-1 rounded-[9px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          이전
        </button>
        <span className="min-w-[72px] text-center text-[12px] font-black text-muted">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(Math.min(page + 1, totalPages))}
          disabled={page >= totalPages}
          className="inline-flex h-9 items-center gap-1 rounded-[9px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
        >
          다음
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function ValidationNotice({ errors }: { errors: string[] }) {
  if (errors.length === 0) return null;
  return (
    <div
      className="rounded-[12px] border border-brand/20 bg-brand-50 px-4 py-3"
      role="alert"
    >
      <p className="flex items-center gap-2 text-[12px] font-black text-brand">
        <AlertCircle className="h-4 w-4" aria-hidden="true" />
        설정값을 확인해 주세요.
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-[11.5px] font-semibold leading-4 text-brand">
        {errors.map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}

function getModeResult(row: NewOrderLogicRow, mode: NewOrderPolicyMode): NewOrderModeResult {
  return row.modes[mode];
}

function SettingsCard({
  title,
  description,
  children,
  className
}: {
  title: string;
  description: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft",
        className
      )}
    >
      <header className="border-b border-divider px-5 py-4">
        <h3 className="text-[13px] font-black text-ink">{title}</h3>
        <p className="mt-1 text-[11.5px] font-semibold leading-4 text-muted2">{description}</p>
      </header>
      <div className="space-y-4 p-5">{children}</div>
    </section>
  );
}

function etaReferenceText(row: NewOrderLogicRow): string {
  if (row.nextEta) {
    return `${row.nextEtaStatus} ${formatPeriodDate(row.nextEta)}`;
  }
  return row.nextEtaStatus;
}

export function NewOrderLogicScreenExact({
  entityCode = null,
  data = null,
  settings,
  defaultSettings,
  exchangeRateKrw = null,
  exchangeRateDate = null,
  exchangeRateSource = null,
  loading = false,
  running = false,
  cancelling = false,
  applyingSettings = false,
  exportingExcel = false,
  error = null,
  canViewAmountData = false,
  canEditAdvancedSettings = false,
  className,
  onRetry,
  onRun,
  onCancelRun,
  onExportExcel,
  onSettingsChange,
  onApplySettings,
  onConfirmedQtyChange,
  onMemoChange
}: NewOrderLogicScreenProps) {
  const instanceId = useId().replace(/:/g, "");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const formulaTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [activeTab, setActiveTab] = useState<NewOrderLogicTab>("proposal");
  const [filters, setFilters] = useState<NewOrderFilterState>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [draftSettings, setDraftSettings] = useState<NewOrderLogicPolicySettings>(() =>
    cloneSettings(settings)
  );
  const [viewMode, setViewMode] = useState<NewOrderPolicyMode>(settings.policyMode);
  const [confirmedQtyDrafts, setConfirmedQtyDrafts] = useState<Record<string, string>>({});
  const [memoDrafts, setMemoDrafts] = useState<Record<string, string>>({});
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [formulaDrawerOpen, setFormulaDrawerOpen] = useState(false);
  const [analysisCompletedAt, setAnalysisCompletedAt] = useState<Date | null>(null);
  const analysisWasRunningRef = useRef(false);
  const analysisElapsedLabel = useAnalysisElapsedLabel(running);

  useEffect(() => {
    setDraftSettings(cloneSettings(settings));
  }, [settings]);

  useEffect(() => {
    setViewMode(data?.meta.appliedMode ?? settings.policyMode);
  }, [data?.meta.appliedMode, data?.meta.jobId, settings.policyMode]);

  // 법인을 바꾸면 이 컴포넌트는 유지되므로, 이전 법인의 완료 표시를
  // 다음 법인 화면에 남기지 않는다.
  useEffect(() => {
    analysisWasRunningRef.current = false;
    setAnalysisCompletedAt(null);
  }, [entityCode]);

  useEffect(() => {
    if (running) {
      analysisWasRunningRef.current = true;
      setAnalysisCompletedAt(null);
      return;
    }
    if (!analysisWasRunningRef.current) return;
    analysisWasRunningRef.current = false;
    if (error || !data?.meta.jobId) return;
    setAnalysisCompletedAt(new Date());
  }, [data?.meta.jobId, error, running]);

  useEffect(() => {
    const rows = data?.rows ?? [];
    setConfirmedQtyDrafts(
      Object.fromEntries(
        rows.map((row) => [
          row.id,
          row.confirmedQty === null || row.confirmedQty === undefined
            ? ""
            : String(row.confirmedQty)
        ])
      )
    );
    setMemoDrafts(Object.fromEntries(rows.map((row) => [row.id, row.memo ?? ""])));
  }, [data?.meta.jobId, data?.rows]);

  const officialMode = data?.meta.appliedMode ?? settings.policyMode;
  const appliedMode = data ? viewMode : settings.policyMode;
  const referenceMode = otherMode(appliedMode);
  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const visibleRows = useMemo(
    () => rows.filter((row) => !EXCLUDED_BRANDS.has(row.brand.trim())),
    [rows]
  );

  const brandOptions = useMemo(
    () =>
      Array.from(new Set(visibleRows.map((row) => row.brand).filter(Boolean))).sort((left, right) =>
        left.localeCompare(right, "ko")
      ),
    [visibleRows]
  );

  const filteredRows = useMemo(() => {
    return visibleRows.filter((row) => {
      if (filters.brand !== "all" && row.brand !== filters.brand) return false;
      return true;
    });
  }, [filters.brand, visibleRows]);

  const proposalRows = useMemo(
    () =>
      [...filteredRows].sort((left, right) => {
        const leftResult = getModeResult(left, appliedMode);
        const rightResult = getModeResult(right, appliedMode);
        if (canViewAmountData) {
          const leftAmount = leftResult.referenceAmountEur;
          const rightAmount = rightResult.referenceAmountEur;
          const leftHasAmount =
            leftAmount !== null &&
            leftAmount !== undefined &&
            Number.isFinite(leftAmount);
          const rightHasAmount =
            rightAmount !== null &&
            rightAmount !== undefined &&
            Number.isFinite(rightAmount);
          if (leftHasAmount !== rightHasAmount) return leftHasAmount ? -1 : 1;
          if (leftHasAmount && rightHasAmount && leftAmount !== rightAmount) {
            return rightAmount - leftAmount;
          }
        }
        // 금액 권한이 없는 계정에는 금액순 자체가 정보 노출이 될 수 있으므로
        // 화면에 보이는 발주신호와 제안수량만 사용해 정렬한다.
        const signalRank: Record<NewOrderSignal, number> = {
          발주: 0,
          확인후발주: 1,
          충분: 2,
          "-": 3
        };
        return (
          signalRank[leftResult.signal] - signalRank[rightResult.signal] ||
          quantityOrZero(rightResult.suggestedQty) -
            quantityOrZero(leftResult.suggestedQty) ||
          left.productCode.localeCompare(right.productCode)
        );
      }),
    [appliedMode, canViewAmountData, filteredRows]
  );

  const comparisonRows = useMemo(
    () =>
      [...filteredRows].sort((left, right) => {
        const leftDiff =
          quantityOrZero(getModeResult(left, appliedMode).suggestedQty) -
          quantityOrZero(getModeResult(left, referenceMode).suggestedQty);
        const rightDiff =
          quantityOrZero(getModeResult(right, appliedMode).suggestedQty) -
          quantityOrZero(getModeResult(right, referenceMode).suggestedQty);
        return Math.abs(rightDiff) - Math.abs(leftDiff);
      }),
    [appliedMode, filteredRows, referenceMode]
  );

  const currencyCode = data?.meta.currencyCode ?? "EUR";
  const krwFactor = krwConversionFactor(currencyCode, exchangeRateKrw);

  const officialSummary = useMemo(() => {
    let orderSkuCount = 0;
    let confirmSkuCount = 0;
    let totalSuggestedQty = 0;
    let totalReferenceAmountKrw = 0;
    let amountCoverageCount = 0;
    let amountRequiredCount = 0;
    for (const row of filteredRows) {
      const result = getModeResult(row, appliedMode);
      if (result.signal === "발주") orderSkuCount += 1;
      if (result.signal === "확인후발주") confirmSkuCount += 1;
      totalSuggestedQty += quantityOrZero(result.suggestedQty);
      if (quantityOrZero(result.suggestedQty) > 0) {
        amountRequiredCount += 1;
      }
      const krwAmount = resolvedKrwAmount(result, krwFactor);
      if (quantityOrZero(result.suggestedQty) > 0 && krwAmount !== null) {
        totalReferenceAmountKrw += krwAmount;
        amountCoverageCount += 1;
      }
    }
    return {
      orderSkuCount,
      confirmSkuCount,
      totalSuggestedQty,
      totalReferenceAmountKrw:
        amountRequiredCount > 0 && amountCoverageCount === 0
          ? null
          : totalReferenceAmountKrw,
      amountCoverageCount,
      amountRequiredCount
    };
  }, [appliedMode, filteredRows, krwFactor]);

  const isHqEntity =
    String(entityCode ?? "").trim().toUpperCase() === "HQ" ||
    data?.meta.entityCode === "HQ" ||
    data?.meta.warehouseCode === "OPO" ||
    data?.meta.periodUnit === "day";
  // 본사는 원천이 원화라 환산계수가 1이고, 그 외 법인은 조회 환율이 필요하다.
  const headquartersWarehouseLabel =
    currencyCode === "KRW" ? "오포" : currencyCode === "USD" ? "미주" : "EU";
  const incomingInventoryLabel = "미입고/입고예정 수량";
  const demandAverageLabel = isHqEntity ? "일평균" : "주평균";
  const depletionReferenceLabel = isHqEntity
    ? "고갈일수(참고)"
    : "고갈주수(참고)";
  const depletionUnit = isHqEntity ? "일" : "주";
  const depletionReferenceTitle = isHqEntity
    ? "오포가용 ÷ 일평균으로 산출한 참고값"
    : "(현지가용 + 운송중) ÷ 주평균으로 산출한 참고값";
  const usesCmsKrwUnitCost = filteredRows.some(
    (row) => row.unitPriceKrw !== null && row.unitPriceKrw !== undefined
  );
  const exchangeRateTitle = currencyCode === "KRW"
    ? "본사 발주금액은 원화 원천값이라 환율을 적용하지 않습니다."
    : usesCmsKrwUnitCost
    ? "CMS 재고 API의 조회 기준일 원화 단가(unit_cost_krw)를 적용했습니다."
    : exchangeRateKrw
    ? `${currencyCode} 기준금액 × ${integerFormatter.format(exchangeRateKrw)}원${
        exchangeRateDate ? ` · ${formatPeriodDate(exchangeRateDate)}` : ""
      } · ${exchangeRateSource === "api" ? "자동 조회" : "기본 환율"}`
    : `${currencyCode}/KRW 환율을 조회하지 못해 원화 금액을 표시할 수 없습니다.`;
  const localProposalAmountLabel = `제안금액 (${currencyCode})`;
  const showKrwProposalAmount = canViewAmountData && currencyCode !== "KRW";

  const amountDataMissingCount =
    officialSummary.amountRequiredCount - officialSummary.amountCoverageCount;

  const comparisonSummary = useMemo(() => {
    let appliedQty = 0;
    let referenceQty = 0;
    let appliedAmount = 0;
    let referenceAmountEur = 0;
    const missingAmountRows: Array<{
      productCode: string;
      modes: NewOrderPolicyMode[];
    }> = [];
    for (const row of filteredRows) {
      const applied = getModeResult(row, appliedMode);
      const reference = getModeResult(row, referenceMode);
      appliedQty += quantityOrZero(applied.suggestedQty);
      referenceQty += quantityOrZero(reference.suggestedQty);
      const appliedKrw = resolvedKrwAmount(applied, krwFactor);
      const referenceKrw = resolvedKrwAmount(reference, krwFactor);
      appliedAmount += appliedKrw ?? 0;
      referenceAmountEur += referenceKrw ?? 0;
      const missingModes = priceMissingModesForComparison(
        row,
        [appliedMode, referenceMode],
        krwFactor
      );
      if (missingModes.length > 0) {
        missingAmountRows.push({
          productCode: row.productCode,
          modes: missingModes
        });
      }
    }
    return {
      appliedQty,
      referenceQty,
      qtyDifference: appliedQty - referenceQty,
      appliedAmount,
      referenceAmountEur,
      missingAmountRows,
      amountDifference: missingAmountRows.length === 0
        ? appliedAmount - referenceAmountEur
        : null
    };
  }, [appliedMode, filteredRows, krwFactor, referenceMode]);

  const currentRows = activeTab === "comparison" ? comparisonRows : proposalRows;
  const totalPages = Math.max(Math.ceil(currentRows.length / pageSize), 1);
  const currentPage = Math.min(page, totalPages);
  const pagedRows = useMemo(
    () => currentRows.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [currentPage, currentRows, pageSize]
  );
  const decisionErrorsById = useMemo(() => {
    const errors = new Map<string, string>();
    for (const row of rows) {
      const quantityValue =
        confirmedQtyDrafts[row.id] ??
        (row.confirmedQty === null || row.confirmedQty === undefined
          ? ""
          : String(row.confirmedQty));
      const message = decisionValidationMessage(row, quantityValue);
      if (message) errors.set(row.id, message);
    }
    return errors;
  }, [confirmedQtyDrafts, rows]);
  const exportDecisionErrorCount = currentRows.reduce(
    (count, row) => count + (decisionErrorsById.has(row.id) ? 1 : 0),
    0
  );
  const actionBusy = running || applyingSettings || exportingExcel;

  useEffect(() => {
    setPage(1);
  }, [activeTab, filters.brand, pageSize]);

  const validationErrors = useMemo(() => {
    const errors: string[] = [];
    // 본사는 일 단위 국내조달 리드타임만 쓰고 주 단위 정책값과 운송수단
    // 리드타임을 갖지 않는다. HQ 실측값은 분석 실행 시 서버가 재조회하므로
    // 현재 화면에서 실측값이 unavailable인 상태는 실행 차단 오류로 보지 않는다.
    const isDomesticLeadTimeEntity = Boolean(draftSettings.domesticLeadTime);
    if (
      draftSettings.gradeCutoffPct <= 0 ||
      draftSettings.gradeCutoffPct >= 100
    ) {
      errors.push("주력 SKU 매출 기준은 0% 초과 100% 미만이어야 합니다.");
    }
    if (
      !isDomesticLeadTimeEntity &&
      (!Number.isFinite(draftSettings.coverWeeks) || draftSettings.coverWeeks < 0)
    ) {
      errors.push("추가 확보 재고는 0주 이상이어야 합니다.");
    }
    if (
      !isDomesticLeadTimeEntity &&
      (
      draftSettings.safetyStockFloorWeeks < 0 ||
      draftSettings.safetyStockCapWeeks < draftSettings.safetyStockFloorWeeks)
    ) {
      errors.push("안전재고 상한은 하한보다 크거나 같아야 합니다.");
    }
    if (
      Object.values(draftSettings.zMatrix).some(
        (value) => !Number.isFinite(value) || value <= 0
      )
    ) {
      errors.push("서비스 수준 Z값은 모두 0보다 커야 합니다.");
    }
    if (
      !isDomesticLeadTimeEntity &&
      draftSettings.leadTimes.some(
        (item) =>
          !Number.isFinite(item.meanDays) ||
          item.meanDays <= 0 ||
          !Number.isFinite(item.sigmaWeeks) ||
          item.sigmaWeeks < 0
      )
    ) {
      errors.push("리드타임 평균은 0보다 커야 하고 σL은 0 이상이어야 합니다.");
    }
    return errors;
  }, [draftSettings]);

  const settingsChanged =
    JSON.stringify(draftSettings) !== JSON.stringify(settings);

  const updateDraftSettings = (next: NewOrderLogicPolicySettings) => {
    setAnalysisCompletedAt(null);
    setDraftSettings(next);
    onSettingsChange?.(next);
  };

  const updateLeadTime = (
    code: string,
    field: keyof Pick<NewOrderLeadTimeSetting, "meanDays" | "sigmaWeeks">,
    value: number
  ) => {
    updateDraftSettings({
      ...draftSettings,
      leadTimes: draftSettings.leadTimes.map((item) =>
        item.code === code ? { ...item, [field]: value } : item
      )
    });
  };

  const updateFilter = <Key extends keyof NewOrderFilterState>(
    key: Key,
    value: NewOrderFilterState[Key]
  ) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const selectTab = (tab: NewOrderLogicTab) => {
    setActiveTab(tab);
  };

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number
  ) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let nextIndex = index;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % TAB_ITEMS.length;
    if (event.key === "ArrowLeft") {
      nextIndex = (index - 1 + TAB_ITEMS.length) % TAB_ITEMS.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = TAB_ITEMS.length - 1;
    const nextTab = TAB_ITEMS[nextIndex];
    selectTab(nextTab.id);
    tabRefs.current[nextIndex]?.focus();
  };

  const selectPolicyMode = (mode: NewOrderPolicyMode) => {
    if (mode === draftSettings.policyMode) return;
    updateDraftSettings({ ...draftSettings, policyMode: mode });
  };

  const switchViewScenario = (mode: NewOrderPolicyMode) => {
    setViewMode(mode);
  };

  const handleExport = () => {
    if (!onExportExcel || exportingExcel || currentRows.length === 0) return;
    setExportMenuOpen(false);
    const context: NewOrderExportContext = {
      jobId: data?.meta.jobId ?? null,
      tab: activeTab,
      appliedMode,
      filters,
      rowIds: currentRows.map((row) => row.id)
    };
    void onExportExcel(context);
  };

  const handleConfirmedQtyChange = (row: NewOrderLogicRow, value: string) => {
    if (!row.isCalculable) return;
    setConfirmedQtyDrafts((current) => ({ ...current, [row.id]: value }));
    const parsed = value.trim() === "" ? null : Number(value);
    if (parsed === null || (Number.isFinite(parsed) && parsed >= 0)) {
      onConfirmedQtyChange?.(row.id, parsed);
    }
  };

  const handleMemoChange = (row: NewOrderLogicRow, value: string) => {
    if (!row.isCalculable) return;
    setMemoDrafts((current) => ({ ...current, [row.id]: value }));
    onMemoChange?.(row.id, value);
  };

  const renderResultState = (content: ReactNode) => {
    if (loading) {
      return (
        <StatePanel
          tone="loading"
          title="발주 결과를 불러오는 중입니다"
          description="동일한 데이터 snapshot과 적용 시나리오를 확인하고 있습니다."
        />
      );
    }
    if (error && !data) {
      return (
        <StatePanel
          tone="error"
          title="발주 작업을 완료하지 못했습니다"
          description={error}
          action={
            onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex h-10 items-center gap-2 rounded-[9px] bg-ink px-4 text-[12px] font-black text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                다시 시도
              </button>
            ) : null
          }
        />
      );
    }
    if (!data) {
      return (
        <StatePanel
          title="아직 실행된 발주 분석이 없습니다"
          description="적용 시나리오와 산식 기준을 확인한 뒤 분석 실행을 누르면 발주 제안과 두 시나리오 비교가 표시됩니다."
        />
      );
    }
    if (rows.length === 0) {
      return (
        <StatePanel
          title="표시할 발주 결과가 없습니다"
          description="분석은 완료됐지만 결과 행이 없습니다. 입력 데이터 범위와 제외 조건을 확인해 주세요."
        />
      );
    }
    return content;
  };

  const filterBar = (
    <section className="mb-4 rounded-[14px] border border-border bg-surface p-3 shadow-soft">
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="발주 결과 필터"
      >
          <BrandSearchSelect
            value={filters.brand}
            options={brandOptions}
            allValue="all"
            buttonLabel={filters.brand === "all" ? "브랜드: 전체" : filters.brand}
            onChange={(value) => updateFilter("brand", value)}
          />
      </div>
      {filters.brand !== "all" ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-divider pt-3 text-[11.5px] font-bold text-muted">
          <span>
            전체 {integerFormatter.format(rows.length)}개 중{" "}
            <strong className="text-ink">
              {integerFormatter.format(filteredRows.length)}개
            </strong>
          </span>
        </div>
      ) : null}
    </section>
  );

  const proposalPanel = renderResultState(
    <>
      <div className="mb-4 grid gap-[14px] md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="즉시발주 SKU"
          value={formatInteger(officialSummary.orderSkuCount)}
          tone="brand"
        />
        <MetricCard
          label="발주필요 SKU"
          value={formatInteger(officialSummary.confirmSkuCount)}
          tone="amber"
        />
        <MetricCard
          label="총 발주필요수량"
          value={formatInteger(officialSummary.totalSuggestedQty)}
        />
        {canViewAmountData ? (
          <MetricCard
            label="총 발주필요금액"
            value={formatCompactKrw(
              officialSummary.totalReferenceAmountKrw
            )}
            title={exchangeRateTitle}
            assistiveText={exchangeRateTitle}
          />
        ) : (
          <MetricCard
            label="데이터 확인 SKU"
            value={formatInteger(
              rows.filter((row) => row.dataStatus !== "정상").length
            )}
            caption="판매없음 · 간헐 · 대량포함 · 이력부족"
          />
        )}
      </div>

      {canViewAmountData && amountDataMissingCount > 0 ? (
        <div
          className="mb-4 rounded-[12px] border border-warn-border bg-warn-bg px-4 py-3 text-[11.5px] font-semibold leading-5 text-warn-strong"
          role="status"
        >
          {`원화 단가가 없는 발주 대상 ${integerFormatter.format(
                amountDataMissingCount
              )}개 SKU는 총 발주필요금액에서 제외되었습니다.`}
        </div>
      ) : null}

      {filterBar}

      {proposalRows.length === 0 ? (
        <StatePanel
          title="조건에 맞는 SKU가 없습니다"
          description="검색어나 필터를 초기화해 다른 결과를 확인해 주세요."
          action={
            <button
              type="button"
              onClick={() => setFilters(EMPTY_FILTERS)}
              className="inline-flex h-10 items-center gap-2 rounded-[9px] border border-border bg-surface px-4 text-[12px] font-black text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              필터 초기화
            </button>
          }
        />
      ) : (
        <>
          <div className="space-y-3 lg:hidden">
            {pagedRows.map((row) => {
              const result = getModeResult(row, appliedMode);
              const quantityValue =
                confirmedQtyDrafts[row.id] ??
                (row.confirmedQty === null || row.confirmedQty === undefined
                  ? ""
                  : String(row.confirmedQty));
              const memoValue = memoDrafts[row.id] ?? row.memo ?? "";
              const decisionError = decisionErrorsById.get(row.id);
              const decisionMessage =
                row.decisionLockReason || decisionError;
              const decisionMessageElementId = decisionMessage
                ? decisionMessageId(instanceId, row.id, "mobile")
                : undefined;
              return (
                <article
                  key={row.id}
                  className="rounded-[14px] border border-border bg-surface p-4 shadow-soft"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-black text-brand">
                        {row.productCode}
                      </p>
                      <h3 className="mt-1 text-[14px] font-black leading-5 text-ink">
                        {row.productName}
                      </h3>
                      <p className="mt-1 text-[11.5px] font-semibold text-muted">
                        {row.brand || "브랜드 미등록"} · {row.grade ?? "등급 미분류"}
                      </p>
                    </div>
                    <SignalBadge signal={result.signal} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <DataStatusBadge status={row.dataStatus} />
                    <PolicyModeBadge mode={appliedMode} official />
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-divider py-3 text-[12px]">
                    <div>
                      <dt className="text-muted">{demandAverageLabel}</dt>
                      <dd className="mt-1 tnum font-black text-ink">
                        {formatDecimal(row.weeklyMean)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted">보유전체(IP)</dt>
                      <dd className="mt-1 tnum font-black text-ink">
                        {formatInteger(row.inventoryPosition)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted">목표 보유량</dt>
                      <dd className="mt-1 tnum font-black text-ink">
                        {formatInteger(result.targetStock)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted">{incomingInventoryLabel} 제외 보유</dt>
                      <dd className="mt-1 tnum font-black text-ink">
                        {formatInteger(row.inventoryPositionWithoutIncoming)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted">제안수량</dt>
                      <dd className="mt-1 tnum font-black text-brand">
                        {formatInteger(result.suggestedQty)}
                      </dd>
                    </div>
                  </dl>
                  {decisionMessage ? (
                    <p
                      id={decisionMessageElementId}
                      className={cn(
                        "mt-2 text-[11px] font-bold leading-4",
                        row.isCalculable ? "text-brand" : "text-muted"
                      )}
                      role={decisionError ? "alert" : undefined}
                    >
                      {row.isCalculable
                        ? decisionMessage
                        : `의사결정 입력 잠금: ${decisionMessage}`}
                    </p>
                  ) : null}
                  <details className="mt-3 rounded-[10px] bg-surface-soft px-3 py-2.5">
                    <summary className="cursor-pointer text-[11.5px] font-black text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30">
                      재고·참고값 전체 보기
                    </summary>
                    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-[11.5px]">
                      {[
                        ["안전재고", formatInteger(result.safetyStock)],
                        [incomingInventoryLabel, formatInteger(row.inboundQty)],
                        ...(isHqEntity
                          ? [["오포가용", formatInteger(row.localAvailableQty)]]
                          : [[`${headquartersWarehouseLabel}가용`, formatInteger(row.euAvailableQty)]]),
                        ...(isHqEntity
                          ? []
                          : [["운송중", formatInteger(row.inTransitQty)]]),
                        ...(isHqEntity ? [] : [["현지가용", formatInteger(row.localAvailableQty)]]),
                        ["다음 ETA", etaReferenceText(row)],
                        [
                          depletionReferenceLabel,
                          formatDecimal(row.stockoutWeeks, depletionUnit)
                        ],
                        [
                          `입고단가 (${currencyCode})`,
                          canViewAmountData
                            ? formatCurrency(row.unitPriceEur, currencyCode)
                            : "권한에 따라 숨김"
                        ],
                        [
                          localProposalAmountLabel,
                          canViewAmountData
                            ? formatCurrency(result.referenceAmountEur, currencyCode)
                            : "권한에 따라 숨김"
                        ],
                        ...(currencyCode === "KRW"
                          ? []
                          : [
                              [
                                "제안금액 (KRW)",
                                canViewAmountData
                                  ? formatCurrency(resolvedKrwAmount(result, krwFactor), "KRW")
                                  : "권한에 따라 숨김"
                              ]
                            ])
                      ].map(([label, value]) => (
                        <div key={label}>
                          <dt className="text-muted">{label}</dt>
                          <dd className="mt-1 tnum font-black text-ink">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                </article>
              );
            })}
            <Pagination
              page={currentPage}
              totalPages={totalPages}
              pageSize={pageSize}
              totalRows={proposalRows.length}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </div>

          <div className="hidden overflow-hidden rounded-[16px] border border-border bg-surface shadow-soft lg:block">
            <div
              className="overflow-x-auto"
              role="region"
              aria-label="발주 제안 표"
              tabIndex={0}
            >
              <table className="min-w-[1800px] table-fixed border-collapse text-[11.5px]">
                <caption className="sr-only">
                  {modeLabel(appliedMode)} 시나리오 발주 제안 결과
                </caption>
                <colgroup>
                  <col className="w-[130px]" />
                  <col className="w-[270px]" />
                  <col className="w-[110px]" />
                  {Array.from({ length: 3 }).map((_, index) => (
                    <col key={index} className="w-[112px]" />
                  ))}
                  <col className="w-[280px]" />
                  <col className="w-[112px]" />
                  <col className="w-[170px]" />
                  <col className="w-[112px]" />
                  <col className="w-[112px]" />
                  {canViewAmountData ? (
                    <>
                      <col className="w-[150px]" />
                      {showKrwProposalAmount ? <col className="w-[150px]" /> : null}
                    </>
                  ) : null}
                </colgroup>
                <thead className="bg-surface-soft">
                  <tr>
                    {[
                      "상품코드",
                      "상품명",
                      "브랜드",
                      demandAverageLabel,
                      "안전재고",
                      "목표 보유량",
                      "재고 구성",
                      "보유전체(IP)",
                      "입고·소진 참고",
                      "제안수량",
                      "발주신호",
                      ...(canViewAmountData
                        ? [
                            `제안금액(${currencyCode})`,
                            ...(showKrwProposalAmount ? ["제안금액(KRW)"] : [])
                          ]
                        : [])
                    ].map((label, index) => (
                      <th
                        key={label}
                        scope="col"
                        className={cn(
                          "border-b border-divider px-3 py-3 text-center font-black text-muted",
                          index === 0 && "sticky left-0 z-20 bg-surface-soft text-left",
                          index === 1 && "text-left"
                        )}
                      >
                        <span
                          title={
                            label.startsWith("제안금액") ? exchangeRateTitle : undefined
                          }
                        >
                          {label}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.map((row) => {
                    const result = getModeResult(row, appliedMode);
                    return (
                      <tr
                        key={row.id}
                        className="group border-b border-rowline last:border-b-0 hover:bg-surface-soft"
                      >
                        <th
                          scope="row"
                          className="sticky left-0 z-10 bg-surface px-3 py-3 text-left font-black text-brand group-hover:bg-surface-soft"
                        >
                          {row.productCode}
                        </th>
                        <td
                          className="truncate px-3 py-3 font-black text-ink"
                          title={row.productName}
                        >
                          {row.productName}
                        </td>
                        <td className="truncate px-3 py-3 text-center font-bold text-ink3">
                          {row.brand}
                        </td>
                        <td className="tnum px-3 py-3 text-right font-black text-ink">
                          {formatDecimal(row.weeklyMean)}
                        </td>
                        <td className="tnum px-3 py-3 text-right font-black text-ink">
                          {formatInteger(result.safetyStock)}
                        </td>
                        <td className="tnum px-3 py-3 text-right font-black text-ink">
                          {formatInteger(result.targetStock)}
                        </td>
                        <td className="px-3 py-2.5 text-[10.5px] font-bold leading-5 text-ink3">
                          {isHqEntity ? (
                            <span className="block">
                              {incomingInventoryLabel} {formatInteger(row.inboundQty)} · 오포{" "}
                              {formatInteger(row.localAvailableQty)}
                            </span>
                          ) : (
                            <>
                              <span className="block">
                                {incomingInventoryLabel} {formatInteger(row.inboundQty)} · {headquartersWarehouseLabel}{" "}
                                {formatInteger(row.euAvailableQty)}
                              </span>
                              <span className="block">
                                운송중 {formatInteger(row.inTransitQty)} · 현지{" "}
                                {formatInteger(row.localAvailableQty)}
                              </span>
                            </>
                          )}
                        </td>
                        <td className="tnum px-3 py-3 text-right font-black text-ink">
                          {formatInteger(row.inventoryPosition)}
                        </td>
                        <td
                          className="whitespace-nowrap px-3 py-2.5 text-[10.5px] font-bold leading-5 text-muted"
                          title={depletionReferenceTitle}
                        >
                          <span className="block">
                            {etaReferenceText(row)}
                          </span>
                          <span className="block">
                            고갈 {formatDecimal(row.stockoutWeeks, depletionUnit)}
                          </span>
                        </td>
                        <td className="tnum px-3 py-3 text-right text-[12.5px] font-black text-brand">
                          {formatInteger(result.suggestedQty)}
                        </td>
                        <td className="px-3 py-3 text-center">
                          <SignalBadge signal={result.signal} />
                        </td>
                        {canViewAmountData ? (
                          <td className="tnum px-3 py-3 text-right font-black text-ink">
                            {formatCurrency(result.referenceAmountEur, currencyCode)}
                          </td>
                        ) : null}
                        {showKrwProposalAmount ? (
                          <td className="tnum px-3 py-3 text-right font-black text-ink">
                            {formatCurrency(
                              resolvedKrwAmount(result, krwFactor),
                              "KRW"
                            )}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={currentPage}
              totalPages={totalPages}
              pageSize={pageSize}
              totalRows={proposalRows.length}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </div>
        </>
      )}
    </>
  );

  const comparisonPanel = renderResultState(
    <>
      <div
        className={cn(
          "mb-4 grid gap-[14px] md:grid-cols-2",
          canViewAmountData ? "xl:grid-cols-4" : "xl:grid-cols-3"
        )}
      >
        <MetricCard
          label={`${modeLabel(appliedMode)} 발주필요수량`}
          value={formatInteger(comparisonSummary.appliedQty)}
          caption="적용 시나리오"
          tone="brand"
        />
        <MetricCard
          label={`${modeLabel(referenceMode)} 발주필요수량`}
          value={formatInteger(comparisonSummary.referenceQty)}
          caption="비교 시나리오"
        />
        <MetricCard
          label="발주필요수량 차이"
          value={`${comparisonSummary.qtyDifference > 0 ? "+" : ""}${formatInteger(
            comparisonSummary.qtyDifference
          )}`}
          caption={`${modeLabel(appliedMode)} − ${modeLabel(referenceMode)}`}
          tone={comparisonSummary.qtyDifference > 0 ? "amber" : "green"}
        />
        {canViewAmountData ? (
          <MetricCard
            label="발주필요금액 차이"
            value={`${
              comparisonSummary.amountDifference !== null &&
              comparisonSummary.amountDifference > 0
                ? "+"
                : ""
            }${formatCompactKrw(
              comparisonSummary.amountDifference
            )}`}
            caption={
              comparisonSummary.amountDifference === null
                ? `단가(KRW) 누락 ${integerFormatter.format(
                    comparisonSummary.missingAmountRows.length
                  )}개 SKU · 비교 불가`
                : `${modeLabel(appliedMode)} − ${modeLabel(referenceMode)}`
            }
            title={exchangeRateTitle}
          />
        ) : null}
      </div>

      {filterBar}

      {comparisonRows.length === 0 ? (
        <StatePanel
          title="조건에 맞는 비교 결과가 없습니다"
          description="검색어나 필터를 초기화해 다른 SKU를 확인해 주세요."
        />
      ) : (
        <div className="overflow-hidden rounded-[16px] border border-border bg-surface shadow-soft">
          <div
            className="overflow-x-auto"
            role="region"
            aria-label="발주 시나리오 비교 표"
            tabIndex={0}
          >
            <table className="min-w-[1250px] table-fixed border-collapse text-[11.5px]">
              <caption className="sr-only">
                동일 snapshot 기준 발주 시나리오별 발주 결과 비교
              </caption>
              <colgroup>
                <col className="w-[130px]" />
                <col className="w-[360px]" />
                <col className="w-[150px]" />
                <col className="w-[150px]" />
                <col className="w-[160px]" />
                {canViewAmountData ? <col className="w-[170px]" /> : null}
                <col className="w-[280px]" />
              </colgroup>
              <thead className="bg-surface-soft">
                <tr>
                  {[
                    "상품코드",
                    "상품명",
                    "현금흐름 우선 발주필요수량",
                    "쇼티지 방어 발주필요수량",
                    "수량 차이 (쇼티지−현금)",
                    ...(canViewAmountData
                      ? ["발주필요금액 차이 (쇼티지−현금)"]
                      : []),
                    "차이 근거"
                  ].map((label, index) => (
                    <th
                      key={label}
                      scope="col"
                      className={cn(
                        "border-b border-divider px-3 py-3 text-center font-black text-muted",
                        index < 2 && "text-left"
                      )}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((row) => {
                  const cash = getModeResult(row, "CASH");
                  const shortage = getModeResult(row, "SHORTAGE");
                  const quantityDifference =
                    shortage.suggestedQty === null ||
                    cash.suggestedQty === null
                      ? null
                      : shortage.suggestedQty - cash.suggestedQty;
                  const missingAmountModes = priceMissingModesForComparison(
                    row,
                    ["CASH", "SHORTAGE"],
                    krwFactor
                  );
                  const amountDifference =
                    missingAmountModes.length > 0
                      ? null
                      : (resolvedKrwAmount(shortage, krwFactor) ?? 0) -
                        (resolvedKrwAmount(cash, krwFactor) ?? 0);
                  const localAmountDifference =
                    shortage.referenceAmountEur === null ||
                    shortage.referenceAmountEur === undefined ||
                    cash.referenceAmountEur === null ||
                    cash.referenceAmountEur === undefined
                      ? null
                      : shortage.referenceAmountEur - cash.referenceAmountEur;
                  const comparisonReasons = Array.from(
                    new Set([
                      ...(row.comparisonReasonsByMode.CASH ?? []),
                      ...(row.comparisonReasonsByMode.SHORTAGE ?? []),
                      ...missingAmountModes.map(
                        (mode) => `${modeLabel(mode)} 단가(KRW) 누락`
                      )
                    ])
                  );
                  return (
                    <tr
                      key={row.id}
                      className="border-b border-rowline last:border-b-0 hover:bg-surface-soft"
                    >
                      <th
                        scope="row"
                        className="px-3 py-3 text-left font-black text-brand"
                      >
                        {row.productCode}
                      </th>
                      <td
                        className="whitespace-normal break-words px-3 py-3 font-black leading-5 text-ink"
                        title={row.productName}
                      >
                        {row.productName}
                      </td>
                      <td className="tnum px-3 py-3 text-right text-[12.5px] font-black text-brand">
                        {formatInteger(cash.suggestedQty)}
                      </td>
                      <td className="tnum px-3 py-3 text-right font-black text-ink">
                        {formatInteger(shortage.suggestedQty)}
                      </td>
                      <td
                        className={cn(
                          "tnum whitespace-nowrap px-3 py-3 text-right font-black",
                          quantityDifference === null ||
                          quantityDifference === 0
                            ? "text-muted"
                            : quantityDifference > 0
                              ? "text-warn-strong"
                              : "text-pos-strong"
                        )}
                      >
                        {quantityDifference !== null && quantityDifference > 0
                          ? "+"
                          : ""}
                        {formatInteger(quantityDifference)}
                      </td>
                      {canViewAmountData ? (
                        <td
                          className={cn(
                            "tnum whitespace-nowrap px-3 py-3 text-right font-black",
                            amountDifference === null ||
                            amountDifference === 0
                              ? "text-muted"
                              : amountDifference > 0
                                ? "text-warn-strong"
                                : "text-pos-strong"
                          )}
                        >
                          {amountDifference === null ? (
                            <>
                              <span>-</span>
                              {missingAmountModes.length > 0 ? (
                                <span className="mt-0.5 block text-[10px] font-semibold text-warn-strong">
                                  단가 누락
                                </span>
                              ) : null}
                            </>
                          ) : (
                            formatCompactKrw(amountDifference)
                          )}
                          {currencyCode === "KRW" ? null : (
                            <span className="mt-0.5 block text-[10px] font-semibold text-muted2">
                              {localAmountDifference !== null && localAmountDifference > 0
                                ? "+"
                                : ""}
                              {formatCurrency(localAmountDifference, currencyCode)}
                            </span>
                          )}
                        </td>
                      ) : null}
                      <td className="px-3 py-3 text-left font-semibold leading-5 text-ink3">
                        {comparisonReasons.join(" · ") || "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            page={currentPage}
            totalPages={totalPages}
            pageSize={pageSize}
            totalRows={comparisonRows.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        </div>
      )}
    </>
  );

  const scenarioQuickSwitch = (
    <div className="mb-4 rounded-[14px] border border-border bg-surface p-3 shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-black text-muted2">결과 보기</span>
          <div className="inline-flex rounded-[10px] border border-border bg-surface-soft p-1">
            {(["SHORTAGE", "CASH"] as NewOrderPolicyMode[]).map((mode) => {
              const selected = appliedMode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => switchViewScenario(mode)}
                  disabled={actionBusy || loading}
                  aria-pressed={selected}
                  className={cn(
                    "rounded-[8px] px-3 py-1.5 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-60",
                    selected ? "bg-brand text-white shadow-soft" : "text-muted2 hover:text-ink"
                  )}
                >
                  {modeLabel(mode)}
                </button>
              );
            })}
          </div>
        </div>
        {settingsChanged ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-warn-border bg-warn-bg px-2.5 py-1 text-[10.5px] font-black text-warn-strong">
            설정 임시 변경 · 미저장
          </span>
        ) : null}
      </div>
    </div>
  );

  const settingsPanel = (
    <>
      {canEditAdvancedSettings ? (
        <>
          <section className="mb-4 flex items-start gap-3 rounded-[12px] border border-blue-200 bg-blue-50 px-4 py-3">
            <Settings2
              className="mt-0.5 h-4 w-4 shrink-0 text-blue-700"
              aria-hidden="true"
            />
            <div>
              <p className="text-[12px] font-black text-blue-800">
                변경한 산식 설정은 이번 실행에만 적용됩니다.
              </p>
              <p className="mt-1 text-[11.5px] font-semibold leading-4 text-blue-700">
                DB 연동 전에는 변경 이력과 다음 접속 시 설정이 저장되지 않습니다.
                결과에는 실제 적용된 산식 기준이 함께 기록됩니다.
              </p>
            </div>
          </section>

          <ValidationNotice errors={validationErrors} />
        </>
      ) : null}

      <section className="mt-4 rounded-[14px] border border-border bg-surface p-4 shadow-soft">
        <div>
          <h3 className="text-[13px] font-black text-ink">적용할 시나리오</h3>
          <p className="mt-1 text-[11.5px] font-semibold text-muted2">
            발주 제안에 반영할 운영 기준을 선택하세요.
          </p>
        </div>
        <fieldset className="mt-3">
          <legend className="sr-only">적용할 발주 시나리오 선택</legend>
          <div className="grid gap-3 md:grid-cols-2">
            {(["SHORTAGE", "CASH"] as NewOrderPolicyMode[]).map((mode) => {
              const selected = draftSettings.policyMode === mode;
              const isCash = mode === "CASH";
              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => selectPolicyMode(mode)}
                  disabled={actionBusy || loading}
                  aria-pressed={selected}
                  className={cn(
                    "flex min-h-[78px] items-center justify-between gap-4 rounded-[12px] border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30",
                    selected
                      ? isCash
                        ? "border-blue-300 bg-blue-50"
                        : "border-brand/30 bg-brand-50"
                      : "border-border bg-surface hover:border-muted"
                  )}
                >
                  <span>
                    <span className="block text-[13px] font-black text-ink">
                      {modeLabel(mode)}
                    </span>
                    <span className="mt-1 block text-[11px] font-semibold text-muted2">
                      {`${
                        isHqEntity ? "" : `${draftSettings.policyTransports[mode]} · `
                      }${
                        isCash
                          ? "재고와 필요자금 부담 감소"
                          : "품절과 판매손실 위험 감소"
                      }`}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "inline-flex h-7 shrink-0 items-center rounded-full px-2.5 text-[10.5px] font-black",
                      selected
                        ? isCash
                          ? "bg-blue-700 text-white"
                          : "bg-brand text-white"
                        : "bg-row text-muted2"
                    )}
                  >
                    {selected ? "선택됨" : "선택"}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>
      </section>

      {canEditAdvancedSettings ? (
        <section className="mt-4">
        <div className="grid gap-[14px] xl:grid-cols-2">
        <SettingsCard
          title="서비스 수준"
          description={
            isHqEntity
              ? "시나리오별 SKU 등급별 품절 방어 수준(Z)을 조정합니다."
              : "시나리오별 기본 운송수단과 SKU 등급별 품절 방어 수준(Z)을 조정합니다."
          }
        >
          <div className="grid gap-3">
            <fieldset
              className={cn(
                "rounded-[12px] border p-3 transition",
                draftSettings.policyMode === "SHORTAGE"
                  ? "border-brand/30 bg-brand-50"
                  : "border-border bg-surface-soft"
              )}
            >
              <legend className="sr-only">쇼티지 방어 시나리오 설정</legend>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-[12.5px] font-black text-ink">
                    쇼티지 방어 시나리오
                  </h4>
                  <p className="mt-1 text-[10.5px] font-semibold text-muted2">
                    품절 위험을 줄이는 높은 서비스 수준
                  </p>
                </div>
                {!isHqEntity ? (
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-1 text-[10px] font-black",
                      draftSettings.policyMode === "SHORTAGE"
                        ? "bg-surface text-brand"
                        : "bg-row text-muted2"
                    )}
                  >
                    {draftSettings.policyMode === "SHORTAGE"
                      ? `적용 중 · ${draftSettings.policyTransports.SHORTAGE}`
                      : `기본 운송 · ${draftSettings.policyTransports.SHORTAGE}`}
                  </span>
                ) : null}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ZLevelSelect
                  label="주력 SKU · Z"
                  value={draftSettings.zMatrix.shortageMajor}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      zMatrix: { ...draftSettings.zMatrix, shortageMajor: value }
                    })
                  }
                  defaultZ={defaultSettings?.zMatrix.shortageMajor}
                />
                <ZLevelSelect
                  label="일반 SKU · Z"
                  value={draftSettings.zMatrix.shortageMinor}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      zMatrix: { ...draftSettings.zMatrix, shortageMinor: value }
                    })
                  }
                  defaultZ={defaultSettings?.zMatrix.shortageMinor}
                />
              </div>
            </fieldset>

            <fieldset
              className={cn(
                "rounded-[12px] border p-3 transition",
                draftSettings.policyMode === "CASH"
                  ? "border-blue-300 bg-blue-50"
                  : "border-border bg-surface-soft"
              )}
            >
              <legend className="sr-only">현금흐름 우선 시나리오 설정</legend>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-[12.5px] font-black text-ink">
                    현금흐름 우선 시나리오
                  </h4>
                  <p className="mt-1 text-[10.5px] font-semibold text-muted2">
                    재고와 필요자금 부담을 줄이는 서비스 수준
                  </p>
                </div>
                {!isHqEntity ? (
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-1 text-[10px] font-black",
                      draftSettings.policyMode === "CASH"
                        ? "bg-surface text-blue-700"
                        : "bg-row text-muted2"
                    )}
                  >
                    {draftSettings.policyMode === "CASH"
                      ? `적용 중 · ${draftSettings.policyTransports.CASH}`
                      : `기본 운송 · ${draftSettings.policyTransports.CASH}`}
                  </span>
                ) : null}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <ZLevelSelect
                  label="주력 SKU · Z"
                  value={draftSettings.zMatrix.cashMajor}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      zMatrix: { ...draftSettings.zMatrix, cashMajor: value }
                    })
                  }
                  defaultZ={defaultSettings?.zMatrix.cashMajor}
                />
                <ZLevelSelect
                  label="일반 SKU · Z"
                  value={draftSettings.zMatrix.cashMinor}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      zMatrix: { ...draftSettings.zMatrix, cashMinor: value }
                    })
                  }
                  defaultZ={defaultSettings?.zMatrix.cashMinor}
                />
              </div>
            </fieldset>
          </div>
        </SettingsCard>

        <SettingsCard
          title={isHqEntity ? "SKU 분류 기준" : "재고 기준 · 정기 검토주기"}
          description={
            isHqEntity
              ? "주력 SKU 분류 기준은 승인 정책으로 고정됩니다."
              : "정기 검토주기와 법인별 안전재고 범위는 승인 정책으로 고정됩니다."
          }
        >
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label="주력 SKU 매출 기준"
              value={draftSettings.gradeCutoffPct}
              onChange={(value) =>
                updateDraftSettings({ ...draftSettings, gradeCutoffPct: value })
              }
              caption={`전체 누적 매출의 ${formatDecimal(
                draftSettings.gradeCutoffPct
              )}% 구간까지 주력 SKU로 분류`}
              unit="%"
              min={1}
              max={99}
            />
            {!isHqEntity ? (
              <>
                <NumberField
                  label="정기 검토주기"
                  value={draftSettings.coverWeeks}
                  onChange={(value) =>
                    updateDraftSettings({ ...draftSettings, coverWeeks: value })
                  }
                  caption="승인 정책 고정값"
                  unit="주"
                  min={0}
                  step={0.5}
                  disabled
                />
                <NumberField
                  label="안전재고 하한"
                  value={draftSettings.safetyStockFloorWeeks}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      safetyStockFloorWeeks: value
                    })
                  }
                  unit="주"
                  min={0}
                  step={0.5}
                  disabled
                />
                <NumberField
                  label="안전재고 상한"
                  value={draftSettings.safetyStockCapWeeks}
                  onChange={(value) =>
                    updateDraftSettings({
                      ...draftSettings,
                      safetyStockCapWeeks: value
                    })
                  }
                  unit="주"
                  min={0}
                  step={0.5}
                  disabled
                />
              </>
            ) : null}
          </div>
        </SettingsCard>

        {draftSettings.domesticLeadTime ? (
          <SettingsCard
            title="국내조달 리드타임 · 변동성"
            description="실입고일 − 구매오더 생성일을 최근 12개월 입고건 동일가중으로 집계해 실행 시 서버가 적용합니다."
            className="xl:col-span-2"
          >
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <NumberField
                label="평균 리드타임"
                value={draftSettings.domesticLeadTime.meanDays}
                onChange={() => undefined}
                caption={
                  draftSettings.domesticLeadTime.valueUnavailable
                    ? "실측값을 확인할 수 없습니다"
                    : draftSettings.domesticLeadTime.measuredSampleSize
                    ? `최근 ${
                        draftSettings.domesticLeadTime.measuredWindowMonths ?? 12
                      }개월 실측 · 표본 ${integerFormatter.format(
                        draftSettings.domesticLeadTime.measuredSampleSize
                      )}건`
                    : "서버 실측 적용값"
                }
                unit="일"
                min={0}
                step={0.01}
                disabled
              />
              <NumberField
                label="리드타임 σL"
                value={draftSettings.domesticLeadTime.sigmaDays}
                onChange={() => undefined}
                caption={
                  draftSettings.domesticLeadTime.valueUnavailable
                    ? "실측값을 확인할 수 없습니다"
                    : "입고건 동일가중 STDEV.S"
                }
                unit="일"
                min={0}
                step={0.01}
                disabled
              />
              <NumberField
                label="정기 검토주기 R"
                value={draftSettings.domesticLeadTime.reviewDays}
                onChange={() => undefined}
                caption="승인 정책 고정값"
                unit="일"
                min={0}
                step={1}
                disabled
              />
              <NumberField
                label="안전재고 하한"
                value={draftSettings.domesticLeadTime.safetyStockFloorDays}
                onChange={() => undefined}
                caption="승인 정책 고정값"
                unit="일"
                min={0}
                step={1}
                disabled
              />
              <NumberField
                label="안전재고 상한"
                value={draftSettings.domesticLeadTime.safetyStockCapDays}
                onChange={() => undefined}
                caption="승인 정책 고정값"
                unit="일"
                min={0}
                step={1}
                disabled
              />
            </div>
          </SettingsCard>
        ) : (
        <SettingsCard
          title="운송 리드타임 · 변동성"
          description="최근 12개월 실측 평균과 표준편차(STDEV.S)를 실행 시 서버가 적용합니다."
          className="xl:col-span-2"
        >
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {draftSettings.leadTimes.map((item) => (
              <section
                key={item.code}
                className="rounded-[12px] border border-border bg-surface-soft p-4"
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <h4 className="text-[12.5px] font-black text-ink">{item.label}</h4>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {item.code === draftSettings.policyTransports.SHORTAGE ||
                    item.code === draftSettings.policyTransports.CASH ? (
                      <span
                        className={cn(
                          "rounded-full px-2 py-1 text-[10px] font-black",
                          (item.code === draftSettings.policyTransports.SHORTAGE &&
                            draftSettings.policyMode === "SHORTAGE") ||
                            (item.code === draftSettings.policyTransports.CASH &&
                              draftSettings.policyMode === "CASH")
                            ? item.code === draftSettings.policyTransports.SHORTAGE
                              ? "bg-brand-50 text-brand"
                              : "bg-blue-50 text-blue-700"
                            : "bg-row text-muted2"
                        )}
                      >
                        {item.code === draftSettings.policyTransports.SHORTAGE
                          ? "쇼티지 방어"
                          : "현금흐름 우선"}
                      </span>
                    ) : null}
                    <span className="rounded-full bg-row px-2 py-1 text-[10px] font-black text-muted">
                      {item.code}
                    </span>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <NumberField
                    label="평균 리드타임"
                    value={item.meanDays}
                    onChange={(value) => updateLeadTime(item.code, "meanDays", value)}
                    unit="일"
                    min={0.1}
                    step={0.1}
                    disabled
                  />
                  <NumberField
                    label="리드타임 σL"
                    value={item.sigmaWeeks}
                    onChange={(value) =>
                      updateLeadTime(item.code, "sigmaWeeks", value)
                    }
                    unit="주"
                    min={0}
                    step={0.01}
                    disabled
                  />
                </div>
              </section>
            ))}
          </div>
        </SettingsCard>
        )}
        </div>
        </section>
      ) : null}

      <div className="sticky bottom-0 z-20 mt-5 flex flex-col gap-3 border-t border-border bg-page/95 py-4 backdrop-blur-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="min-h-5 text-[11.5px] font-bold text-muted" aria-live="polite">
          {settingsChanged ? (
            <span className="inline-flex items-center gap-1.5 text-warn-strong">
              <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
              {canEditAdvancedSettings
                ? "현재 세션에 적용되지 않은 변경값이 있습니다."
                : "선택한 시나리오가 아직 적용되지 않았습니다."}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5">
              <Check className="h-3.5 w-3.5 text-pos" aria-hidden="true" />
              {canEditAdvancedSettings
                ? "현재 설정과 같습니다."
                : "현재 적용 시나리오와 같습니다."}
            </span>
          )}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          {canEditAdvancedSettings ? (
            <button
              type="button"
              onClick={() => {
                if (defaultSettings) {
                  updateDraftSettings(
                    restoreEditableSettings(draftSettings, defaultSettings)
                  );
                }
              }}
              disabled={!defaultSettings || actionBusy || loading}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-[9px] border border-border bg-surface px-4 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              기본값 복원
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void onApplySettings?.(draftSettings)}
            disabled={
              !onApplySettings ||
              actionBusy ||
              loading ||
              !settingsChanged ||
              validationErrors.length > 0
            }
            className="inline-flex h-10 items-center justify-center gap-2 rounded-[9px] bg-ink px-4 text-[12px] font-black text-white transition hover:bg-ink3 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
          >
            {applyingSettings ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Check className="h-4 w-4" aria-hidden="true" />
            )}
            {applyingSettings
              ? canEditAdvancedSettings
                ? "설정 적용 중…"
                : "시나리오 적용 중…"
              : canEditAdvancedSettings
                ? "선택한 설정 적용"
                : "선택한 시나리오 적용"}
          </button>
        </div>
      </div>
    </>
  );

  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[1600px] px-4 py-5 sm:px-6 sm:py-6 lg:px-[25px]",
        className
      )}
      aria-busy={loading || actionBusy}
    >
      <header className="mb-4 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[18px] font-black leading-none text-ink">발주분석 V2</h2>
            <span className="inline-flex h-6 items-center rounded-full bg-brand-50 px-2.5 text-[10px] font-black tracking-wide text-brand">
              BETA
            </span>
            <button
              ref={formulaTriggerRef}
              type="button"
              onClick={() => setFormulaDrawerOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={formulaDrawerOpen}
              aria-controls="order-formula-dialog"
              className="ml-1 inline-flex h-9 items-center justify-center gap-2 rounded-[8px] border border-border bg-surface px-3 text-[11px] font-black text-ink transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              <Calculator className="h-4 w-4 text-blue-700" aria-hidden="true" />
              발주 산식 보기
            </button>
          </div>
          {appliedMode !== officialMode ? (
            <span className="rounded-full bg-row px-2.5 py-1 text-[10.5px] font-black text-muted2">
              참고 시나리오
            </span>
          ) : null}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row xl:justify-end">
          <button
            type="button"
            onClick={() => void onRun?.(draftSettings)}
            disabled={
              !onRun ||
              actionBusy ||
              loading ||
              validationErrors.length > 0
            }
            className={cn(
              "inline-flex h-10 items-center justify-center gap-2 rounded-[9px] px-4 text-[12px] font-black text-white transition disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
              analysisCompletedAt
                ? "bg-pos hover:bg-pos"
                : "bg-brand hover:bg-brand-700"
            )}
            aria-live="polite"
            title={
              analysisCompletedAt
                ? `분석 완료 ${analysisCompletedAt.toLocaleTimeString("ko-KR", {
                    hour: "2-digit",
                    minute: "2-digit"
                  })}`
                : undefined
            }
          >
            {running ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : analysisCompletedAt ? (
              <Check className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Play className="h-4 w-4" aria-hidden="true" />
            )}
            {running ? `분석 실행 중… ${analysisElapsedLabel}` : analysisCompletedAt ? "분석 완료" : "분석 실행"}
          </button>
          {running ? (
            <button
              type="button"
              onClick={() => void onCancelRun?.()}
              disabled={!onCancelRun || cancelling}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-[9px] bg-sidebar px-4 text-[12px] font-black text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              {cancelling ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
              {cancelling ? "분석 중단 중…" : "분석 중단"}
            </button>
          ) : null}
          <div className="relative">
            <button
              type="button"
              onClick={() => setExportMenuOpen((open) => !open)}
              disabled={
                !onExportExcel ||
                actionBusy ||
                loading ||
                !data ||
                currentRows.length === 0 ||
                exportDecisionErrorCount > 0
              }
              title={
                currentRows.length === 0
                  ? "현재 필터 조건에서 내보낼 SKU가 없습니다."
                  : exportDecisionErrorCount > 0
                  ? `확정수량 검증 오류 ${exportDecisionErrorCount}건을 먼저 수정해 주세요.`
                  : undefined
              }
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[9px] bg-ink px-4 text-[12px] font-black text-white transition hover:bg-ink3 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
            >
              {exportingExcel ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Download className="h-4 w-4" aria-hidden="true" />
              )}
              {exportingExcel ? "Excel 생성 중…" : "엑셀 내보내기"}
              <ChevronDown className={cn("h-4 w-4 transition", exportMenuOpen && "rotate-180")} aria-hidden="true" />
            </button>
            {exportMenuOpen ? (
              <div className="absolute right-0 top-11 z-40 w-[260px] overflow-hidden rounded-[12px] border border-border bg-surface py-1 shadow-soft">
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={!onExportExcel || exportingExcel || currentRows.length === 0}
                  className="block w-full px-4 py-3 text-left text-[13px] font-black text-ink hover:bg-surface-soft disabled:cursor-not-allowed disabled:text-muted2 disabled:opacity-50"
                >
                  {filters.brand === "all" ? "전체 브랜드 데이터 내보내기" : `${filters.brand} 데이터 내보내기`}
                  <span className="mt-1 block text-[11px] font-bold text-muted">
                    {filters.brand === "all" ? "전체 브랜드" : `브랜드: ${filters.brand}`} · {integerFormatter.format(currentRows.length)} SKU
                  </span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <section
        className="mb-4 flex items-start gap-3 rounded-[14px] border border-blue-200 bg-blue-50 px-4 py-3"
        aria-labelledby={`${instanceId}-order-notice-title`}
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-700" aria-hidden="true" />
        <div>
          <p
            id={`${instanceId}-order-notice-title`}
            className="text-[12px] font-black text-blue-900"
          >
            발주 전 참고사항
          </p>
          <p className="mt-1 text-[11.5px] font-semibold leading-4 text-blue-800">
            제안수량은 발주 검토를 돕기 위한 참고값입니다. 발주 전 판매·재고 데이터의
            기준시점, 입고 예정일(ETA), 단가를 확인해 주세요.
          </p>
          {data?.meta.warnings?.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] font-semibold leading-4 text-blue-900">
              {data.meta.warnings.map((warning, index) => (
                <li key={`${index}-${warning}`}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      {error && data ? (
        <section
          className="mb-4 flex items-start gap-3 rounded-[12px] border border-brand/20 bg-brand-50 px-4 py-3"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
          <div>
            <p className="text-[12px] font-black text-brand">
              요청한 작업을 완료하지 못했습니다.
            </p>
            <p className="mt-1 text-[11.5px] font-semibold leading-4 text-brand">
              {error}
            </p>
          </div>
        </section>
      ) : null}

      <section
        className="mb-4 rounded-[14px] border border-border bg-surface p-3 shadow-soft"
        aria-label="발주 실행 메타데이터"
      >
        <div className="flex flex-wrap gap-2">
          <MetaChip label="공식 적용 시나리오" value={modeLabel(officialMode)} emphasized />
          <MetaChip
            label="수요기간"
            value={
              data
                ? `${formatPeriodDate(data.meta.demandPeriod.from)}–${formatPeriodDate(
                    data.meta.demandPeriod.to
                  )} · ${data.meta.demandPeriod.observationWindowDays ?? (data.meta.periodUnit === "day" ? 91 : data.meta.demandPeriod.completedWeeks * 7)}일${
                    data.meta.periodUnit === "day"
                      ? " (일별 판매량)"
                      : ` (${data.meta.demandPeriod.completedWeeks}주)`
                  }`
                : String(entityCode || "").toUpperCase() === "HQ"
                  ? "최근 91일 (일별 판매량)"
                  : `최근 ${draftSettings.demandWeeks * 7}일 (${draftSettings.demandWeeks}주)`
            }
          />
        </div>
      </section>

      {data && exportDecisionErrorCount > 0 ? (
        <section
          className="mb-4 flex items-start gap-3 rounded-[12px] border border-brand/20 bg-brand-50 px-4 py-3"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
          <div>
            <p className="text-[12px] font-black text-brand">
              확정수량 검증 오류 {integerFormatter.format(exportDecisionErrorCount)}건
            </p>
            <p className="mt-1 text-[11.5px] font-semibold leading-4 text-brand">
              확정수량을 빈칸 없이 0 이상의 정수로 입력해야 현재 필터 결과를 Excel로
              내보낼 수 있습니다. 메모는 선택사항입니다.
            </p>
          </div>
        </section>
      ) : null}

      <div
        role="tablist"
        aria-label="발주분석 V2 화면"
        className="mb-4 flex overflow-x-auto border-b border-border"
      >
        {TAB_ITEMS.map((tab, index) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              id={`${instanceId}-${tab.id}-tab`}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`${instanceId}-${tab.id}-panel`}
              tabIndex={active ? 0 : -1}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              className={cn(
                "relative min-h-12 shrink-0 px-5 text-[13px] font-black transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40",
                active ? "text-ink" : "text-muted2 hover:text-ink"
              )}
            >
              {tab.label}
              {active ? (
                <span
                  className="absolute inset-x-0 bottom-0 h-0.5 bg-brand"
                  aria-hidden="true"
                />
              ) : null}
            </button>
          );
        })}
      </div>

      {activeTab === "proposal" ? scenarioQuickSwitch : null}

      <div
        id={`${instanceId}-proposal-panel`}
        role="tabpanel"
        aria-labelledby={`${instanceId}-proposal-tab`}
        hidden={activeTab !== "proposal"}
      >
        {activeTab === "proposal" ? proposalPanel : null}
      </div>
      <div
        id={`${instanceId}-comparison-panel`}
        role="tabpanel"
        aria-labelledby={`${instanceId}-comparison-tab`}
        hidden={activeTab !== "comparison"}
      >
        {activeTab === "comparison" ? comparisonPanel : null}
      </div>
      <div
        id={`${instanceId}-settings-panel`}
        role="tabpanel"
        aria-labelledby={`${instanceId}-settings-tab`}
        hidden={activeTab !== "settings"}
      >
        {activeTab === "settings" ? settingsPanel : null}
      </div>

      <div className="sr-only" aria-live="polite">
        {running
          ? "발주 분석을 실행 중입니다."
          : exportingExcel
            ? "신규 산식 Excel을 생성 중입니다."
            : ""}
      </div>

      <OrderFormulaDrawer
        open={formulaDrawerOpen}
        policyMode={appliedMode}
        settings={settings}
        entityCode={entityCode}
        hasAnalysisResult={Boolean(data) && !running}
        onClose={() => setFormulaDrawerOpen(false)}
      />
    </div>
  );
}

export default NewOrderLogicScreenExact;
