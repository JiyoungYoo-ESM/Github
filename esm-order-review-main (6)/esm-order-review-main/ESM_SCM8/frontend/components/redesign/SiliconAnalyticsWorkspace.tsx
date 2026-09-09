"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { CellFormulaValue, CellValue, Worksheet } from "exceljs";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowLeftRight,
  BarChart3,
  Box,
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardList,
  Database,
  FileText,
  FlaskConical,
  Globe2,
  Grid3X3,
  ListChecks,
  Lock,
  LucideIcon,
  Menu,
  PackageCheck,
  Search,
  Star,
  Tag,
  Upload,
  X,
  Download
} from "lucide-react";
import {
  analyzeFromCms,
  clearLastAnalysisResult,
  downloadHref,
  getCategoryCorrectionOptions,
  getExchangeRate,
  getLastAnalysisResult,
  isAbortError,
  exportReportFromTemplate,
  getSeasonTrendAnalysis,
  getStockGapItems,
  saveCategoryCorrections,
  type ReportAudience,
  type ReportExportFormat
} from "@/lib/api";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { EntityIntegrationNotice } from "@/components/auth/EntityIntegrationNotice";
import { DiagnosticsScreenExact } from "./screens/diag/DiagnosticsScreenExact";
import { GapScreenExact, stockGapShortageQty } from "./screens/gap/GapScreenExact";
import type { StockGapComputed } from "./screens/gap/GapScreenExact";
import { OrderScreenExact } from "./screens/order/OrderScreenExact";
import {
  NewOrderLogicScreenExact,
  useNewOrderLogicScreenModel
} from "./screens/order-v2";
import { OrderV3Screen } from "./screens/order-v3";
import { SeasonFactorManagementScreen } from "./screens/season-factor/SeasonFactorManagementScreen";
import { InsightInputScreenExact } from "./screens/idata/InsightInputScreenExact";
import { SeasonCalendarScreenExact } from "./screens/season/SeasonCalendarScreenExact";
import { SkuScreenExact } from "./screens/sku/SkuScreenExact";
import { CategoryScreenExact } from "./screens/category/CategoryScreenExact";
import { IngredientScreenExact } from "./screens/ingredient/IngredientScreenExact";
import { CrossAnalysisScreenExact } from "./screens/cross/CrossAnalysisScreenExact";
import { CustomerSupportScreen } from "./screens/support/CustomerSupportScreen";
import { CorporateInventoryScreen } from "./screens/corporate-inventory/CorporateInventoryScreen";
import { CountryScreenExact } from "./screens/country/CountryScreenExact";
import { BrandScreenExact } from "./screens/brand/BrandScreenExact";
import { ReportBuilder } from "./screens/report/ReportBuilder";
import { PrepScreenExact } from "./screens/prep/PrepScreenExact";
import { growthPercentValue } from "./lib/growth-display";
import { validCrossLabel } from "./lib/cross-label";
import { escapeReportHtml } from "./lib/report-html";
import { AnalysisStartRequiredState, InsightAnalysisRequiredState } from "./shared/AnalysisRequiredState";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "./shared/AnalysisPeriod";
import { BrandSearchSelect } from "./shared/BrandSearchSelect";
import { BrandBar, SkuNameWithCode } from "./shared/BrandBar";
import { ingredientCoverageStats, ingredientCrossScopeNote, uniqueValueCount } from "./shared/ingredient-analysis";
import { OrderMetricCard } from "./shared/OrderMetricCard";
import { StatusPill } from "./shared/StatusPill";
import { OrderSubTabs } from "./shared/OrderSubTabs";
import { exchangeRateBasisLabel, exchangeRateText, krwEokFromEur, setCurrentKrwExchangeRate, wonEok } from "./lib/currency-format";
import {
  buildCalendarMonthAverageProfile,
  buildTopSkuConcentration,
  completeSeasonalityMonthKeys
} from "@/lib/brand-analysis";
import { displayBrandName } from "@/lib/brand-display";
import { trendLineColors } from "@/lib/chart-tokens";
import {
  analysisMonthKeys,
  formatAnalysisMonthLabel,
  nearestAvailableMonth,
  type CrossMomStatus
} from "@/lib/cross-analysis-mom";
import {
  crossMatrixData,
  sourceRowsForCrossAxis,
  type CrossAxis,
  type CrossMetric,
  type CrossMomPeriod,
  type CrossScale
} from "@/lib/cross-analysis-matrix";
import { allocateCrossMatrixShares } from "@/lib/cross-analysis-share";
import {
  completeSeasonMonthKeys,
} from "@/lib/season-calendar";
import {
  amountOf,
  brandOf,
  buildCountrySummary,
  category1Of,
  category2Of,
  countryOf,
  ingredientOf,
  monthKeyOf,
  numberValue,
  productNameOf,
  qtyOf,
  skuCodeOf
} from "@/lib/global-demand-view-model";
import { getCountryRegion, needsRegionReview } from "@/lib/region-groups";
import {
  calculateStockGapShortageQty,
  computeStockGapItem,
  formatDate as formatStockGapDate,
  stockGapStatusOrder
} from "@/lib/stock-gap";
import { cn, formatNumber } from "@/lib/utils";
import type {
  AnalyzeResponse,
  CategoryCorrectionItem,
  CategoryCorrectionOptions,
  IngredientAnalysis,
  MonthCoverage,
  SeasonAnalysis
} from "@/types/api";
import type {
  ComparisonBasis,
  GlobalSearchResult,
  GlobalSearchTarget,
  Metric,
  Mode,
  NavItem,
  ReportBlockKind,
  ReportBlockSection,
  ReportBlockSize,
  ReportBlockSnapshot,
  Screen,
  SharedAnalysisRuntime,
  TableRow
} from "./lib/types";
import { REPORT_CARD_SNAPSHOT_ATTR } from "./lib/report-card-snapshot";
import {
  addMonthsForDate,
  DEMAND_DATA_MIN_DATE,
  demandRange,
  demandYearRange,
  MAX_DEMAND_DIRECT_RANGE_MONTHS,
  MAX_REPORT_EXPORT_ID_LENGTH,
  normalizedBrandIdentity,
  reportAnalysisPeriodParams,
  reportBrandRole,
  stableShortHash,
  todayKst,
  useLoadingDots,
  compactReportExportId,
  analysisPeriodLabel,
  analysisPeriodSentenceLabel,
  analysisPeriodCompactLabel,
  analysisRangeMonthCount,
  longKoreanDateLabel
} from "./lib/workspace-format";
import {
  allNavItems,
  deferredInsightNav,
  deepInsightNav,
  insightNav,
  insightRequiredCopy,
  metrics,
  modeOf,
  overviewNav,
  orderNav,
  ORDER_SCREENS,
  INSIGHT_RESULT_SCREENS,
  qualityNav,
  supportNav,
  v3SettingsNav,
  rows,
  titles
} from "./lib/nav-config";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";
import {
  canAccessOrderAnalysis,
  isOrderAnalysisBlockedForEntity,
  isOrderAnalysisScreen
} from "@/lib/order-access";
import {
  canAccessCorporateInventory,
  canAccessCorporateInventoryForEntity,
  isCorporateInventoryScreen
} from "@/lib/corporate-inventory-access";
import { pathForWorkspaceScreen, workspaceScreenFromPathname } from "./lib/workspace-routes";
import { searchGlobalSearchIndex } from "./lib/global-search";
import { useWorkspaceExchangeRate } from "./workspace/useWorkspaceExchangeRate";
import { useWorkspaceAnalysisSession } from "./workspace/useWorkspaceAnalysisSession";
import { useWorkspaceFavorites } from "./workspace/useWorkspaceFavorites";
import { useWorkspaceGlobalSearch } from "./workspace/useWorkspaceGlobalSearch";
import { useWorkspaceReportBlocks } from "./workspace/useWorkspaceReportBlocks";
import {
  CorporationSelector,
  DataTable,
  InsightNavSection,
  MetricCard,
  NavSection,
  Stepper
} from "./lib/WorkspaceUi";
import {
  availableComparisonBasis,
  automaticComparisonBasis,
  automaticGrowthTargetMonths,
  comparableYearWindow,
  comparisonBasisFromValue,
  comparisonPeriodLabel,
  compactYoyPeriodLabel,
  GROWTH_DISPLAY_CAP,
  growthBadgeClass,
  growthDisplayLabel,
  growthLabelsForMonthPair,
  isAdjacentMonthPair,
  isGrowthStatusLabel,
  latestComparableMonths,
  latestComparableYears,
  missingMonthRangeLabel,
  monthsBetweenInclusive,
  pickComparableYearWindow,
  previousMonthKey,
  previousYearMonthKey,
  shortMonthKeyLabel,
  shortMonthPairLabel,
  yoyBucketOf,
  yoyWindowRangeLabel
} from "./lib/yoy-comparison";

type Props = {
  initialScreen?: Screen;
};

// Search processing and reusable workspace controls live in focused modules.

function SeasonHeatmap() {
  const heatRows = [
    ["선케어", 2, 3, 5, 8, 10, 9, 7, 5, 3, 2, 2, 2],
    ["진정 토너", 5, 6, 7, 8, 9, 8, 7, 6, 5, 5, 6, 6],
    ["립틴트", 4, 4, 5, 5, 6, 6, 7, 8, 8, 9, 10, 9],
    ["앰플", 8, 8, 9, 7, 6, 5, 4, 4, 5, 6, 7, 8]
  ];
  return (
    <div className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
      <div className="flex items-center justify-between border-b border-divider px-5 py-4">
        <h3 className="text-[15px] font-black">카테고리별 월간 수요 계수</h3>
        <span className="text-[11.5px] font-bold text-muted">낮음 → 높음</span>
      </div>
      <div className="grid grid-cols-[140px_1fr] border-b border-divider bg-surface-soft px-4 py-3 text-[11.5px] font-black text-muted">
        <span>카테고리</span>
        <div className="grid grid-cols-12 gap-2 text-center">
          {Array.from({ length: 12 }, (_, index) => (
            <span key={index}>{index + 1}</span>
          ))}
        </div>
      </div>
      {heatRows.map(([label, ...values]) => (
        <div key={label} className="grid grid-cols-[140px_1fr] items-center border-b border-rowline px-4 py-3 last:border-b-0">
          <span className="text-[13px] font-black">{label}</span>
          <div className="grid grid-cols-12 gap-2">
            {values.map((value, index) => (
              <div
                key={`${label}-${index}`}
                className="h-8 rounded-[7px]"
                style={{ backgroundColor: `rgba(230, 0, 45, ${0.08 + Number(value) / 14})` }}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CrossMatrix() {
  const { canViewAmountData } = useUserPermissions();
  const labels = ["아누아", "조선미녀", "메디큐브", "토리든", "롬앤"];
  const countries = ["미국", "프랑스", "UAE", "일본"];
  return (
    <div className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-divider px-5 py-4">
        <h3 className="text-[15px] font-black">국가 × 브랜드 매출 매트릭스</h3>
        <div className="flex rounded-[10px] bg-page p-1">
          {(canViewAmountData ? ["매출액", "판매량", "YoY"] : ["판매량", "YoY"]).map((item, index) => (
            <button
              key={item}
              type="button"
              className={cn(
                "h-8 rounded-[8px] px-4 text-[12px] font-black",
                index === 0 ? "bg-surface text-ink shadow-sm" : "text-muted"
              )}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-[120px_repeat(5,minmax(88px,1fr))] overflow-x-auto text-[12.5px]">
        <div className="bg-surface-soft p-3 font-black text-muted">국가 / 브랜드</div>
        {labels.map((label) => (
          <div key={label} className="bg-surface-soft p-3 text-center font-black text-muted">
            {label}
          </div>
        ))}
        {countries.map((country, rowIndex) => (
          <div key={country} className="contents">
            <div className="border-t border-divider p-3 font-black">{country}</div>
            {labels.map((label, colIndex) => {
              const value = 8 - Math.abs(rowIndex - colIndex) + rowIndex;
              return (
                <div
                  key={`${country}-${label}`}
                  className="border-t border-l border-divider p-3 text-center font-black"
                  style={{ backgroundColor: `rgba(230, 0, 45, ${0.05 + value / 20})` }}
                >
                  {canViewAmountData ? `€${value.toFixed(1)}K` : `${formatNumber(value * 10, 0)}%`}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function ExtraPanel({ screen }: { screen: Screen }) {
  if (screen === "season") return <SeasonHeatmap />;
  if (screen === "cross") return <CrossMatrix />;
  if (screen === "report") return <ReportBuilder />;
  return null;
}

function WorkspaceGlobalSearch({
  index,
  onNavigate
}: {
  index: GlobalSearchResult[];
  onNavigate: (screen: Screen) => void;
}) {
  const { canViewAmountData } = useUserPermissions();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const searchRef = useRef<HTMLDivElement | null>(null);
  const results = useMemo(() => searchGlobalSearchIndex(index, query), [index, query]);
  const showResults = focused && query.trim().length > 0;

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (!searchRef.current?.contains(event.target as Node)) setFocused(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  const selectResult = (item: GlobalSearchResult) => {
    onNavigate(item.screen);
    setQuery("");
    setFocused(false);
  };

  return (
    <div ref={searchRef} className="relative ml-auto w-full min-w-0 max-w-[360px] md:w-[300px] xl:w-[360px]">
      <label className="flex h-[38px] items-center gap-[10px] rounded-[10px] border border-border bg-surface px-[13px]">
        <Search className="h-4 w-4 text-muted2" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setFocused(true)}
          className="min-w-0 flex-1 border-none bg-transparent text-[13px] font-semibold outline-none placeholder:text-muted2"
          placeholder="국가 · 브랜드 · 상품명 · SKU 검색"
        />
      </label>
      {showResults ? (
        <div className="absolute right-0 top-[44px] z-40 w-full overflow-hidden rounded-[12px] border border-border bg-surface shadow-[0_18px_45px_rgba(15,23,42,0.18)]">
          {results.length > 0 ? (
            <div className="max-h-[390px] overflow-y-auto py-[6px]">
              {results.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => selectResult(item)}
                  className="flex w-full items-center gap-[11px] px-[12px] py-[10px] text-left transition hover:bg-row"
                >
                  <span
                    className={cn(
                      "grid h-[30px] w-[45px] shrink-0 place-items-center rounded-[8px] text-[11px] font-black",
                      item.target === "country"
                        ? "bg-blue-50 text-blue-700"
                        : item.target === "brand"
                          ? "bg-brand-50 text-brand"
                          : "bg-emerald-50 text-emerald-700"
                    )}
                  >
                    {item.target === "country" ? "국가" : item.target === "brand" ? "브랜드" : "SKU"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-black text-ink">{item.label}</span>
                    <span className="mt-[3px] block truncate text-[11px] font-semibold text-muted2">
                      {item.description} · {canViewAmountData && item.amount > 0 ? wonEok(item.amount) : `${formatNumber(item.qty)}개`}
                    </span>
                    <span className="mt-[6px] flex flex-wrap gap-[4px]">
                      {item.tabs.slice(0, 5).map((tab) => (
                        <span key={tab} className="rounded-full border border-border bg-surface-soft px-[7px] py-[2px] text-[10px] font-black text-muted2">
                          {tab}
                        </span>
                      ))}
                      {item.tabs.length > 5 ? (
                        <span className="rounded-full border border-border bg-surface-soft px-[7px] py-[2px] text-[10px] font-black text-muted2">
                          +{item.tabs.length - 5}
                        </span>
                      ) : null}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="px-[14px] py-[18px] text-center text-[12px] font-black text-muted2">
              검색 결과가 없습니다.
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

function MobileWorkspaceMenu({
  screen,
  onNavigate,
  favoriteItems,
  favoriteIds,
  onToggleFavorite,
  overviewNavItems,
  orderNavItems,
  v3SettingsNavItems
}: {
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  favoriteItems: NavItem[];
  favoriteIds: Screen[];
  onToggleFavorite: (screen: Screen) => void;
  overviewNavItems: NavItem[];
  orderNavItems: NavItem[];
  v3SettingsNavItems: NavItem[];
}) {
  const [open, setOpen] = useState(false);
  const navGroups: Array<{ label: string; items: NavItem[] }> = [
    { label: "경영 · OVERVIEW", items: overviewNavItems },
    { label: "발주 · QUANTITATIVE", items: orderNavItems },
    { label: "분석 · INSIGHT", items: insightNav },
    { label: "심화", items: deepInsightNav },
    { label: "데이터 점검 · QUALITY", items: qualityNav },
    { label: "관리자 · V3 설정", items: v3SettingsNavItems },
    { label: "지원 · SUPPORT", items: supportNav },
    { label: "준비 중", items: deferredInsightNav }
  ];

  const selectScreen = (nextScreen: Screen) => {
    onNavigate(nextScreen);
    setOpen(false);
  };

  return (
    <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-white/[.08] bg-sidebar px-4 text-row lg:hidden">
      <Link href="/" aria-label="Silicon2 홈으로 이동" className="inline-flex">
        <Image src="/assets/silicon2-logo-white.png" alt="SILICON2" width={104} height={20} className="h-5 w-auto" />
      </Link>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="메뉴 열기"
        aria-expanded={open}
        className="grid h-10 w-10 place-items-center rounded-[10px] text-row transition hover:bg-white/10"
      >
        <Menu className="h-5 w-5" />
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex bg-black/55" role="dialog" aria-modal="true" aria-label="모바일 메뉴">
          <button type="button" aria-label="메뉴 닫기" className="flex-1" onClick={() => setOpen(false)} />
          <aside className="flex h-full w-[min(86vw,340px)] flex-col bg-sidebar text-row shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-white/[.08] px-4">
              <Image src="/assets/silicon2-logo-white.png" alt="SILICON2" width={104} height={20} className="h-5 w-auto" />
              <button type="button" aria-label="메뉴 닫기" onClick={() => setOpen(false)} className="grid h-10 w-10 place-items-center rounded-[10px] text-muted2 hover:bg-white/10 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <CorporationSelector />
            <nav className="analytics-sidebar-scroll min-h-0 flex-1 overflow-y-auto px-3 py-4" aria-label="모바일 주 메뉴">
              {favoriteItems.length > 0 ? (
                <div className="mb-4 border-b border-white/[.08] pb-4">
                  <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[.12em] text-muted2">자주 쓰는 탭</p>
                  {favoriteItems.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === screen;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectScreen(item.id)}
                        className={cn(
                          "mb-1 flex min-h-11 w-full items-center gap-3 rounded-[10px] px-3 text-left text-[14px] font-bold transition",
                          active ? "bg-brand text-white" : "text-muted2 hover:bg-white/[.07] hover:text-row"
                        )}
                      >
                        <Icon className="h-[18px] w-[18px] shrink-0" />
                        <span className="truncate">{item.label}</span>
                        <Star className="ml-auto h-4 w-4 shrink-0 fill-current" />
                      </button>
                    );
                  })}
                </div>
              ) : null}
              {navGroups.filter((group) => group.items.length > 0).map((group) => (
                <div key={group.label} className="mb-4 last:mb-0">
                  <p className="px-3 pb-2 text-[10px] font-black uppercase tracking-[.12em] text-muted2">{group.label}</p>
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active = item.id === screen;
                    const favorite = favoriteIds.includes(item.id);
                    const disabled = Boolean(item.disabled);
                    return (
                      <div
                        key={item.id}
                        className={cn(
                          "mb-1 flex min-h-11 items-center rounded-[10px] transition",
                          disabled
                            ? "cursor-not-allowed text-muted opacity-60"
                            : active
                              ? "bg-brand text-white"
                              : "text-muted2 hover:bg-white/[.07] hover:text-row"
                        )}
                      >
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => selectScreen(item.id)}
                          aria-label={disabled ? `${item.label} ${item.statusLabel ?? "준비 중"}` : undefined}
                          className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2 text-left text-[14px] font-bold disabled:cursor-not-allowed disabled:text-muted"
                        >
                          <Icon className="h-[18px] w-[18px] shrink-0" />
                          <span className="min-w-0 whitespace-normal break-keep leading-[1.15]">{item.label}</span>
                          {item.statusLabel ? (
                            <span className="ml-auto shrink-0 self-start rounded-full border border-white/[.12] px-2 py-1 text-[9px] font-black text-current">
                              {item.statusLabel}
                            </span>
                          ) : null}
                        </button>
                        {!disabled && !item.statusLabel ? (
                          <button
                            type="button"
                            onClick={() => onToggleFavorite(item.id)}
                            aria-label={favorite ? `${item.label} 즐겨찾기 해제` : `${item.label} 즐겨찾기 추가`}
                            className="mr-1 grid h-10 w-10 shrink-0 place-items-center rounded-[9px] transition hover:bg-white/10"
                          >
                            <Star className={cn("h-4 w-4", favorite && "fill-current")} />
                          </button>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ))}
            </nav>
            <WorkspaceAccountActions className="p-4" />
          </aside>
        </div>
      ) : null}
    </div>
  );
}

// Report drawer and preview are isolated from workspace orchestration.

function WorkspaceAccountActions({ className }: { className?: string }) {
  const { user } = useAuthSession();
  const accountName = user?.display_name || user?.username || "로그인 계정";
  const showUsername = Boolean(user?.username && user.username !== accountName);

  return (
    <div className={cn("border-t border-white/[.08]", className)}>
      <div className="flex min-w-0 items-center gap-2.5 rounded-[8px] border border-white/[.12] bg-white/[.06] p-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-black/40 text-[12px] font-black text-white ring-1 ring-white/[.12]">
          {accountName.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[12px] font-black text-white">{accountName}</span>
          {showUsername ? (
            <span className="mt-0.5 block truncate text-[10px] font-semibold text-muted">
              {user?.username}
            </span>
          ) : (
            <span className="mt-0.5 block text-[10px] font-semibold text-muted">로그인 계정</span>
          )}
        </span>
        <LogoutButton
          compact
          className="shrink-0 text-muted2 hover:bg-white/[.1] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
        />
      </div>
    </div>
  );
}

function NewOrderLogicWorkspaceContent() {
  const model = useNewOrderLogicScreenModel();
  const { canViewAmountData } = useUserPermissions();
  return (
    <NewOrderLogicScreenExact
      {...model}
      canViewAmountData
      canEditAdvancedSettings={canViewAmountData}
    />
  );
}

function NewOrderLogicWorkspaceScreen() {
  return <NewOrderLogicWorkspaceContent />;
}

export function SiliconAnalyticsWorkspace({ initialScreen = "prep" }: Props) {
  const pathname = usePathname();
  const { user, selectedEntity } = useAuthSession();
  const isAdmin = user?.is_admin === true;
  const orderAnalysisAllowed = canAccessOrderAnalysis(user);
  const corporateInventoryAllowed = canAccessCorporateInventory(user);
  const corporateInventoryAvailable = corporateInventoryAllowed && canAccessCorporateInventoryForEntity(selectedEntity);
  const screen = workspaceScreenFromPathname(pathname) ?? initialScreen;
  const mode: Mode = modeOf(screen);
  const {
    analysisDate,
    analysisReady,
    analysisSettings,
    completeOrderAnalysis,
    currentAnalysisResult,
    insightAnalysisReady,
    invalidateInsightAnalysis,
    markInsightAnalysisReady,
    updateAnalysisSettings
  } = useWorkspaceAnalysisSession();
  const {
    exchangeRate,
    setExchangeRate,
    exchangeRateInput,
    setExchangeRateInput,
    exchangeRateError,
    setExchangeRateError,
    refreshingExchangeRate,
    setRefreshingExchangeRate,
    currencyCode
  } = useWorkspaceExchangeRate(false);
  const { index: globalSearchIndex, refresh: refreshGlobalSearch, clear: clearGlobalSearch } =
    useWorkspaceGlobalSearch(markInsightAnalysisReady, orderAnalysisAllowed);
  const {
    blocks: reportBlocks,
    syncBlock: syncReportBlock,
    toggleBlock: toggleReportBlock
  } = useWorkspaceReportBlocks();
  const availableNavItems = useMemo(
    () => {
      const items = orderAnalysisAllowed
        ? allNavItems
        : allNavItems.filter((item) => !isOrderAnalysisScreen(item.id));
      return items.filter((item) => (
        (isAdmin || item.id !== "season-factor") &&
        (corporateInventoryAvailable || !isCorporateInventoryScreen(item.id)) &&
        !isOrderAnalysisBlockedForEntity(selectedEntity, item.id)
      ));
    },
    [corporateInventoryAvailable, isAdmin, orderAnalysisAllowed, selectedEntity]
  );
  const visibleOrderNav = useMemo(
    () => {
      if (!orderAnalysisAllowed) {
        return orderNav.map((item) => ({ ...item, disabled: true, statusLabel: "권한 없음" }));
      }
      return orderNav.map((item) => (
        isOrderAnalysisBlockedForEntity(selectedEntity, item.id)
          ? { ...item, disabled: true, statusLabel: "비활성화" }
          : item
      ));
    },
    [orderAnalysisAllowed, selectedEntity]
  );
  const visibleV3SettingsNav = isAdmin ? v3SettingsNav : [];
  const { favoriteNavIds, favoriteNavItems, toggleFavoriteNav } =
    useWorkspaceFavorites(availableNavItems);
  const current = titles[screen];
  const currentRows = rows[screen];
  const showStepper = mode === "order" && screen !== "order-v2" && screen !== "order-v3" && screen !== "season-factor";
  const showWorkspaceHeader = screen !== "order-v3";
  const insightRequired = !insightAnalysisReady && INSIGHT_RESULT_SCREENS.includes(screen);
  const diagnosticsRequired = !insightAnalysisReady && screen === "diag";
  const insightRequiredState = insightRequiredCopy[screen];

  useEffect(() => {
    setCurrentKrwExchangeRate(exchangeRate
      ? {
          currencyCode: exchangeRate.currency_code,
          value: exchangeRate.currency_krw_rate,
          date: exchangeRate.rate_date,
          source: exchangeRate.rate_source
        }
      : null);
  }, [exchangeRate]);

  const activeMetrics = useMemo(() => metrics[screen], [screen]);
  const navigate = useCallback((next: Screen) => {
    if (
      (!orderAnalysisAllowed && isOrderAnalysisScreen(next)) ||
      (!corporateInventoryAvailable && isCorporateInventoryScreen(next)) ||
      isOrderAnalysisBlockedForEntity(selectedEntity, next)
    ) return;
    const availableScreen = next === "ingredient" && !INGREDIENT_ANALYSIS_ENABLED ? "idata" : next;
    const nextPath = pathForWorkspaceScreen(availableScreen);
    if (nextPath === pathname) return;
    window.history.pushState(null, "", nextPath);
  }, [corporateInventoryAvailable, orderAnalysisAllowed, pathname, selectedEntity]);

  const handleAnalysisComplete = (result: AnalyzeResponse) => {
    completeOrderAnalysis(result);
    refreshGlobalSearch();
  };

  const refreshExchangeRate = useCallback(async () => {
    setRefreshingExchangeRate(true);
    setExchangeRateError("");
    setCurrentKrwExchangeRate(null);
    setExchangeRate(null);
    try {
      const rate = await getExchangeRate(currencyCode);
      setCurrentKrwExchangeRate({
        currencyCode: rate.currency_code,
        value: rate.currency_krw_rate,
        date: rate.rate_date,
        source: rate.rate_source
      });
      setExchangeRate(rate);
      setExchangeRateInput(String(rate.currency_krw_rate));
    } catch (error) {
      // 법인 전환·로그아웃에서 우리가 끊은 요청은 실패가 아니다. 로그도 남기지 않고
      // "환율 조회 실패"도 띄우지 않는다.
      if (isAbortError(error)) {
        return;
      }
      console.warn("환율 조회 실패:", error instanceof Error ? error.message : error);
      setExchangeRateError("환율 조회 실패");
    } finally {
      setRefreshingExchangeRate(false);
    }
  }, [currencyCode, setExchangeRate, setExchangeRateInput, setExchangeRateError, setRefreshingExchangeRate]);

  // 워크스페이스 최초 마운트 시 1회만 조회한다. 데이터 준비 화면을 다시 열어도(=screen
  // state만 바뀜, 루트는 재마운트 안 됨) 재조회하지 않는다 — 재조회는 사용자가 버튼을
  // 눌렀을 때만. 분석 시작 시에도 여기서 암묵적으로 다시 조회하지 않고, 화면에 표시된
  // 값을 그대로 스냅샷해서 보낸다(PrepScreenExact.startAnalysis 참고).
  useEffect(() => {
    void refreshExchangeRate();
  }, [refreshExchangeRate]);

  const handleInsightAnalysisComplete = () => {
    markInsightAnalysisReady();
    refreshGlobalSearch();
  };

  const handleInsightAnalysisInvalidated = () => {
    invalidateInsightAnalysis();
    clearGlobalSearch();
    refreshGlobalSearch();
  };

  return (
    <main className="silicon-analytics-shell flex min-h-screen bg-page text-ink">
      <aside className="analytics-sidebar sticky top-0 hidden h-screen w-[252px] shrink-0 flex-col bg-sidebar text-row lg:flex">
        <div className="flex h-16 items-center border-b border-white/[.08] px-[22px]">
          <Link href="/" aria-label="랜딩페이지로 이동" className="inline-flex">
            <Image
              src="/assets/silicon2-logo-white.png"
              alt="SILICON2"
              width={120}
              height={22}
              style={{ height: 22, width: "auto" }}
            />
          </Link>
        </div>
        <CorporationSelector />
        <div className="analytics-sidebar-scroll flex-1 overflow-y-auto px-[14px] pb-6 pt-[18px]">
          <NavSection
            label="자주 쓰는 탭"
            items={favoriteNavItems}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="경영 · OVERVIEW"
            items={corporateInventoryAvailable ? overviewNav : []}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="발주 · QUANTITATIVE"
            items={visibleOrderNav}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <InsightNavSection
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="데이터 점검 · QUALITY"
            items={qualityNav}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="관리자 · V3 설정"
            items={visibleV3SettingsNav}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="지원 · SUPPORT"
            items={supportNav}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
          <NavSection
            label="준비 중"
            items={deferredInsightNav}
            screen={screen}
            onNavigate={navigate}
            favoriteIds={favoriteNavIds}
            onToggleFavorite={toggleFavoriteNav}
          />
        </div>
        <WorkspaceAccountActions className="px-[18px] py-[14px]" />
      </aside>

      <section className="min-w-0 flex-1">
        <MobileWorkspaceMenu
          screen={screen}
          onNavigate={navigate}
          favoriteItems={favoriteNavItems}
          favoriteIds={favoriteNavIds}
          onToggleFavorite={toggleFavoriteNav}
          overviewNavItems={corporateInventoryAvailable ? overviewNav : []}
          orderNavItems={visibleOrderNav}
          v3SettingsNavItems={visibleV3SettingsNav}
        />
        {screen === "overview" ? null : <div className="px-4 pt-3 lg:px-[25px] lg:pt-4"><EntityIntegrationNotice /></div>}
        {showWorkspaceHeader && screen !== "support" ? <header className="z-20 border-b border-border bg-surface lg:sticky lg:top-0">
          <div className="analytics-topbar flex min-h-[64px] flex-wrap items-center gap-3 px-4 py-3 lg:gap-4 lg:px-[25px]">
            <div className="min-w-[116px] shrink-0">
              <p className="text-[11px] font-black leading-none text-brand">{current.crumb}</p>
              <h1 className="mt-[6px] text-[19px] font-black leading-none tracking-normal text-ink">
                {current.title}
              </h1>
            </div>
            <WorkspaceGlobalSearch index={globalSearchIndex} onNavigate={navigate} />
          </div>
          {showStepper ? <Stepper screen={screen} analysisReady={analysisReady} onNavigate={navigate} /> : null}
        </header> : null}

        {screen === "overview" ? (
          <CorporateInventoryScreen />
        ) : screen === "support" ? (
          <CustomerSupportScreen />
        ) : screen === "prep" ? (
          <PrepScreenExact
            onAnalysisComplete={handleAnalysisComplete}
            onNavigate={navigate}
            analysisSettings={analysisSettings}
            onAnalysisSettingsChange={updateAnalysisSettings}
            analysisDate={analysisDate}
          />
        ) : diagnosticsRequired ? (
          <InsightAnalysisRequiredState
            title="데이터 진단을 먼저 실행해 주세요"
            description="아직 이번 세션에서 분석 시작을 실행하지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 분류 필요 SKU, 성분 매칭, 권역 확인 결과가 이 화면에 표시됩니다."
            onNavigate={navigate}
          />
        ) : screen === "diag" ? (
          <DiagnosticsScreenExact />
        ) : screen === "order" ? (
          <OrderScreenExact analysisReady={analysisReady} currentAnalysisResult={currentAnalysisResult} onNavigate={navigate} />
        ) : screen === "order-v2" ? (
          <NewOrderLogicWorkspaceScreen />
        ) : screen === "order-v3" ? (
          <OrderV3Screen />
        ) : screen === "season-factor" ? (
          <SeasonFactorManagementScreen />
        ) : screen === "gap" ? (
          <GapScreenExact analysisReady={analysisReady} onNavigate={navigate} />
        ) : screen === "idata" ? (
          <InsightInputScreenExact
            onAnalysisComplete={handleInsightAnalysisComplete}
            onAnalysisInvalidated={handleInsightAnalysisInvalidated}
            onNavigate={navigate}
          />
        ) : insightRequired && insightRequiredState ? (
          <InsightAnalysisRequiredState title={insightRequiredState.title} description={insightRequiredState.description} onNavigate={navigate} />
        ) : screen === "country" ? (
          <CountryScreenExact
            reportBlocks={reportBlocks}
            onToggleReportBlock={toggleReportBlock}
            onSyncReportBlock={syncReportBlock}
            onNavigate={navigate}
          />
        ) : screen === "brand" ? (
          <BrandScreenExact reportBlocks={reportBlocks} onToggleReportBlock={toggleReportBlock} />
        ) : screen === "sku" ? (
          <SkuScreenExact reportBlocks={reportBlocks} onToggleReportBlock={toggleReportBlock} onNavigate={navigate} />
        ) : screen === "category" ? (
          <CategoryScreenExact onNavigate={navigate} />
        ) : screen === "season" ? (
          <SeasonCalendarScreenExact reportBlocks={reportBlocks} />
        ) : screen === "ingredient" ? (
          <IngredientScreenExact />
        ) : screen === "cross" ? (
          <CrossAnalysisScreenExact reportBlocks={reportBlocks} />
        ) : screen === "report" ? (
          <ReportBuilder />
        ) : (
        <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-[25px]">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-[780px]">
              <h2 className="text-[17px] font-black leading-none">{current.title}</h2>
              <p className="mt-[10px] text-[13px] font-semibold leading-6 text-muted">
                {current.description}
              </p>
            </div>
          </div>

          <div className="mb-4 grid gap-[14px] md:grid-cols-2 xl:grid-cols-4">
            {activeMetrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>

          <div className="mb-4">
            <ExtraPanel screen={screen} />
          </div>

          <DataTable headers={currentRows.headers} rows={currentRows.rows} />
        </div>
        )}
      </section>
    </main>
  );
}
