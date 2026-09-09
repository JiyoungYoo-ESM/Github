"use client";

import { useEffect, useMemo, useState } from "react";

import { downloadHref, getLastAnalysisResult } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import { isVisibleAnalysisBrandOption, resolveFullOrderReviewDownload } from "../../shared/order-review-shared";
import { downloadStockGapRowsXlsx } from "./gapExportXlsx";
import { isDormantStockGapItem } from "@/lib/stock-gap";
import { formatNumber } from "@/lib/utils";
import {
  compareStockGapRows,
  gapSortLabels,
  gapTableColumns,
  isEtaMissingRow,
  stockGapShortageQty,
  type GapSortKey,
  type GapTableColumnKey,
  type SortDirection
} from "./gapScreenModel";
import { useGapScreenData } from "./useGapScreenData";

export function useGapScreenModel({ analysisReady }: { analysisReady: boolean }) {
  const { rows, loadFailed } = useGapScreenData(analysisReady);
  const [selectedBrand, setSelectedBrand] = useState("전체");
  const [showDormantRows, setShowDormantRows] = useState(false);
  const [gapSort, setGapSort] = useState<{ key: GapSortKey; direction: SortDirection }>({
    key: "gap",
    direction: "desc"
  });
  const [gapExportMenuOpen, setGapExportMenuOpen] = useState(false);
  const [gapExportError, setGapExportError] = useState("");
  const [gapExportingExcel, setGapExportingExcel] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [gapColumnWidths, setGapColumnWidths] = useState<Record<GapTableColumnKey, number>>(() =>
    gapTableColumns.reduce(
      (widths, column) => ({
        ...widths,
        [column.key]: column.defaultWidth
      }),
      {} as Record<GapTableColumnKey, number>
    )
  );

  const brandOptions = useMemo(() => {
    const brands = (rows ?? [])
      .map((row) => displayBrandName(row.brand))
      .filter((brand) => brand && brand !== "-" && brand !== "상품명 미확인" && isVisibleAnalysisBrandOption(brand));
    return Array.from(new Set(brands)).sort((a, b) => a.localeCompare(b, "ko"));
  }, [rows]);
  // 판매·재고·운송·미입고가 전부 없는 행은 재고 공백을 판정할 근거가 없어 기본 목록에서 뺀다.
  const dormantRowCount = useMemo(() => (rows ?? []).filter(isDormantStockGapItem).length, [rows]);
  const visibleRows = useMemo(() => {
    const baseRows = showDormantRows ? (rows ?? []) : (rows ?? []).filter((row) => !isDormantStockGapItem(row));
    const filteredRows = selectedBrand === "전체" ? baseRows : baseRows.filter((row) => displayBrandName(row.brand) === selectedBrand);
    return [...filteredRows].sort((a, b) => compareStockGapRows(a, b, gapSort.key, gapSort.direction));
  }, [gapSort.direction, gapSort.key, rows, selectedBrand, showDormantRows]);
  const gapRiskRows = visibleRows.filter((row) => row.status === "stock_gap" || row.status === "urgent_replenishment");
  const longGapRows = gapRiskRows.filter((row) => (row.gapDays ?? 0) >= 7);
  const etaMissingRows = visibleRows.filter(isEtaMissingRow);
  const noInboundRows = visibleRows.filter((row) => row.status === "stockout_no_inbound");
  const totalShortageQty = gapRiskRows.reduce((sum, row) => sum + stockGapShortageQty(row), 0);
  const totalPages = Math.max(Math.ceil(visibleRows.length / pageSize), 1);
  const currentPage = Math.min(page, totalPages);
  const pagedRows = visibleRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const gapTableWidth = useMemo(
    () => gapTableColumns.reduce((sum, column) => sum + gapColumnWidths[column.key], 0),
    [gapColumnWidths]
  );

  const startGapColumnResize = (key: GapTableColumnKey, event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = gapColumnWidths[key];
    const minWidth = gapTableColumns.find((column) => column.key === key)?.minWidth ?? 80;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onPointerMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.max(minWidth, startWidth + moveEvent.clientX - startX);
      setGapColumnWidths((current) => ({ ...current, [key]: nextWidth }));
    };

    const stopResize = () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
  };

  const toggleGapSort = (key: GapSortKey) => {
    setGapSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc"
    }));
  };

  useEffect(() => {
    setPage(1);
  }, [gapSort.direction, gapSort.key, pageSize, selectedBrand, showDormantRows]);

  useEffect(() => {
    if (selectedBrand !== "전체" && !brandOptions.includes(selectedBrand)) {
      setSelectedBrand("전체");
    }
  }, [brandOptions, selectedBrand]);

  const exportCurrentGapFilterExcel = async () => {
    if (gapExportingExcel) return;
    if (visibleRows.length === 0) {
      setGapExportError("내보낼 재고공백 SKU가 없습니다.");
      return;
    }
    setGapExportError("");
    setGapExportingExcel(true);
    try {
      const brandText = selectedBrand === "전체" ? "all" : selectedBrand.replace(/[\\/:*?"<>|]/g, "_");
      const brandScope = selectedBrand === "전체" ? "전체 브랜드 데이터" : `${selectedBrand} 데이터`;
      await downloadStockGapRowsXlsx(visibleRows, `ESM_stock_gap_filtered_${brandText}_${new Date().toISOString().slice(0, 10)}.xlsx`, {
        brandLabel: selectedBrand,
        sortLabel: `${gapSortLabels[gapSort.key]} ${gapSort.direction === "desc" ? "내림차순" : "오름차순"}`,
        // 화면에서 숨긴 행은 파일에도 없다. 무엇이 빠졌는지 파일 안에 남긴다.
        scopeLabel: showDormantRows
          ? `${brandScope} · 판매·재고 없는 SKU 포함`
          : `${brandScope} · 판매·재고 없는 SKU ${formatNumber(dormantRowCount)}건 제외`
      });
      setGapExportMenuOpen(false);
    } catch (error) {
      setGapExportError(error instanceof Error ? error.message : "엑셀 파일 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setGapExportingExcel(false);
    }
  };

  const exportFullGapExcel = async () => {
    if (gapExportingExcel) return;
    setGapExportError("");
    setGapExportingExcel(true);
    try {
      const result = await resolveFullOrderReviewDownload(getLastAnalysisResult());
      if (!result) {
        throw new Error("원본 ESM_order 파일을 복구하지 못했습니다. 분석을 다시 실행해 주세요.");
      }
      const link = document.createElement("a");
      link.href = downloadHref(result);
      link.download = `ESM_order_review_${result.job_id}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setGapExportMenuOpen(false);
    } catch (error) {
      setGapExportError(error instanceof Error ? error.message : "원본 ESM_order 파일 다운로드에 실패했습니다.");
    } finally {
      setGapExportingExcel(false);
    }
  };

  return {
    rows,
    loadFailed,
    selectedBrand,
    setSelectedBrand,
    brandOptions,
    showDormantRows,
    setShowDormantRows,
    dormantRowCount,
    gapSort,
    toggleGapSort,
    gapExportMenuOpen,
    setGapExportMenuOpen,
    gapExportError,
    gapExportingExcel,
    page,
    setPage,
    pageSize,
    setPageSize,
    currentPage,
    totalPages,
    pagedRows,
    visibleRows,
    gapRiskRows,
    longGapRows,
    etaMissingRows,
    noInboundRows,
    totalShortageQty,
    gapColumnWidths,
    startGapColumnResize,
    gapTableWidth,
    exportCurrentGapFilterExcel,
    exportFullGapExcel
  };
}
