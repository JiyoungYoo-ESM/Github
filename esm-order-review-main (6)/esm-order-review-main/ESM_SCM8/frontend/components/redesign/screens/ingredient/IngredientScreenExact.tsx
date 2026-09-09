"use client";

import { useState } from "react";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { IngredientMappingScreen } from "./IngredientMappingScreen";
import { IngredientRankScreen } from "./IngredientRankScreen";
import { IngredientTabButton } from "./IngredientScreenParts";
import { useIngredientScreenData } from "./useIngredientScreenData";

type IngredientView = "rank" | "mapping";

export function IngredientScreenExact() {
  const [view, setView] = useState<IngredientView>("rank");
  const { ingredient, monthCoverage, comparisonBasis, analysisOptions, loading } = useIngredientScreenData();

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px] flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-[8px]">
            <h2 className="text-[18px] font-black leading-none text-ink">성분 기준 분석</h2>
            <span className="rounded-full bg-row px-[9px] py-[3px] text-[11px] font-black text-muted2">신규</span>
          </div>
          <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
            “어떤 성분이 뜨고 있나? 어느 국가·브랜드에서 강한가?” — 흩어진 성분 표기를 통합해 성분 단위로 순위·성장·교차를 봅니다.
          </p>
          <div className="mt-[12px]">
            <AnalysisPeriodBadge options={analysisOptions} />
            <AnalysisPeriodCaveat options={analysisOptions} />
          </div>
        </div>
      </div>
      <div className="mb-[16px] flex flex-wrap gap-[10px]">
        <IngredientTabButton label="성분 순위 · 성장" active={view === "rank"} onClick={() => setView("rank")} />
        <IngredientTabButton label="성분 매칭" active={view === "mapping"} onClick={() => setView("mapping")} />
      </div>
      {loading ? (
        <section className="rounded-[14px] border border-border bg-surface px-[20px] py-[36px] text-center text-[13px] font-bold text-muted2 shadow-soft">
          성분 분석 데이터를 불러오는 중입니다.
        </section>
      ) : view === "rank" ? (
        <IngredientRankScreen ingredient={ingredient} monthCoverage={monthCoverage} comparisonBasis={comparisonBasis} analysisOptions={analysisOptions} />
      ) : (
        <IngredientMappingScreen ingredient={ingredient} />
      )}
    </div>
  );
}
