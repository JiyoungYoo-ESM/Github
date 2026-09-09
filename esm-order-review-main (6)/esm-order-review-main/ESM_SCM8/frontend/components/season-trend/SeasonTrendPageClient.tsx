"use client";

import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingState } from "@/components/common/LoadingState";
import { getSeasonTrendAnalysis } from "@/lib/api";
import type { SeasonAnalysis, SeasonTrendAnalyzeResponse } from "@/types/api";
import { GlobalDemandTab } from "./GlobalDemandTab";
import { MappingCheckTab } from "./MappingCheckTab";
import { SeasonTrendUploadPanel } from "./SeasonTrendUploadPanel";

type SeasonTrendData = Awaited<ReturnType<typeof getSeasonTrendAnalysis>>;

export type SeasonTrendSection = "global" | "mapping";

const excludedCategory1Values = new Set(["악세사리", "화장품 진열 집기"]);

const emptySeasonAnalysis = {
  category1Monthly: [],
  category2Monthly: [],
  category1Share: [],
  category2Share: [],
  ytdComparison: [],
  topSku: [],
  skuMonthly: [],
  mappingQuality: [],
  uncategorizedSku: [],
  countryCategoryMonthly: [],
  countryCategory2Monthly: [],
  countryTopSku: [],
  countrySkuSummary: [],
  countrySkuMonthly: [],
  countryCustomerSummary: [],
  countryCategoryCustomerSummary: [],
  customerSalesSummary: []
};

const emptyIngredientAnalysis = {
  keywordMap: [],
  skuTags: [],
  monthlyTrend: [],
  summary: [],
  growth3m: [],
  ytdComparison: [],
  topSku: [],
  topBrand: [],
  unmatchedSku: [],
  coverage: [],
  countryCoverage: [],
  countryMonthlyTrend: [],
  countrySummary: [],
  countryGrowth3m: [],
  countryYtdComparison: [],
  countryTopSku: [],
  countryTopBrand: []
};

function category1Value(row: Record<string, unknown>) {
  const value = row["기능구분1"] ?? row["대분류"] ?? row["category1"] ?? row["class1"];
  return value === null || value === undefined ? "" : String(value).trim();
}

function withoutExcludedCategory1<T extends Record<string, unknown>>(rows: T[] | undefined) {
  return (rows ?? []).filter((row) => !excludedCategory1Values.has(category1Value(row)));
}

function filterSeasonAnalysis(season: SeasonAnalysis) {
  return {
    ...season,
    category1Monthly: withoutExcludedCategory1(season.category1Monthly),
    category2Monthly: withoutExcludedCategory1(season.category2Monthly),
    category1Share: withoutExcludedCategory1(season.category1Share),
    category2Share: withoutExcludedCategory1(season.category2Share),
    ytdComparison: withoutExcludedCategory1(season.ytdComparison),
    topSku: withoutExcludedCategory1(season.topSku),
    skuMonthly: withoutExcludedCategory1(season.skuMonthly),
    uncategorizedSku: withoutExcludedCategory1(season.uncategorizedSku),
    countryCategoryMonthly: withoutExcludedCategory1(season.countryCategoryMonthly),
    countryCategory2Monthly: withoutExcludedCategory1(season.countryCategory2Monthly),
    countryTopSku: withoutExcludedCategory1(season.countryTopSku),
    countrySkuSummary: withoutExcludedCategory1(season.countrySkuSummary),
    countrySkuMonthly: withoutExcludedCategory1(season.countrySkuMonthly),
    countryCategoryCustomerSummary: withoutExcludedCategory1(season.countryCategoryCustomerSummary)
  };
}

export function SeasonTrendPageClient({ section }: { section: SeasonTrendSection }) {
  const [data, setData] = useState<SeasonTrendData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getSeasonTrendAnalysis()
      .then((result) => {
        if (mounted) {
          setData(result);
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <LoadingState panel />;
  }

  const seasonAnalysis = filterSeasonAnalysis(data?.seasonAnalysis ?? emptySeasonAnalysis);
  const ingredientAnalysis = data?.ingredientAnalysis ?? emptyIngredientAnalysis;
  const uploadedFileRoles = data?.uploadedFileRoles ?? [];
  const uploadedFiles = data?.uploadedFiles ?? [];
  const analysisOptions = data?.analysisOptions;
  const hasSeasonTrendData = Boolean(data?.hasSeasonTrendData);
  const hasSalesHistory = uploadedFileRoles.includes("sales_history");
  const hasProdList = uploadedFileRoles.includes("prod_list");
  const sourceSummary = uploadedFiles
    .filter((file) => ["sales_history", "prod_list", "category_correction"].includes(file.role))
    .map((file) => `${file.role}: ${file.original_name}`)
    .join(" / ");
  const handleSeasonAnalyzed = (result: SeasonTrendAnalyzeResponse) => {
    setData({
      hasAnalysisResult: true,
      hasSeasonTrendData: Boolean(
        (result.season_analysis.category1Monthly?.length ?? 0) > 0 ||
          (result.season_analysis.countryCategoryMonthly?.length ?? 0) > 0 ||
          (result.season_analysis.category2Monthly?.length ?? 0) > 0 ||
          (result.season_analysis.countryCategory2Monthly?.length ?? 0) > 0 ||
          (result.ingredient_analysis.summary?.length ?? 0) > 0
      ),
      seasonAnalysis: result.season_analysis,
      ingredientAnalysis: result.ingredient_analysis,
      uploadedFileRoles: result.uploaded_files?.map((file) => file.role) ?? [],
      uploadedFiles: result.uploaded_files ?? [],
      analysisOptions: result.analysis_options
    });
  };

  return (
    <div className="space-y-6">
      {section === "global" ? (
        <>
          <SeasonTrendUploadPanel activeSection="global" defaultSettingsOpen onAnalyzed={handleSeasonAnalyzed} />
          {hasSeasonTrendData ? (
            <GlobalDemandTab season={seasonAnalysis} ingredient={ingredientAnalysis} analysisOptions={analysisOptions} />
          ) : (
            <EmptyState
              icon={Database}
              title="표시할 수요 분석 데이터가 없습니다"
              description="분석 기간을 선택한 뒤 분석 시작을 눌러 주세요. CMS API 조회와 분석이 끝나면 이 영역에 국가별 수요 분석이 표시됩니다."
            />
          )}
        </>
      ) : null}
      {section === "mapping" ? (
        <MappingCheckTab
          season={seasonAnalysis}
          ingredient={ingredientAnalysis}
          hasSalesHistory={hasSalesHistory}
          hasProdList={hasProdList}
        />
      ) : null}
    </div>
  );
}
