"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getCategoryCorrectionOptions, saveCategoryCorrections } from "@/lib/api";
import { getCountryRegion, needsRegionReview } from "@/lib/region-groups";
import type { CategoryCorrectionItem, CategoryCorrectionOptions, IngredientAnalysis, SeasonAnalysis } from "@/types/api";
import { numberValue, textValue } from "./SeasonHeatmap";
import { SeasonTrendTable } from "./SeasonTrendTable";

type MappingCheckTabProps = {
  season: SeasonAnalysis;
  ingredient: IngredientAnalysis;
  hasSalesHistory: boolean;
  hasProdList: boolean;
};

type DraftCorrection = {
  category1: string;
  category2: string;
};

const UNMAPPED = "미분류";

function usableCategory(value: unknown) {
  const text = textValue(value);
  return text && text !== UNMAPPED ? text : "";
}

function correctionKey(row: Record<string, unknown>) {
  return textValue(row["상품코드"]);
}

function buildCorrectionRows(rows: Array<Record<string, unknown>>) {
  const bySku = new Map<string, Record<string, unknown>>();
  rows.forEach((row) => {
    const code = correctionKey(row);
    if (!code) {
      return;
    }
    const existing = bySku.get(code);
    if (!existing || numberValue(row["판매수량"]) > numberValue(existing["판매수량"])) {
      bySku.set(code, row);
    }
  });
  return Array.from(bySku.values()).sort((a, b) => numberValue(b["판매수량"]) - numberValue(a["판매수량"]));
}

function buildRegionReviewRows(rows: Array<Record<string, unknown>>) {
  const countries = new Map<string, { qty: number; amount: number }>();
  rows.forEach((row) => {
    const country = textValue(row["국가"]) || "미상";
    const current = countries.get(country) ?? { qty: 0, amount: 0 };
    current.qty += numberValue(row["판매수량"]);
    current.amount += numberValue(row["판매금액"]);
    countries.set(country, current);
  });

  return Array.from(countries.entries())
    .map(([country, totals]) => {
      const regionInfo = getCountryRegion(country);
      return { country, ...totals, regionInfo };
    })
    .filter((item) => needsRegionReview(item.regionInfo))
    .sort((a, b) => b.qty - a.qty);
}

function unmappedReason(row: Record<string, unknown>, hasProdList: boolean) {
  if (!hasProdList) {
    return "상품목록 파일이 없어 카테고리를 확인할 수 없습니다.";
  }

  const category1 = textValue(row["기능구분1"]);
  const category2 = textValue(row["기능구분2"]);
  const missingCategory1 = !category1 || category1 === UNMAPPED;
  const missingCategory2 = !category2 || category2 === UNMAPPED;

  if (missingCategory1 && missingCategory2) {
    return "상품목록에서 대분류와 중분류를 찾지 못했습니다.";
  }
  if (missingCategory1) {
    return "상품목록에서 대분류를 찾지 못했습니다.";
  }
  if (missingCategory2) {
    return "상품목록에서 중분류를 찾지 못했습니다.";
  }
  return "상품목록 매핑 확인이 필요합니다.";
}

function correctionDraft(row: Record<string, unknown>, draft?: DraftCorrection): DraftCorrection {
  return {
    category1: draft?.category1 ?? usableCategory(row["기능구분1"]),
    category2: draft?.category2 ?? usableCategory(row["기능구분2"])
  };
}

export function MappingCheckTab({ season, ingredient, hasSalesHistory, hasProdList }: MappingCheckTabProps) {
  const allCorrectionRows = useMemo(() => buildCorrectionRows(season.uncategorizedSku ?? []), [season.uncategorizedSku]);
  const regionReviewRows = useMemo(
    () => buildRegionReviewRows(season.countryCategoryMonthly ?? []),
    [season.countryCategoryMonthly]
  );
  const [options, setOptions] = useState<CategoryCorrectionOptions>({ category1: [], category2ByCategory1: {} });
  const [drafts, setDrafts] = useState<Record<string, DraftCorrection>>({});
  const [savedCodes, setSavedCodes] = useState<Set<string>>(() => new Set());
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const correctionRows = useMemo(
    () => allCorrectionRows.filter((row) => !savedCodes.has(correctionKey(row))),
    [allCorrectionRows, savedCodes]
  );
  const diagnosticCards = [
    {
      label: "분류 필요 SKU",
      value: correctionRows.length,
      tone: correctionRows.length > 0 ? "amber" : "emerald"
    },
    {
      label: "성분 미매칭 SKU",
      value: ingredient.unmatchedSku?.length ?? 0,
      tone: (ingredient.unmatchedSku?.length ?? 0) > 0 ? "amber" : "emerald"
    },
    {
      label: "권역 확인 국가",
      value: regionReviewRows.length,
      tone: regionReviewRows.length > 0 ? "amber" : "emerald"
    },
    {
      label: "성분 태깅 SKU",
      value: ingredient.skuTags?.length ?? 0,
      tone: "slate"
    }
  ];

  useEffect(() => {
    let mounted = true;
    getCategoryCorrectionOptions()
      .then((result) => {
        if (mounted) {
          setOptions(result);
        }
      })
      .catch(() => {
        if (mounted) {
          setError("카테고리 목록을 불러오지 못했습니다.");
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const completeItems = useMemo<CategoryCorrectionItem[]>(
    () =>
      correctionRows.flatMap((row) => {
          const productCode = correctionKey(row);
          const draft = correctionDraft(row, drafts[productCode]);
          if (!productCode || !draft?.category1 || !draft?.category2) {
            return [];
          }
          return [{
            productCode,
            category1: draft.category1,
            category2: draft.category2,
            productName: textValue(row["상품명"]),
            brand: textValue(row["브랜드"])
          }];
        }),
    [correctionRows, drafts]
  );

  const updateDraft = (productCode: string, patch: Partial<DraftCorrection>) => {
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
      setMessage(`${result.saved_count}개 SKU 보정값을 저장했습니다. 다시 분석하면 결과에 반영됩니다.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분류 보정값 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {!hasSalesHistory ? (
        <div className="rounded-lg border border-amber-100 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          장기 판매이력 파일이 업로드되지 않아 시즌 분석/성분 트렌드 분석을 표시할 수 없습니다. 장기 판매이력 파일을 추가 업로드하면 해당 분석 결과가 표시됩니다.
        </div>
      ) : null}
      {hasSalesHistory && !hasProdList ? (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800">
          상품목록 파일이 없어 대분류/중분류 분석 정확도가 제한됩니다. 카테고리는 {UNMAPPED}로 처리됩니다.
        </div>
      ) : null}

      <section className="rounded-lg border border-line bg-white p-5">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-400">Diagnostics</p>
          <h3 className="mt-1 text-lg font-bold text-slate-950">데이터 진단 요약</h3>
          <p className="mt-1 text-sm text-slate-600">
            분석 결과를 보기 전에 확인이 필요한 미분류, 성분 미매칭, 권역 매핑 항목만 요약합니다.
          </p>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {diagnosticCards.map((item) => (
            <div
              key={item.label}
              className={`rounded-lg border px-4 py-3 ${
                item.tone === "amber"
                  ? "border-amber-200 bg-amber-50"
                  : item.tone === "emerald"
                    ? "border-emerald-200 bg-emerald-50"
                    : "border-slate-200 bg-slate-50"
              }`}
            >
              <p className="text-xs font-semibold text-slate-500">{item.label}</p>
              <p className="mt-1 text-2xl font-black text-slate-950">{item.value.toLocaleString()}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-white p-5">
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-bold text-slate-950">권역 기준 확인</h3>
          <p className="text-sm text-slate-600">
            국가별 데이터를 유럽, 중동유럽, 기타 권역으로 묶기 전에 회사 기준 확인이 필요한 국가를 점검합니다.
          </p>
        </div>

        {regionReviewRows.length === 0 ? (
          <div className="mt-4 rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
            현재 데이터에서 권역 기준 확인이 필요한 국가는 없습니다.
          </div>
        ) : (
          <div className="mt-4 overflow-hidden rounded-lg border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-bold text-slate-500">
                <tr>
                  <th className="px-4 py-3">국가</th>
                  <th className="px-4 py-3">현재 권역</th>
                  <th className="px-4 py-3 text-right">판매수량</th>
                  <th className="px-4 py-3">확인 이슈</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {regionReviewRows.map((item) => (
                  <tr key={item.country}>
                    <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{item.country}</td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700">
                        {item.regionInfo.region}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">
                      {numberValue(item.qty).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{item.regionInfo.note ?? "회사 권역 기준 확인이 필요합니다."}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <SeasonTrendTable title="매핑 현황" rows={season.mappingQuality} />

      <section className="rounded-lg border border-line bg-white p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-950">분류 필요 SKU</h3>
            <p className="mt-1 text-sm text-slate-600">
              판매이력에는 있지만 상품목록에서 카테고리를 찾지 못한 SKU입니다. 대분류/중분류를 저장하면 다음 분석부터 자동으로 반영됩니다.
            </p>
          </div>
          <Button onClick={handleSave} disabled={isSaving || completeItems.length === 0}>
            {isSaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            선택값 저장 ({completeItems.length})
          </Button>
        </div>

        {message ? (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
            <Check className="h-4 w-4" />
            {message}
          </div>
        ) : null}
        {error ? <div className="mt-4 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div> : null}

        {correctionRows.length === 0 ? (
          <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm font-medium text-slate-500">
            지금 저장할 SKU가 없습니다.
          </div>
        ) : (
          <div className="mt-5 overflow-hidden rounded-lg border border-slate-200">
            <div className="max-h-[520px] overflow-auto">
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs font-bold text-slate-500">
                  <tr>
                    <th className="px-4 py-3">상품코드</th>
                    <th className="px-4 py-3">브랜드</th>
                    <th className="px-4 py-3">상품명</th>
                    <th className="px-4 py-3">미분류 사유</th>
                    <th className="px-4 py-3 text-right">판매수량</th>
                    <th className="px-4 py-3">대분류</th>
                    <th className="px-4 py-3">중분류</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {correctionRows.map((row) => {
                    const productCode = correctionKey(row);
                    const draft = correctionDraft(row, drafts[productCode]);
                    const category2Options = draft.category1 ? options.category2ByCategory1[draft.category1] ?? [] : [];
                    const reason = unmappedReason(row, hasProdList);
                    return (
                      <tr key={productCode} className="bg-white">
                        <td className="whitespace-nowrap px-4 py-3 font-semibold text-slate-900">{productCode}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-slate-700">{textValue(row["브랜드"]) || "-"}</td>
                        <td className="min-w-[320px] px-4 py-3 text-slate-700">{textValue(row["상품명"]) || "-"}</td>
                        <td className="min-w-[260px] px-4 py-3 text-slate-600">{reason}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">{numberValue(row["판매수량"]).toLocaleString()}</td>
                        <td className="px-4 py-3">
                          <select
                            value={draft.category1}
                            onChange={(event) => updateDraft(productCode, { category1: event.target.value })}
                            className="h-9 w-44 rounded-md border border-slate-200 bg-white px-2 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                          >
                            <option value="">선택</option>
                            {options.category1.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-4 py-3">
                          <select
                            value={draft.category2}
                            onChange={(event) => updateDraft(productCode, { category2: event.target.value })}
                            disabled={!draft.category1}
                            className="h-9 w-44 rounded-md border border-slate-200 bg-white px-2 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950 disabled:bg-slate-100"
                          >
                            <option value="">선택</option>
                            {category2Options.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <SeasonTrendTable title="성분 미매칭 SKU" rows={ingredient.unmatchedSku} />
      <SeasonTrendTable title="성분 키워드 맵" rows={ingredient.keywordMap} />

      <details className="group">
        <summary className="cursor-pointer rounded-lg border border-slate-200 bg-white px-5 py-4 text-sm font-bold text-slate-800 transition hover:border-slate-300">
          성분 SKU 태깅 성공 목록 보기
        </summary>
        <div className="mt-4">
          <SeasonTrendTable title="성분 SKU 태깅 결과" rows={ingredient.skuTags} />
        </div>
      </details>
    </div>
  );
}
