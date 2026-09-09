"use client";

import { useEffect, useState } from "react";
import { cn, formatNumber } from "@/lib/utils";
import type { IngredientAnalysis, MonthCoverage } from "@/types/api";
import type { ComparisonBasis } from "../../lib/types";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { ingredientCoverageStats, uniqueValueCount } from "../../shared/ingredient-analysis";
import {
  completedYtdComparableYearWindow,
  completedYtdPeriodLabel,
  latestComparableMonths,
  shortMonthPairLabel
} from "../../lib/yoy-comparison";
import { ingredientOf } from "@/lib/global-demand-view-model";
import { IngredientMetricCard } from "./IngredientScreenParts";
import { buildIngredientRankRows, ingredientYoyClass } from "./ingredientScreenModel";
import { useUserPermissions } from "@/lib/use-user-permissions";

export function IngredientRankScreen({
  ingredient,
  monthCoverage,
  comparisonBasis,
  analysisOptions
}: {
  ingredient: IngredientAnalysis | null;
  monthCoverage: MonthCoverage[];
  comparisonBasis: ComparisonBasis;
  analysisOptions: Record<string, unknown> | null;
}) {
  const { canViewAmountData } = useUserPermissions();
  const rows = buildIngredientRankRows(ingredient, comparisonBasis, monthCoverage);
  const [ingredientPage, setIngredientPage] = useState(1);
  const coverage = ingredientCoverageStats(ingredient);
  const matchedIngredientCount = uniqueValueCount(ingredient?.summary ?? [], ingredientOf);
  const topIngredient = rows[0]?.ingredient ?? "-";
  const momPeriods = latestComparableMonths(ingredient?.monthlyTrend ?? []);
  const momLabel = shortMonthPairLabel(momPeriods);
  // 테이블 헤더는 지표명(MoM/월 비교)과 비교 기간을 위아래로 나눠 표기한다.
  const [momMetricName, ...momDetailParts] = momLabel.split(" · ");
  const momPairDetail = momDetailParts.join(" · ");
  const completeMonthKeys = monthCoverage.length > 0
    ? new Set(monthCoverage.filter((item) => item.status === "complete").map((item) => item.month))
    : undefined;
  const ytdWindow = completedYtdComparableYearWindow(ingredient?.monthlyTrend ?? [], completeMonthKeys);
  const comparisonHelp = `매출액 기준 · ${completedYtdPeriodLabel(ytdWindow)} · ${momLabel} 기준`;
  const averageEurKrwRate =
    Number(analysisOptions?.average_eur_krw_rate) > 0
      ? Number(analysisOptions?.average_eur_krw_rate)
      : null;
  const ingredientPageSize = 10;
  const ingredientPageCount = Math.max(1, Math.ceil(rows.length / ingredientPageSize));
  const safeIngredientPage = Math.min(ingredientPage, ingredientPageCount);
  const visibleRows = rows.slice((safeIngredientPage - 1) * ingredientPageSize, safeIngredientPage * ingredientPageSize);
  const visibleIngredientStart = rows.length > 0 ? (safeIngredientPage - 1) * ingredientPageSize + 1 : 0;
  const visibleIngredientEnd = Math.min(safeIngredientPage * ingredientPageSize, rows.length);

  useEffect(() => {
    if (ingredientPage > ingredientPageCount) setIngredientPage(ingredientPageCount);
  }, [ingredientPage, ingredientPageCount]);

  return (
    <>
      <div className="mb-[16px] grid grid-cols-4 gap-[14px]">
        <IngredientMetricCard label="매칭 성분 수" value={`${formatNumber(matchedIngredientCount)}종`} sub="성분 사전 기준" />
        <IngredientMetricCard label="성분 미매칭 SKU" value={`${formatNumber(coverage.unmatchedSkuCount)}건`} sub="상품명/성분명 점검 필요" tone="warn" />
        <IngredientMetricCard label="매출 상위 성분" value={topIngredient} sub="분석 기간 매출 기준" tone="pos" />
        <IngredientMetricCard label="성분 태깅 SKU" value={`${formatNumber(coverage.matchedSkuCount)}개`} sub="성분 기준으로 분류된 SKU" />
      </div>

      <div className="grid gap-[16px] xl:grid-cols-[minmax(880px,1fr)_minmax(360px,0.65fr)]">
        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-center justify-between border-b border-divider px-[18px] py-[16px]">
            <h3 className="text-[15px] font-black text-ink">성분별 순위 · 성장</h3>
            <div className="flex items-center gap-3">
              <span className="text-[12px] font-semibold text-muted2">
                {formatNumber(visibleIngredientStart)}-{formatNumber(visibleIngredientEnd)} / {formatNumber(rows.length)}
              </span>
              <p className="text-[12px] font-semibold text-muted2">{comparisonHelp}</p>
            </div>
          </div>
          <table className="w-full table-fixed border-collapse text-[13px]">
            <thead>
              <tr className="bg-surface-soft text-muted">
                <th className="w-[235px] border-b border-divider px-[16px] py-[12px] text-left font-black">성분</th>
                <th className="w-[190px] border-b border-divider px-[14px] py-[12px] text-right font-black">{canViewAmountData ? "매출액" : "매출 비중"}</th>
                <th className="w-[70px] border-b border-divider px-[10px] py-[12px] text-right font-black">YTD YoY</th>
                <th className="w-[125px] border-b border-divider px-[10px] py-[12px] text-right font-black">{momMetricName}{momPairDetail ? <><br /><span className="text-[11px] font-bold text-muted2">{momPairDetail}</span></> : null}</th>
                <th className="w-[150px] border-b border-divider px-[12px] py-[12px] text-left font-black">주요 국가</th>
                <th className="w-[145px] border-b border-divider px-[12px] py-[12px] text-left font-black">주요 브랜드</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => (
                <tr key={row.ingredient}>
                  <td className="border-b border-rowline px-[16px] py-[13px]">
                    <span className="mr-[10px] inline-block w-[20px] font-black text-muted2">{(safeIngredientPage - 1) * ingredientPageSize + index + 1}</span>
                    <span className="font-black text-ink">{row.ingredient}</span>
                  </td>
                  <td className="border-b border-rowline px-[16px] py-[13px]">
                    <div className="flex items-center justify-end gap-[10px]">
                      <div className="h-[5px] w-[112px] overflow-hidden rounded-full bg-row">
                        <div className="h-full rounded-full bg-brand" style={{ width: row.width }} />
                      </div>
                      <span className="w-[106px] whitespace-nowrap text-right">
                        {canViewAmountData ? <span className="block font-black text-ink">{wonEok(row.amount)}</span> : <span className="block font-black text-ink">{row.width}</span>}
                        {canViewAmountData && krwEokFromEur(row.amount, averageEurKrwRate) ? (
                          <span className="mt-[2px] block text-[11px] font-black text-muted2">{krwEokFromEur(row.amount, averageEurKrwRate)}</span>
                        ) : null}
                      </span>
                    </div>
                  </td>
                  <td className={cn("border-b border-rowline px-[16px] py-[13px] text-right font-black", ingredientYoyClass(row.yoy))}>
                    {row.yoy}
                  </td>
                  <td className={cn("border-b border-rowline px-[16px] py-[13px] text-right font-black", ingredientYoyClass(row.mom))}>
                    <span className="whitespace-nowrap" title={row.mom !== "-" ? `${row.mom} (${momLabel})` : row.mom}>{row.mom}</span>
                  </td>
                  <td className="border-b border-rowline px-[12px] py-[13px] font-semibold text-ink3">
                    <span className="block whitespace-nowrap" title={row.country}>{row.country}</span>
                  </td>
                  <td className="border-b border-rowline px-[12px] py-[13px] font-semibold text-ink3">
                    <span className="block truncate" title={row.brand}>{row.brand}</span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-[16px] py-[36px] text-center text-[13px] font-bold text-muted2">
                    성분 분석 데이터가 없습니다. 데이터 입력에서 분석 시작을 먼저 실행해 주세요.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          {ingredientPageCount > 1 ? (
            <div className="flex items-center justify-between border-t border-divider px-[18px] py-[12px]">
              <button
                type="button"
                onClick={() => setIngredientPage((page) => Math.max(1, page - 1))}
                disabled={safeIngredientPage <= 1}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-[12px] font-black text-muted2">
                {formatNumber(safeIngredientPage)} / {formatNumber(ingredientPageCount)}
              </span>
              <button
                type="button"
                onClick={() => setIngredientPage((page) => Math.min(ingredientPageCount, page + 1))}
                disabled={safeIngredientPage >= ingredientPageCount}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                다음
              </button>
            </div>
          ) : null}
        </section>

        <div className="grid content-start gap-[14px]">
          <section className="rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <div className="mb-[14px] flex items-center justify-between">
              <h3 className="text-[14px] font-black text-ink">
                성분 × 국가 <span className="font-semibold text-muted2">· 미리보기</span>
              </h3>
            </div>
            {rows.slice(0, 3).map((row) => (
              <div key={row.ingredient} className="flex items-center justify-between border-b border-rowline py-[10px] last:border-b-0">
                <p className="text-[13px] font-black text-ink">{row.ingredient}</p>
                <p className="text-[12px] font-black text-brand">{row.country}</p>
              </div>
            ))}
          </section>

          <section className="rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <div className="mb-[14px] flex items-center justify-between">
              <h3 className="text-[14px] font-black text-ink">
                성분 × 브랜드 <span className="font-semibold text-muted2">· 미리보기</span>
              </h3>
            </div>
            {rows.slice(0, 3).map((row) => (
              <div key={row.ingredient} className="flex items-center justify-between border-b border-rowline py-[10px] last:border-b-0">
                <p className="text-[13px] font-black text-ink">{row.ingredient}</p>
                <p className="text-[12px] font-black text-brand">{row.brand}</p>
              </div>
            ))}
          </section>

        </div>
      </div>
      <p className="mt-[16px] text-[12px] font-semibold italic text-muted2">
        핵심: 성분은 국가·브랜드·SKU를 가로지르는 또 하나의 축 → “어느 성분이 어느 시장에서 뜨는가”를 브랜드 미팅·신제품 기획 인사이트로 활용
      </p>
    </>
  );
}
