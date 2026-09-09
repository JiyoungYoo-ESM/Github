"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { cn, formatNumber } from "@/lib/utils";

const pageSizeOptions = [100, 300, 500];

type PaginationControlsProps = {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  className?: string;
};

function pageRange(page: number, totalPages: number) {
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, start + 4);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

export function PaginationControls({
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
  className
}: PaginationControlsProps) {
  const totalPages = Math.max(Math.ceil(totalItems / pageSize), 1);
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-3", className)}>
      <p className="text-sm font-medium text-slate-500">
        {formatNumber(startItem)}-{formatNumber(endItem)} / 총 {formatNumber(totalItems)}건
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {onPageSizeChange ? (
          <Select
            value={String(pageSize)}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            wrapperClassName="w-32"
            aria-label="페이지당 표시 개수"
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {formatNumber(option)}개씩
              </option>
            ))}
          </Select>
        ) : null}

        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          aria-label="이전 페이지"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>

        <div className="flex items-center gap-1">
          {pageRange(currentPage, totalPages).map((item) => (
            <Button
              key={item}
              type="button"
              variant={item === currentPage ? "default" : "ghost"}
              size="sm"
              className="min-w-9 px-2"
              onClick={() => onPageChange(item)}
            >
              {item}
            </Button>
          ))}
        </div>

        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          aria-label="다음 페이지"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
