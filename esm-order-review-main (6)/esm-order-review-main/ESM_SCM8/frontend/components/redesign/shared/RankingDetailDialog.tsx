"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2, Search, X } from "lucide-react";

import { cn, formatNumber } from "@/lib/utils";
import { Pagination } from "./Pagination";

export type RankingDetailRow = {
  id: string;
  label: string;
  detail?: string;
  amount?: string;
  amountKrw?: string;
  sharePct: number;
};

export type RankingDetailColumn = {
  key: string;
  label: string;
  badge?: { text: string; className: string };
  rows: RankingDetailRow[];
  valueLabel?: string;
  shareLabel?: string;
};

export function RankingDetailOpenButton({
  onClick,
  className
}: {
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[8px] border border-border bg-surface px-2.5 text-[11px] font-black text-ink transition hover:border-brand hover:text-brand",
        className
      )}
    >
      <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
      전체 보기
    </button>
  );
}

const PAGE_SIZE = 10;
const SEARCH_THRESHOLD = 10;

function RankingColumnPanel({
  resetKey,
  rows,
  valueLabel,
  shareLabel,
  onSelect,
  scrollClassName
}: {
  resetKey: string;
  rows: RankingDetailRow[];
  valueLabel: string;
  shareLabel: string;
  onSelect?: (row: RankingDetailRow) => void;
  scrollClassName: string;
}) {
  const [page, setPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    setPage(1);
    setSearchTerm("");
  }, [resetKey]);

  const canSearch = rows.length > SEARCH_THRESHOLD;
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filteredRows =
    canSearch && normalizedSearch
      ? rows.filter((row) => `${row.label} ${row.detail ?? ""}`.toLowerCase().includes(normalizedSearch))
      : rows;
  // 검색은 목록만 좁히고 순위는 전체 rows(이미 순위순으로 정렬된 원본)를 유지한다.
  const rankById = new Map(rows.map((row, index) => [row.id, index + 1]));
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pageRows = filteredRows.slice(pageStart, pageStart + PAGE_SIZE);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {canSearch ? (
        <div className="shrink-0 border-b border-divider px-4 py-3 sm:px-6">
          <div className="relative w-full">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted2" aria-hidden="true" />
            <input
              type="text"
              value={searchTerm}
              onChange={(event) => {
                setSearchTerm(event.target.value);
                setPage(1);
              }}
              placeholder="항목 검색"
              aria-label="항목 검색"
              className="h-9 w-full rounded-[8px] border border-border bg-surface pl-9 pr-3 text-[12.5px] font-semibold text-ink outline-none placeholder:text-muted2 focus:border-brand"
            />
          </div>
          {normalizedSearch ? (
            <p className="mt-1.5 text-[11px] font-semibold text-muted2">
              검색 결과 {formatNumber(filteredRows.length)}개 · 전체 순위 유지
            </p>
          ) : null}
        </div>
      ) : null}

      <div className={cn("px-4 sm:px-6", scrollClassName)}>
        <div className="sticky top-0 z-10 grid grid-cols-[42px_minmax(0,1fr)_110px] items-center border-b border-divider bg-surface py-3 text-[11px] font-black text-muted2 sm:grid-cols-[54px_minmax(0,1fr)_170px_100px]">
          <span>순위</span>
          <span>항목</span>
          <span className="text-right">{valueLabel}</span>
          <span className="hidden text-right sm:block">{shareLabel}</span>
        </div>
        {pageRows.length > 0 ? pageRows.map((row, index) => {
          const content = (
            <>
              <span className="text-[12px] font-black text-muted2">{rankById.get(row.id) ?? pageStart + index + 1}</span>
              <span className="min-w-0">
                <span className="block truncate text-[13px] font-black text-ink">{row.label}</span>
                {row.detail ? <span className="mt-0.5 block truncate text-[11px] font-semibold text-muted2">{row.detail}</span> : null}
                <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-surface-soft sm:hidden">
                  <span className="block h-full rounded-full bg-brand" style={{ width: `${Math.max(2, Math.min(100, row.sharePct))}%` }} />
                </span>
              </span>
              <span className="text-right">
                <span className="block text-[12.5px] font-black text-ink">{row.amount || "-"}</span>
                {row.amountKrw ? <span className="mt-0.5 block text-[10.5px] font-semibold text-muted2">{row.amountKrw}</span> : null}
                <span className="mt-0.5 block text-[11px] font-black text-brand sm:hidden">{formatNumber(row.sharePct, 1)}%</span>
              </span>
              <span className="hidden text-right sm:block">
                <span className="text-[12px] font-black text-ink">{formatNumber(row.sharePct, 1)}%</span>
                <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface-soft">
                  <span className="block h-full rounded-full bg-brand" style={{ width: `${Math.max(2, Math.min(100, row.sharePct))}%` }} />
                </span>
              </span>
            </>
          );
          return onSelect ? (
            <button
              key={row.id}
              type="button"
              onClick={() => onSelect(row)}
              className="grid w-full grid-cols-[42px_minmax(0,1fr)_110px] items-center gap-2 border-b border-rowline py-3.5 text-left transition hover:bg-surface-soft sm:grid-cols-[54px_minmax(0,1fr)_170px_100px] sm:gap-4"
            >
              {content}
            </button>
          ) : (
            <div
              key={row.id}
              className="grid grid-cols-[42px_minmax(0,1fr)_110px] items-center gap-2 border-b border-rowline py-3.5 sm:grid-cols-[54px_minmax(0,1fr)_170px_100px] sm:gap-4"
            >
              {content}
            </div>
          );
        }) : (
          <p className="py-16 text-center text-[13px] font-semibold text-muted2">
            {normalizedSearch ? "검색 결과가 없습니다." : "표시할 데이터가 없습니다."}
          </p>
        )}
      </div>

      {filteredRows.length > 0 ? (
        <footer className="flex shrink-0 items-center justify-center border-t border-divider px-4 py-3 sm:px-6">
          <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setPage} />
        </footer>
      ) : null}
    </div>
  );
}

export function RankingDetailDialog({
  open,
  title,
  subtitle,
  valueLabel = "매출",
  shareLabel = "점유율",
  rows,
  columns,
  onClose,
  onSelect
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  valueLabel?: string;
  shareLabel?: string;
  rows?: RankingDetailRow[];
  columns?: RankingDetailColumn[];
  onClose: () => void;
  onSelect?: (row: RankingDetailRow) => void;
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

  const totalRowCount = columns ? columns.reduce((sum, column) => sum + column.rows.length, 0) : (rows ?? []).length;

  return (
    <div className="fixed inset-0 z-[120] flex items-stretch justify-center bg-black/45 p-0 sm:p-5">
      <button type="button" aria-label="전체 순위 닫기" onClick={onClose} className="absolute inset-0 cursor-default" />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="ranking-detail-title"
        className="relative flex h-full w-full max-w-[1120px] flex-col overflow-hidden bg-surface shadow-2xl sm:h-[calc(100vh-40px)] sm:rounded-[18px] sm:border sm:border-border"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-divider px-5 py-4 sm:px-7 sm:py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="ranking-detail-title" className="text-[18px] font-black text-ink sm:text-[20px]">{title}</h2>
              <span className="rounded-full bg-surface-soft px-2.5 py-1 text-[11px] font-black text-muted2">
                전체 {formatNumber(totalRowCount)}개
              </span>
            </div>
            {subtitle ? <p className="mt-1.5 text-[12px] font-semibold text-muted2">{subtitle}</p> : null}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="전체 순위 닫기"
            onClick={onClose}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] border border-border bg-surface text-muted2 transition hover:border-brand hover:text-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>

        {columns ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-row md:divide-x md:divide-divider md:overflow-hidden">
            {columns.map((column) => (
              <div key={column.key} className="flex min-h-0 flex-col border-b border-divider last:border-b-0 md:flex-1 md:border-b-0">
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-divider px-4 py-3 sm:px-6">
                  <p className="text-[13px] font-black text-ink">
                    {column.label} <span className="font-semibold text-muted2">· {formatNumber(column.rows.length)}개</span>
                  </p>
                  {column.badge ? (
                    <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-black", column.badge.className)}>{column.badge.text}</span>
                  ) : null}
                </div>
                <RankingColumnPanel
                  resetKey={`${title}:${column.key}`}
                  rows={column.rows}
                  valueLabel={column.valueLabel ?? valueLabel}
                  shareLabel={column.shareLabel ?? shareLabel}
                  onSelect={onSelect}
                  scrollClassName="md:min-h-0 md:flex-1 md:overflow-y-auto pb-6"
                />
              </div>
            ))}
          </div>
        ) : (
          <RankingColumnPanel
            resetKey={title}
            rows={rows ?? []}
            valueLabel={valueLabel}
            shareLabel={shareLabel}
            onSelect={onSelect}
            scrollClassName="min-h-0 flex-1 overflow-y-auto pb-6"
          />
        )}
      </section>
    </div>
  );
}
