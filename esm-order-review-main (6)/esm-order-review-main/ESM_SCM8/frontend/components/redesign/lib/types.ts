import type { LucideIcon } from "lucide-react";
import type { ExchangeRateResponse } from "../../../types/api.ts";
import type { LeadTimeInputValues, LeadTimeMethod } from "../../../lib/lead-times.ts";

export type Screen =
  | "overview"
  | "prep"
  | "diag"
  | "order"
  | "order-v2"
  | "order-v3"
  | "season-factor"
  | "gap"
  | "season"
  | "final"
  | "idata"
  | "country"
  | "brand"
  | "sku"
  | "category"
  | "ingredient"
  | "cross"
  | "report"
  | "support";

export type Mode = "overview" | "order" | "insight" | "quality" | "support";
export type ComparisonBasis = "none" | "yoy" | "mom";

export type NavItem = {
  id: Screen;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
  statusLabel?: string;
};

export type SharedAnalysisSettings = {
  safetyMonths: string;
  leadTimeMethods: LeadTimeMethod[];
  leadTimeValues: LeadTimeInputValues;
  leadTimeLoading: boolean;
  leadTimeError: string;
};

export type SharedAnalysisSettingsPatch = {
  safetyMonths?: string;
  leadTimeValues?: LeadTimeInputValues;
};

// 사용자가 직접 입력하는 SharedAnalysisSettings와 달리, 이 값들은 자동으로 계산되거나
// 외부 API에서 조회된다(분석 기준일 = 오늘, 환율 = 수출입은행 API). 워크스페이스 루트가
// 소유하며 화면이 바뀌어도 재조회하지 않는다 — 데이터 준비 화면과 향후 다른 분석 화면이
// 항상 같은 값을 보게 하기 위함.
export type SharedAnalysisRuntime = {
  analysisDate: string;
  exchangeRate: ExchangeRateResponse | null;
};

export type Metric = {
  label: string;
  value: string;
  sub: string;
  tone?: "brand" | "green" | "muted" | "amber";
};

export type TableRow = Array<string | number>;

export type ReportBlockKind = "kpi" | "share" | "ranking" | "trend" | "matrix";
export type ReportBlockSection = "summary" | "region" | "brand" | "sku" | "cross" | "season" | "ingredient";
export type ReportBlockSize = "full" | "half";
export type ReportBlockSnapshot = {
  columns?: string[];
  rows: Array<Record<string, unknown>>;
};

export type ReportBlock = {
  id: string;
  title: string;
  subtitle: string;
  meta: string;
  type?: string;
  kind?: ReportBlockKind;
  section?: ReportBlockSection;
  size?: ReportBlockSize;
  params?: Record<string, unknown>;
  snapshot?: ReportBlockSnapshot | null;
  htmlSnapshot?: string | null;
};

export type GlobalSearchTarget = "country" | "brand" | "sku";

export type GlobalSearchTab = {
  screen: Screen;
  label: string;
};

export type GlobalSearchSource = {
  row: Record<string, unknown>;
  tabs: GlobalSearchTab[];
};

export type GlobalSearchResult = {
  id: string;
  target: GlobalSearchTarget;
  label: string;
  description: string;
  amount: number;
  qty: number;
  screen: Screen;
  searchText: string;
  tabs: string[];
  tabScreens: Screen[];
};

// YoY는 항상 "동일 월 구간"끼리 비교한다. months는 비교에 사용할 월 창(최신 연도에 존재하는 월),
// 월 정보가 아예 없는 연 단위 데이터면 null(연 전체 비교).
export type ComparableYearWindow = { latestYear: number; previousYear: number; months: Set<number> | null };
