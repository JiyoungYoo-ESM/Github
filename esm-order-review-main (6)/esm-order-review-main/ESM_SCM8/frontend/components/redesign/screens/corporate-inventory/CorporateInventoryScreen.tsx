"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Boxes, CheckCircle2, ChevronRight, CircleDollarSign, Info, RefreshCw, Truck, X } from "lucide-react";
import {
  getCorporateInventory,
  isAbortError,
  type CorporateInventoryCompany,
  type CorporateInventoryInTransit,
  type CorporateInventoryResponse
} from "@/lib/api";
import { cn } from "@/lib/utils";

const EOK_IN_KRW = 100_000_000;
const WHOLE_UNIT_CURRENCIES = new Set(["IDR", "JPY", "KRW", "VND"]);
type HoldingsValuation = "book" | "current";

function numberFromKrw(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatKrwEok(value: string): string {
  const amount = numberFromKrw(value);
  if (Math.abs(amount) >= EOK_IN_KRW) return `₩ ${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(amount / EOK_IN_KRW)}억`;
  if (Math.abs(amount) >= 10_000) return `₩ ${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(amount / 10_000)}만`;
  return `₩ ${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(amount)}`;
}

function formatSignedKrwEok(value: string): string {
  const amount = numberFromKrw(value);
  if (amount === 0) return "₩ 0";
  const absolute = formatKrwEok(String(Math.abs(amount))).replace(/^₩\s*/, "");
  return `${amount > 0 ? "+" : "-"}${absolute}`;
}

function companyAmount(company: CorporateInventoryCompany, valuation: HoldingsValuation): string {
  return valuation === "current" ? company.ending_inventory_current_krw : company.ending_inventory_krw;
}

function warehouseAmount(
  warehouse: CorporateInventoryCompany["warehouses"][number],
  valuation: HoldingsValuation
): string {
  return valuation === "current" ? warehouse.ending_inventory_current_krw : warehouse.ending_inventory_krw;
}

function formatDecimal(value: string, maximumFractionDigits = 2): string {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("ko-KR", { maximumFractionDigits }).format(amount)
    : "-";
}

function formatOriginalAmount(value: string, currencyCode: string): string {
  return `${currencyCode} ${formatDecimal(value, WHOLE_UNIT_CURRENCIES.has(currencyCode) ? 0 : 2)}`;
}

function hasLocalAmount(value: string | null | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function KoreanDate({ value }: { value: string }) {
  const matched = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!matched) return <>{value}</>;
  return <>{Number(matched[1])}년 {Number(matched[2])}월 {Number(matched[3])}일</>;
}

function InventoryDetailDialog({
  open,
  eyebrow,
  title,
  total,
  onClose,
  onBack,
  children
}: {
  open: boolean;
  eyebrow: string;
  title: string;
  total?: ReactNode;
  onClose: () => void;
  onBack?: () => void;
  children: ReactNode;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousActiveElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previousActiveElement?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/45 p-3 sm:p-5">
      <button type="button" aria-label="상세 창 닫기" onClick={onClose} className="absolute inset-0 cursor-default" />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="corporate-inventory-detail-title"
        className="relative flex max-h-[calc(100vh-24px)] w-full max-w-[920px] flex-col overflow-hidden rounded-[16px] border border-border bg-surface shadow-2xl sm:max-h-[calc(100vh-40px)]"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-divider px-5 py-4 sm:px-6 sm:py-5">
          <div className="min-w-0">
            {eyebrow ? <p className="text-[11px] font-black text-brand">{eyebrow}</p> : null}
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              {onBack ? (
                <button
                  type="button"
                  onClick={onBack}
                  className="inline-flex h-9 items-center gap-1.5 rounded-[8px] border border-border px-3 text-[11.5px] font-black text-ink3 transition hover:border-brand hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
                >
                  <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> 목록
                </button>
              ) : null}
              <h2 id="corporate-inventory-detail-title" className="text-[17px] font-black text-ink sm:text-[18px]">{title}</h2>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {total ? <span className="text-right text-[13px] font-black text-ink">{total}</span> : null}
            <button
              ref={closeButtonRef}
              type="button"
              aria-label="상세 창 닫기"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-[10px] border border-border text-ink3 transition hover:border-brand hover:text-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
            >
              <X className="h-[18px] w-[18px]" aria-hidden="true" />
            </button>
          </div>
        </header>
        <div className="min-h-0 overflow-y-auto">{children}</div>
      </section>
    </div>
  );
}

function CompanyRanking({ companies, totalKrw, valuation }: {
  companies: CorporateInventoryCompany[];
  totalKrw: string;
  valuation: HoldingsValuation;
}) {
  const sortedCompanies = useMemo(
    () => [...companies].sort((left, right) => {
      const amountDifference = numberFromKrw(companyAmount(right, valuation)) - numberFromKrw(companyAmount(left, valuation));
      return amountDifference || left.company_name.localeCompare(right.company_name, "ko");
    }),
    [companies, valuation]
  );
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const total = numberFromKrw(totalKrw);
  const companiesPerColumn = Math.ceil(sortedCompanies.length / 2);
  const companyColumns = [
    sortedCompanies.slice(0, companiesPerColumn),
    sortedCompanies.slice(companiesPerColumn)
  ].filter((column) => column.length > 0);

  useEffect(() => {
    setSelectedCode((current) => sortedCompanies.some((company) => company.company_code === current) ? current : null);
  }, [sortedCompanies]);

  const selectedCompany = sortedCompanies.find((company) => company.company_code === selectedCode) ?? null;
  const sortedWarehouses = useMemo(
    () => selectedCompany
      ? [...selectedCompany.warehouses].sort((left, right) => {
          const amountDifference = numberFromKrw(warehouseAmount(right, valuation)) - numberFromKrw(warehouseAmount(left, valuation));
          return amountDifference || left.warehouse_name.localeCompare(right.warehouse_name, "ko");
        })
      : [],
    [selectedCompany, valuation]
  );

  return (
    <>
      <section className="mx-auto w-full overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-divider px-5 py-3 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[16px] font-black text-ink">법인별 보유 재고 상세</h2>
            <span className={cn(
              "inline-flex items-center rounded-full px-2.5 py-1 text-[10.5px] font-black",
              valuation === "current" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
            )}>
              {valuation === "current" ? "현재환율 평가액 표시 중" : "장부금액 표시 중"}
            </span>
          </div>
          <span className="text-[11.5px] font-semibold text-muted">법인을 선택하면 창고 상세를 확인할 수 있습니다</span>
        </div>
        <div className="grid divide-y divide-divider md:grid-cols-2 md:divide-x md:divide-y-0">
          {companyColumns.map((column, columnIndex) => (
            <div key={columnIndex} className="min-w-0 px-5 sm:px-6">
              <div className="grid h-8 grid-cols-[24px_minmax(0,1fr)_48px_128px_16px] items-center gap-2 border-b border-divider text-[10.5px] font-extrabold text-muted2">
                <span>#</span>
                <span>법인</span>
                <span className="text-right">비중</span>
                <span className="text-right">{valuation === "current" ? "현재환율 평가액" : "장부금액"}</span>
                <span aria-hidden="true" />
              </div>
              {column.map((company, index) => {
                const rank = columnIndex * companiesPerColumn + index + 1;
                const displayedAmount = companyAmount(company, valuation);
                const amount = numberFromKrw(displayedAmount);
                const share = total > 0 ? Math.round((amount / total) * 1000) / 10 : 0;
                const hasNoInventory = company.inventory_status === "no_inventory";
                return (
                  <button
                    key={company.company_code}
                    type="button"
                    onClick={() => setSelectedCode(company.company_code)}
                    aria-haspopup="dialog"
                    className="grid min-h-[42px] w-full grid-cols-[24px_minmax(0,1fr)_48px_128px_16px] items-center gap-2 border-b border-rowline py-1 text-left transition last:border-b-0 hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                  >
                    <span className={cn("text-[12.5px] font-black", rank <= 3 ? "text-brand" : "text-muted2")}>{rank}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-black leading-[17px] text-ink" title={company.company_name}>
                        {company.company_name}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] font-bold leading-[12px] text-muted2">
                        {company.country_name}{hasNoInventory ? " · 보유재고 없음" : ""}
                        {company.valuation_basis === "current_exchange_rate" ? " · IDR 환율 보정" : ""}
                      </span>
                    </span>
                    <span className="text-right text-[12.5px] font-black text-muted2">{share}%</span>
                    <span className="min-w-0 text-right">
                      <span className="block text-[13px] font-black text-ink">{formatKrwEok(displayedAmount)}</span>
                      {company.valuation_basis === "current_exchange_rate" && hasLocalAmount(company.ending_inventory_local) ? (
                        <span
                          className="mt-0.5 block truncate text-[10px] font-bold leading-[12px] text-muted2"
                          title={formatOriginalAmount(company.ending_inventory_local, company.base_currency)}
                        >
                          {formatOriginalAmount(company.ending_inventory_local, company.base_currency)}
                        </span>
                      ) : null}
                    </span>
                    <ChevronRight className="h-4 w-4 justify-self-end text-muted2" aria-hidden="true" />
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </section>
      <InventoryDetailDialog
        open={selectedCompany !== null}
        eyebrow={selectedCompany?.country_name ?? ""}
        title={selectedCompany ? `${selectedCompany.company_name} 창고별 재고금액` : "창고별 재고금액"}
        onClose={() => setSelectedCode(null)}
      >
        {selectedCompany ? (
          <>
            {(valuation === "current" || selectedCompany.valuation_basis === "current_exchange_rate") && selectedCompany.exchange_rate_unit && selectedCompany.exchange_rate_krw ? (
              <p className="border-b border-divider bg-surface-soft px-5 py-3 text-[11px] font-semibold text-muted2 sm:px-6">
                적용 환율: {selectedCompany.exchange_rate_unit} {formatDecimal(selectedCompany.exchange_rate_krw)}원
                {selectedCompany.exchange_rate_date ? <> · <KoreanDate value={selectedCompany.exchange_rate_date} /> 고시</> : null}
              </p>
            ) : null}
            {sortedWarehouses.length > 0 ? (
              <div className="divide-y divide-rowline px-5 sm:px-6">
                {sortedWarehouses.map((warehouse) => (
                  <div key={warehouse.warehouse_code} className="flex min-h-[58px] items-center justify-between gap-4 py-2">
                    <span className="min-w-0">
                      <span className="block break-words text-[13px] font-black text-ink">{warehouse.warehouse_name}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-[13px] font-black text-ink">{formatKrwEok(warehouseAmount(warehouse, valuation))}</span>
                      {selectedCompany.valuation_basis === "current_exchange_rate" && hasLocalAmount(warehouse.ending_inventory_local) ? (
                        <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">
                          {formatOriginalAmount(warehouse.ending_inventory_local, selectedCompany.base_currency)}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="px-5 py-10 text-center text-[12.5px] font-bold text-muted">
                {selectedCompany.inventory_status === "no_inventory" ? "오늘 기준 보유재고가 없습니다." : "표시할 창고가 없습니다."}
              </p>
            )}
          </>
        ) : null}
      </InventoryDetailDialog>
    </>
  );
}

function HoldingsFailure({ message }: { message: string }) {
  return (
    <section className="rounded-[14px] border border-rose-200 bg-rose-50 px-5 py-5 text-rose-900 shadow-soft" role="status">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <h2 className="text-[15px] font-black">보유 재고 갱신 실패</h2>
          <p className="mt-1 text-[13px] font-semibold leading-6">{message}</p>
          <p className="mt-1 text-[12px] font-bold text-rose-700">금액을 0원으로 대체하지 않았습니다.</p>
        </div>
      </div>
    </section>
  );
}

function TransitDestinations({
  inTransit,
  open,
  onClose
}: {
  inTransit: Extract<CorporateInventoryInTransit, { status: "ready" }>;
  open: boolean;
  onClose: () => void;
}) {
  const [selectedDestinationCode, setSelectedDestinationCode] = useState<string | null>(null);
  const selectedDestination = inTransit.destinations.find((destination) => destination.destination_code === selectedDestinationCode) ?? null;
  const sortedDestinations = useMemo(
    () => [...inTransit.destinations].sort((left, right) => {
      const amountDifference = numberFromKrw(right.total_krw) - numberFromKrw(left.total_krw);
      return amountDifference || left.destination_name.localeCompare(right.destination_name, "ko");
    }),
    [inTransit.destinations]
  );

  useEffect(() => {
    if (!open) setSelectedDestinationCode(null);
  }, [open]);

  const close = () => {
    setSelectedDestinationCode(null);
    onClose();
  };

  return (
    <InventoryDetailDialog
      open={open}
      eyebrow=""
      title={selectedDestination ? `${selectedDestination.destination_name} 운송중 재고` : "도착 법인별 운송중 재고"}
      onClose={close}
      onBack={selectedDestination ? () => setSelectedDestinationCode(null) : undefined}
    >
      {selectedDestination ? (
        <>
          <p className="border-b border-divider bg-surface-soft px-5 py-3 text-[11.5px] font-semibold text-ink3 sm:px-6">
            원화 환산 기준: 인보이스에 기록된 계약환율
          </p>
          {selectedDestination.transport_modes.length > 0 ? (
            <div className="grid gap-3 p-5 sm:grid-cols-2 sm:p-6 min-[860px]:grid-cols-3">
              {selectedDestination.transport_modes.map((mode) => (
                <section key={mode.transport_mode_code} className="rounded-[10px] border border-border bg-surface-soft px-4 py-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                      <span>
                        <span className="block text-[13px] font-black text-ink">{mode.transport_mode_name}</span>
                        <span className="mt-0.5 block text-[11.5px] font-semibold tabular-nums text-ink3">수량 {formatDecimal(mode.quantity)}</span>
                      </span>
                    <span className="shrink-0 text-[13px] font-black tabular-nums text-brand">{formatKrwEok(mode.total_krw)}</span>
                  </div>
                  <div className="mt-3 space-y-2 border-t border-divider pt-2.5">
                    {mode.currencies.map((currency) => (
                      <div key={currency.currency_code}>
                        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                          <span className="text-[11.5px] font-bold tabular-nums text-ink3">{formatOriginalAmount(currency.original_amount, currency.currency_code)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : <p className="px-5 py-10 text-center text-[12.5px] font-bold text-muted">표시할 운송수단별 재고가 없습니다.</p>}
        </>
      ) : sortedDestinations.length > 0 ? (
        <div className="divide-y divide-rowline px-5 sm:px-6">
          {sortedDestinations.map((destination, index) => (
            <button
              key={destination.destination_code}
              type="button"
              onClick={() => setSelectedDestinationCode(destination.destination_code)}
              className="grid min-h-[64px] w-full grid-cols-[28px_minmax(0,1fr)_112px_16px] items-center gap-3 py-2 text-left transition hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 sm:grid-cols-[32px_minmax(0,1fr)_140px_18px]"
            >
              <span className="text-[12px] font-black text-muted2">{index + 1}</span>
              <span className="min-w-0">
                <span className="block break-words text-[13px] font-black text-ink">{destination.destination_name}</span>
                <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">수량 {formatDecimal(destination.quantity)}</span>
              </span>
              <span className="text-right text-[13px] font-black text-ink">{formatKrwEok(destination.total_krw)}</span>
              <ChevronRight className="h-4 w-4 text-muted2" aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : (
        <p className="px-5 py-10 text-center text-[12.5px] font-bold text-muted">현재 운송중 재고가 없습니다.</p>
      )}
    </InventoryDetailDialog>
  );
}

export function CorporateInventoryScreen() {
  const [data, setData] = useState<CorporateInventoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestError, setRequestError] = useState("");
  const [valuation, setValuation] = useState<HoldingsValuation>("current");
  const [transitDialogOpen, setTransitDialogOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setRequestError("");
    try {
      setData(await getCorporateInventory());
    } catch (error) {
      if (isAbortError(error)) return;
      setRequestError(error instanceof Error ? error.message : "전사 재고를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const holdingsReady = data?.holdings.status === "ready" ? data.holdings : null;
  const transitReady = data?.in_transit.status === "ready" ? data.in_transit : null;
  const transitFailureMessage = data?.in_transit.status === "failed"
    ? data.in_transit.message
    : "운송중 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  const totalReady = data?.total_inventory.status === "ready" ? data.total_inventory : null;
  const holdingsFailureMessage = data?.holdings.status === "failed"
    ? data.holdings.message
    : "보유 재고를 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.";
  const selectedHoldingsTotal = holdingsReady
    ? valuation === "current" ? holdingsReady.total_current_krw : holdingsReady.total_krw
    : null;

  return (
    <div className="relative mx-auto max-w-[1440px] px-4 py-5 sm:px-6 sm:py-6 lg:px-[25px]">
      <button type="button" onClick={() => void refresh()} disabled={loading} className="mb-4 ml-auto inline-flex h-10 items-center gap-2 rounded-[9px] border border-border bg-surface px-3.5 text-[12px] font-black text-ink shadow-soft transition hover:bg-surface-soft disabled:cursor-not-allowed disabled:opacity-60 lg:absolute lg:right-[25px] lg:top-6 lg:mb-0">
        <RefreshCw className={cn("h-4 w-4 text-brand", loading && "animate-spin")} />
        새로고침
      </button>

      <div className="lg:pr-[120px]">
      {loading && !data ? (
        <div className="grid min-h-[360px] place-items-center rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-center gap-3 text-[13px] font-black text-muted"><RefreshCw className="h-5 w-5 animate-spin text-brand" />전사 재고를 불러오는 중입니다.</div>
        </div>
      ) : requestError ? (
        <section className="rounded-[14px] border border-rose-200 bg-rose-50 px-5 py-5 text-rose-900 shadow-soft" role="alert">
          <div className="flex items-start gap-3"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" /><div><h2 className="text-[15px] font-black">전사 재고 조회 실패</h2><p className="mt-1 text-[13px] font-semibold">{requestError}</p></div></div>
        </section>
      ) : data ? (
        <>
          <div className="mb-4 grid gap-[14px] lg:grid-cols-[1.45fr_.95fr]">
            <section className="rounded-[14px] border border-border bg-surface px-5 py-5 shadow-soft sm:px-6">
              <div className="flex items-center gap-3">
                <Boxes className="h-6 w-6 text-ink" strokeWidth={2.2} aria-hidden="true" />
                <h3 className="text-[17px] font-black text-ink">보유재고 평가</h3>
              </div>
              {holdingsReady && selectedHoldingsTotal ? (
                <>
                  <div className="mt-4 grid grid-cols-2 rounded-[10px] border border-border bg-surface p-0.5" role="group" aria-label="보유재고 평가 기준">
                    {(["book", "current"] as const).map((basis) => {
                      const selected = valuation === basis;
                      return (
                        <button
                          key={basis}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => setValuation(basis)}
                          className={cn(
                            "inline-flex min-h-11 items-center justify-center gap-2 rounded-[8px] px-3 text-[12.5px] font-black transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30",
                            selected ? "border border-brand bg-brand/[.035] text-brand shadow-sm" : "text-muted hover:bg-surface-soft hover:text-ink"
                          )}
                        >
                          {basis === "book" ? "장부금액" : "현재환율 평가액"}
                          {selected ? <CheckCircle2 className="h-4 w-4" fill="currentColor" stroke="white" aria-hidden="true" /> : null}
                        </button>
                      );
                    })}
                  </div>
                  <p className="mt-5 text-center text-[34px] font-black leading-none tracking-[-0.04em] text-ink sm:text-[42px]">
                    {formatKrwEok(selectedHoldingsTotal)}
                  </p>
                  <div className="mx-auto mt-4 flex w-fit flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-[9px] border border-border bg-surface-soft px-4 py-2 text-[12px] font-bold text-muted">
                    <span>{valuation === "current" ? "장부금액" : "현재환율 평가액"}</span>
                    <span className="font-black text-ink">
                      {formatKrwEok(valuation === "current" ? holdingsReady.total_krw : holdingsReady.total_current_krw)}
                    </span>
                    <span aria-hidden="true">·</span>
                    <span>차이</span>
                    <span className={cn("font-black", numberFromKrw(holdingsReady.difference_krw) > 0 ? "text-rose-600" : numberFromKrw(holdingsReady.difference_krw) < 0 ? "text-blue-600" : "text-ink3")}>{formatSignedKrwEok(holdingsReady.difference_krw)}</span>
                  </div>
                  <p className="mt-3 flex items-center justify-center gap-1.5 text-center text-[11px] font-semibold text-muted2">
                    <Info className="h-3.5 w-3.5" aria-hidden="true" />
                    {valuation === "current" ? "조회 기준일 이하 최근 고시환율 적용" : "입고 시점 원화 단가가 반영된 장부금액"}
                  </p>
                </>
              ) : (
                <div className="mt-4"><HoldingsFailure message={holdingsFailureMessage} /></div>
              )}
            </section>
            {transitReady ? (
              <button
                type="button"
                onClick={() => setTransitDialogOpen(true)}
                aria-haspopup="dialog"
                className="group rounded-[14px] border border-border bg-surface px-5 py-5 text-left shadow-soft transition hover:border-brand/30 hover:bg-surface-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 sm:px-6"
              >
                <span className="flex items-center gap-3">
                  <Truck className="h-6 w-6 text-ink" strokeWidth={2.2} aria-hidden="true" />
                  <span className="text-[17px] font-black text-ink">운송중 재고</span>
                </span>
                <span className="mt-12 block text-center text-[34px] font-black leading-none tracking-[-0.04em] text-ink sm:text-[42px]">{formatKrwEok(transitReady.total_krw)}</span>
                <span className="mx-auto mt-5 flex w-fit items-center gap-2 rounded-[9px] border border-brand px-4 py-2 text-[12px] font-black text-brand">
                  <CircleDollarSign className="h-4 w-4" aria-hidden="true" /> 계약환율 기준
                </span>
                <span className="mt-5 flex items-center justify-center gap-1.5 text-center text-[11px] font-semibold text-muted2">
                  <Info className="h-3.5 w-3.5" aria-hidden="true" /> 인보이스별 계약환율 적용 · 현재환율 전환 대상 아님
                </span>
              </button>
            ) : (
              <section className="rounded-[14px] border border-rose-200 bg-rose-50 px-5 py-5 text-rose-900 shadow-soft sm:px-6">
                <div className="flex items-center gap-3"><Truck className="h-6 w-6" /><h3 className="text-[17px] font-black">운송중 재고</h3></div>
                <p className="mt-10 text-center text-[25px] font-black">갱신 실패</p>
                <p className="mt-3 text-center text-[12px] font-bold">부분 합계나 0원으로 대체하지 않았습니다.</p>
              </section>
            )}
          </div>

          <section className="mb-4 grid items-center gap-3 rounded-[11px] border border-brand/25 bg-brand/[.045] px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:px-6">
            <span className="flex min-w-0 items-center gap-3">
              <CircleDollarSign className="h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
              <span className="text-[12.5px] font-black text-ink">관리 기준 총 재고</span>
              <span className={cn("text-[24px] font-black leading-none", totalReady ? "text-brand" : "text-rose-600")}>{totalReady ? formatKrwEok(totalReady.total_krw) : "산출 불가"}</span>
            </span>
            <span className="hidden h-7 w-px bg-brand/15 sm:block" />
            <span className="flex items-center justify-start gap-1.5 text-[11.5px] font-bold text-ink3 sm:justify-center">
              보유 장부금액 + 운송중 계약환율 금액 <Info className="h-3.5 w-3.5 text-muted2" aria-hidden="true" />
            </span>
          </section>

          {holdingsReady ? (
            <div id="corporate-inventory-company-ranking">
              <CompanyRanking
                companies={holdingsReady.companies}
                totalKrw={valuation === "current" ? holdingsReady.total_current_krw : holdingsReady.total_krw}
                valuation={valuation}
              />
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-muted2">
            <span>기준일 · <span className="text-ink3"><KoreanDate value={data.as_of} /> · KST</span></span>
            <span>법인별 금액은 선택한 표시 기준에 따라 변경됩니다.</span>
          </div>
          {transitReady ? <TransitDestinations inTransit={transitReady} open={transitDialogOpen} onClose={() => setTransitDialogOpen(false)} /> : (
            <span className="sr-only">{transitFailureMessage}</span>
          )}
        </>
      ) : null}
      </div>
    </div>
  );
}
