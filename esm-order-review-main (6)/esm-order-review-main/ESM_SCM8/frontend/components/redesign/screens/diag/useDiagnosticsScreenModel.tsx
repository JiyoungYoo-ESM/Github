"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getCategoryCorrectionOptions, getSeasonTrendAnalysis, saveCategoryCorrections, useApiQuery } from "@/lib/api";
import { brandOf, productNameOf, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import type { CategoryCorrectionItem, CategoryCorrectionOptions } from "@/types/api";
import {
  buildDiagnosticCorrectionRows,
  buildDiagnosticRegionRows,
  diagnosticCorrectionDraft,
  diagnosticCorrectionKey,
  diagnosticEditable,
  type DiagnosticDraftCorrection
} from "./diagnosticsScreenModel";

const EMPTY_CATEGORY_OPTIONS: CategoryCorrectionOptions = { category1: [], category2ByCategory1: {} };

export function useDiagnosticsScreenModel() {
  const [drafts, setDrafts] = useState<Record<string, DiagnosticDraftCorrection>>({});
  const [savedCodes, setSavedCodes] = useState<Set<string>>(() => new Set());
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const { data: analysisResult, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const { data: options, hasError: optionsLoadFailed } = useApiQuery({
    query: useCallback(() => getCategoryCorrectionOptions(), []),
    initialData: EMPTY_CATEGORY_OPTIONS
  });
  const season = analysisResult?.seasonAnalysis ?? null;
  const ingredient = analysisResult?.ingredientAnalysis ?? null;

  useEffect(() => {
    if (optionsLoadFailed) setError("카테고리 목록을 불러오지 못했습니다.");
  }, [optionsLoadFailed]);

  const allCorrectionRows = useMemo(() => buildDiagnosticCorrectionRows(season?.uncategorizedSku ?? []), [season?.uncategorizedSku]);
  const correctionRows = useMemo(() => allCorrectionRows.filter((row) => !savedCodes.has(diagnosticCorrectionKey(row))), [allCorrectionRows, savedCodes]);
  const regionRows = useMemo(() => buildDiagnosticRegionRows(season?.countryCategoryMonthly ?? []), [season?.countryCategoryMonthly]);
  const mismatchRows = useMemo(() => ingredient?.unmatchedSku ?? [], [ingredient?.unmatchedSku]);
  const taggedSkuCount = useMemo(() => {
    const codes = new Set((ingredient?.skuTags ?? []).map((row) => skuCodeOf(row)).filter((code) => code && code !== "-"));
    return codes.size || (ingredient?.skuTags?.length ?? 0);
  }, [ingredient?.skuTags]);

  const completeItems = useMemo<CategoryCorrectionItem[]>(
    () =>
      correctionRows.flatMap((row) => {
        const productCode = diagnosticCorrectionKey(row);
        if (!diagnosticEditable(row)) return [];
        const draft = diagnosticCorrectionDraft(row, drafts[productCode]);
        if (!productCode || productCode === "-" || !draft.category1 || !draft.category2) return [];
        return [
          {
            productCode,
            category1: draft.category1,
            category2: draft.category2,
            productName: productNameOf(row),
            brand: brandOf(row)
          }
        ];
      }),
    [correctionRows, drafts]
  );

  const updateDraft = (productCode: string, patch: Partial<DiagnosticDraftCorrection>) => {
    setDrafts((current) => {
      const previous = current[productCode] ?? { category1: "", category2: "" };
      const next = { ...previous, ...patch };
      if (patch.category1 && patch.category1 !== previous.category1) {
        next.category2 = "";
      }
      return { ...current, [productCode]: next };
    });
    setMessage("");
    setError("");
  };

  const handleSave = async () => {
    if (completeItems.length === 0) {
      setError("저장할 SKU의 대분류/중분류를 선택해 주세요.");
      return;
    }
    setIsSaving(true);
    setMessage("");
    setError("");
    try {
      const result = await saveCategoryCorrections(completeItems);
      setSavedCodes((current) => {
        const next = new Set(current);
        completeItems.forEach((item) => next.add(item.productCode));
        return next;
      });
      setMessage(`${formatNumber(result.saved_count)}개 SKU 보정값을 저장했습니다. 다시 분석하면 결과에 반영됩니다.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분류 보정값 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return {
    loading,
    loadFailed,
    options,
    drafts,
    correctionRows,
    regionRows,
    mismatchRows,
    taggedSkuCount,
    completeItems,
    updateDraft,
    handleSave,
    isSaving,
    message,
    error
  };
}
