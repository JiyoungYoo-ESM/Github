"use client";

import { cn, formatNumber } from "@/lib/utils";
import { skuCodeOf } from "@/lib/global-demand-view-model";
import type { IngredientAnalysis } from "@/types/api";
import { uniqueValueCount } from "../../shared/ingredient-analysis";
import { IngredientMetricCard } from "./IngredientScreenParts";
import { buildDetectedIngredientKeywordRows, keywordListOf } from "./ingredientScreenModel";
import { ingredientOf } from "@/lib/global-demand-view-model";

export function IngredientMappingScreen({ ingredient }: { ingredient: IngredientAnalysis | null }) {
  const keywordMap = ingredient?.keywordMap ?? [];
  const detectedRows = buildDetectedIngredientKeywordRows(ingredient);
  const dictionaryRows = keywordMap.flatMap((row) => keywordListOf(row).map((keyword) => ({ keyword, standard: ingredientOf(row), skuCodes: new Set<string>() })));
  const tableRows = detectedRows.length > 0 ? detectedRows : dictionaryRows;
  const totalKeywordCount = detectedRows.length || dictionaryRows.length;
  const taggedSkuCount = uniqueValueCount(ingredient?.skuTags ?? [], skuCodeOf);
  const unmatchedSkuCount = ingredient?.unmatchedSku?.length ?? 0;
  const mappingRate = taggedSkuCount + unmatchedSkuCount > 0 ? (taggedSkuCount / (taggedSkuCount + unmatchedSkuCount)) * 100 : 0;

  return (
    <>
      <div className="mb-[16px] grid grid-cols-4 gap-[14px]">
        <IngredientMetricCard label="감지 키워드" value={`${formatNumber(totalKeywordCount)}건`} sub={detectedRows.length > 0 ? "CMS 상품명 기준" : "성분 사전 등록"} />
        <IngredientMetricCard label="성분 태깅 SKU" value={`${formatNumber(taggedSkuCount)}건`} sub="표준 성분명으로 분류" tone="pos" />
        <IngredientMetricCard label="성분 미매칭 SKU" value={`${formatNumber(unmatchedSkuCount)}건`} sub="검수 및 추가 매칭 필요" tone="warn" />
        <IngredientMetricCard label="자동 매핑률" value={`${formatNumber(mappingRate, 1)}%`} sub="성분 사전 기준" />
      </div>

      <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
        <div className="flex items-center justify-between border-b border-divider px-[18px] py-[16px]">
          <h3 className="text-[15px] font-black text-ink">CMS 감지 키워드 매핑 결과</h3>
          <p className="text-[12px] font-semibold text-muted2">상품명에서 감지된 키워드 기준</p>
        </div>
        <table className="w-full table-fixed border-collapse text-[13px]">
          <thead>
            <tr className="bg-surface-soft text-muted">
              <th className="w-[42%] border-b border-divider px-[16px] py-[12px] text-left font-black">감지 키워드</th>
              <th className="border-b border-divider px-[16px] py-[12px] text-left font-black">표준 성분명</th>
              <th className="w-[220px] border-b border-divider px-[16px] py-[12px] text-left font-black">태깅 SKU</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.slice(0, 50).map((row) => (
              <tr key={`${row.keyword}-${row.standard}`}>
                <td className="border-b border-rowline px-[16px] py-[13px] font-black text-ink">{row.keyword}</td>
                <td className="border-b border-rowline px-[16px] py-[13px] font-semibold text-ink3">{row.standard}</td>
                <td className="border-b border-rowline px-[16px] py-[13px]">
                  <span
                    className={cn(
                      "inline-flex h-[24px] items-center rounded-[7px] px-[10px] text-[11px] font-black",
                      "bg-pos/10 text-pos"
                    )}
                  >
                    {row.skuCodes.size > 0 ? `매핑 완료 · ${formatNumber(row.skuCodes.size)} SKU` : "매핑 완료"}
                  </span>
                </td>
              </tr>
            ))}
            {tableRows.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-[16px] py-[36px] text-center text-[13px] font-bold text-muted2">
                  성분 매핑 데이터가 없습니다. 데이터 입력에서 분석 시작을 먼저 실행해 주세요.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
      <p className="mt-[14px] text-[12px] font-semibold italic text-muted2">
        성분 매칭이 완료될수록 성분 순위·성장 분석의 정확성이 높아집니다. 미매핑 항목은 신뢰도 연결에서도 반영됩니다.
      </p>
    </>
  );
}
