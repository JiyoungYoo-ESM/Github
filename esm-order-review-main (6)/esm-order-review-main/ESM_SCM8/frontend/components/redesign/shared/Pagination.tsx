"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

const ELLIPSIS = "…" as const;

export function buildPageItems(currentPage: number, totalPages: number): (number | typeof ELLIPSIS)[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  if (currentPage <= 4) {
    return [1, 2, 3, 4, 5, ELLIPSIS, totalPages];
  }
  if (currentPage >= totalPages - 3) {
    return [1, ELLIPSIS, totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [1, ELLIPSIS, currentPage - 1, currentPage, currentPage + 1, ELLIPSIS, totalPages];
}

export function Pagination({
  currentPage,
  totalPages,
  onPageChange,
  className
}: {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center justify-center gap-1", className)}>
      <button
        type="button"
        aria-label="이전 페이지"
        disabled={currentPage === 1}
        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
        className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-border bg-surface text-muted2 transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted2"
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </button>
      {buildPageItems(currentPage, totalPages).map((item, index) =>
        item === ELLIPSIS ? (
          <span key={`ellipsis-${index}`} className="inline-flex h-8 min-w-[24px] items-center justify-center text-[12px] font-black text-muted2">
            {ELLIPSIS}
          </span>
        ) : (
          <button
            key={item}
            type="button"
            aria-current={item === currentPage ? "page" : undefined}
            onClick={() => onPageChange(item)}
            className={cn(
              "inline-flex h-8 min-w-[32px] items-center justify-center rounded-[8px] px-2 text-[12px] font-black transition",
              item === currentPage ? "bg-brand text-white" : "text-muted2 hover:bg-surface-soft hover:text-ink"
            )}
          >
            {item}
          </button>
        )
      )}
      <button
        type="button"
        aria-label="다음 페이지"
        disabled={currentPage === totalPages}
        onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
        className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-border bg-surface text-muted2 transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-muted2"
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
