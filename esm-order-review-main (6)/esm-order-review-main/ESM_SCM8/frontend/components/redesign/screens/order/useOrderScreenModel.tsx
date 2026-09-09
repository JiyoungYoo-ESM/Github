"use client";

import { useEffect, useMemo, useState } from "react";

import { getLastAnalysisResult } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import type { AnalyzeResponse } from "@/types/api";
import { isVisibleAnalysisBrandOption, resolveFullOrderReviewDownload } from "../../shared/order-review-shared";
import { downloadFullOrderReviewXlsx, downloadOrderRowsXlsx } from "./orderExportXlsx";
import {
  adjustedOrderAmount,
  adjustedOrderQty,
  compareOrderRows,
  orderMoi,
  orderTableColumns,
  type InboundScenario,
  type OrderSortKey,
  type OrderTableColumnKey,
  type SortDirection
} from "./orderScreenModel";
import { useOrderScreenData } from "./useOrderScreenData";

export function useOrderScreenModel({
  analysisReady,
  currentAnalysisResult
}: {
  analysisReady: boolean;
  currentAnalysisResult: AnalyzeResponse | null;
}) {
  const { rows, latestRunMeta, loadFailed } = useOrderScreenData(analysisReady);
  const [exportError, setExportError] = useState("");
  const [exportingExcel, setExportingExcel] = useState(false);
  const [inboundScenario, setInboundScenario] = useState<InboundScenario>("before");
  const [selectedBrand, setSelectedBrand] = useState("all");
  const [orderSort, setOrderSort] = useState<{ key: OrderSortKey; direction: SortDirection }>({
    key: "amount",
    direction: "desc"
  });
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [columnWidths, setColumnWidths] = useState<Record<OrderTableColumnKey, number>>(() =>
    orderTableColumns.reduce(
      (widths, column) => ({
        ...widths,
        [column.key]: column.defaultWidth
      }),
      {} as Record<OrderTableColumnKey, number>
    )
  );

  const allRows = useMemo(() => rows ?? [], [rows]);
  // 발주 탭은 계정 유형과 관계없이 발주 의사결정에 필요한 금액을 표시한다.
  // 다른 분석 화면과 일반 계정용 다운로드의 금액 제한은 그대로 유지한다.
  const visibleOrderTableColumns = orderTableColumns;
  const brandOptions = useMemo(
    () =>
      Array.from(
        new Set(
          allRows
            .map((row) => displayBrandName(row.brand))
            .filter((brand) => brand && brand !== "-" && isVisibleAnalysisBrandOption(brand))
        )
      ).sort((a, b) => a.localeCompare(b, "ko")),
    [allRows]
  );
  useEffect(() => {
    if (selectedBrand !== "all" && !brandOptions.includes(selectedBrand)) {
      setSelectedBrand("all");
    }
  }, [brandOptions, selectedBrand]);
  const orderRows = useMemo(
    () => (selectedBrand === "all" ? allRows : allRows.filter((row) => displayBrandName(row.brand) === selectedBrand)),
    [allRows, selectedBrand]
  );
  const actionableRows = useMemo(() => orderRows.filter((row) => adjustedOrderQty(row, inboundScenario) > 0), [inboundScenario, orderRows]);
  const latestRunLabel = useMemo(() => {
    if (!latestRunMeta?.savedAt) return "";
    const parsed = new Date(latestRunMeta.savedAt);
    if (Number.isNaN(parsed.getTime())) return "";
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(parsed);
  }, [latestRunMeta]);
  const totalOrderQty = useMemo(
    () => actionableRows.reduce((sum, row) => sum + adjustedOrderQty(row, inboundScenario), 0),
    [actionableRows, inboundScenario]
  );
  const totalOrderAmount = useMemo(
    () => actionableRows.reduce((sum, row) => sum + adjustedOrderAmount(row, inboundScenario), 0),
    [actionableRows, inboundScenario]
  );
  const visibleRows = useMemo(
    () => [...orderRows].sort((a, b) => compareOrderRows(a, b, inboundScenario, orderSort.key, orderSort.direction)),
    [inboundScenario, orderRows, orderSort.direction, orderSort.key]
  );
  const totalPages = Math.max(Math.ceil(visibleRows.length / pageSize), 1);
  const currentPage = Math.min(page, totalPages);
  const pagedRows = useMemo(
    () => visibleRows.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [currentPage, pageSize, visibleRows]
  );
  const tableWidth = useMemo(
    () => visibleOrderTableColumns.reduce((sum, column) => sum + columnWidths[column.key], 0),
    [columnWidths, visibleOrderTableColumns]
  );

  const toggleOrderSort = (key: OrderSortKey) => {
    setOrderSort((current) => ({
      key,
      direction: current.key === key && current.direction === "desc" ? "asc" : "desc"
    }));
  };

  const startColumnResize = (key: OrderTableColumnKey, event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = columnWidths[key];
    const minWidth = orderTableColumns.find((column) => column.key === key)?.minWidth ?? 80;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onPointerMove = (moveEvent: PointerEvent) => {
      const nextWidth = Math.max(minWidth, startWidth + moveEvent.clientX - startX);
      setColumnWidths((current) => ({ ...current, [key]: nextWidth }));
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

  useEffect(() => {
    setPage(1);
  }, [inboundScenario, orderSort.direction, orderSort.key, pageSize, selectedBrand]);

  const exportFullOrderReviewExcel = async () => {
    if (exportingExcel) return;
    setExportError("");
    setExportingExcel(true);
    try {
      const result = await resolveFullOrderReviewDownload(currentAnalysisResult ?? getLastAnalysisResult());
      if (!result) {
        throw new Error("원본 ESM_order 파일을 복구하지 못했습니다. 분석을 다시 실행해 주세요.");
      }
      await downloadFullOrderReviewXlsx(result, inboundScenario, `ESM_order_review_${result.job_id}.xlsx`);
      setExportMenuOpen(false);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "원본 ESM_order 파일 다운로드에 실패했습니다.");
    } finally {
      setExportingExcel(false);
    }
  };

  const exportCurrentFilterExcel = async () => {
    if (exportingExcel) return;
    if (visibleRows.length === 0) {
      setExportError("내보낼 브랜드 데이터가 없습니다.");
      return;
    }
    setExportError("");
    setExportingExcel(true);
    try {
      const brandText = selectedBrand === "all" ? "all" : selectedBrand.replace(/[\\/:*?"<>|]/g, "_");
      await downloadOrderRowsXlsx(
        visibleRows,
        inboundScenario,
        `ESM_order_review_filtered_${brandText}_${new Date().toISOString().slice(0, 10)}.xlsx`,
        true
      );
      setExportMenuOpen(false);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "엑셀 파일 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setExportingExcel(false);
    }
  };

  return {
    rows,
    loadFailed,
    latestRunLabel,
    latestRunMeta,
    exportError,
    exportingExcel,
    exportMenuOpen,
    setExportMenuOpen,
    inboundScenario,
    setInboundScenario,
    selectedBrand,
    setSelectedBrand,
    brandOptions,
    orderSort,
    toggleOrderSort,
    page,
    setPage,
    pageSize,
    setPageSize,
    currentPage,
    totalPages,
    pagedRows,
    visibleRows,
    actionableRows,
    totalOrderQty,
    totalOrderAmount,
    visibleOrderTableColumns,
    columnWidths,
    startColumnResize,
    tableWidth,
    exportFullOrderReviewExcel,
    exportCurrentFilterExcel
  };
}
