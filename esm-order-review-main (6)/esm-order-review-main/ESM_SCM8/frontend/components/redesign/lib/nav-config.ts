import {
  Box,
  CalendarDays,
  Check,
  Database,
  FileText,
  FlaskConical,
  Globe2,
  Grid3X3,
  Layers,
  ListChecks,
  MessageCircleMore,
  SlidersHorizontal,
  Sigma,
  Tag,
  Upload
} from "lucide-react";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";
import type { Metric, Mode, NavItem, Screen, SharedAnalysisSettings, TableRow } from "./types";
import { todayKst } from "./workspace-format";

export const DEFAULT_SHARED_ANALYSIS_SETTINGS: SharedAnalysisSettings = {
  safetyMonths: "3",
  leadTimeMethods: [],
  leadTimeValues: {},
  leadTimeLoading: false,
  leadTimeError: ""
};

export const ORDER_SCREENS: Screen[] = ["prep", "diag", "order", "order-v2", "order-v3", "season-factor", "gap", "final"];
export const INSIGHT_RESULT_SCREENS: Screen[] = ["country", "brand", "category", "sku", "season", "cross", "report", "ingredient"];
export const FAVORITE_NAV_STORAGE_KEY = "silicon2-scm-favorite-tabs";
export const DEFAULT_FAVORITE_NAV_IDS: Screen[] = [];

export function modeOf(screen: Screen): Mode {
  if (screen === "overview") return "overview";
  if (screen === "support") return "support";
  if (screen === "diag") return "quality";
  return ORDER_SCREENS.includes(screen) ? "order" : "insight";
}

export const insightRequiredCopy: Partial<Record<Screen, { title: string; description: string }>> = {
  country: {
    title: "국가 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 국가/권역별 수요 결과가 이 화면에 반영됩니다."
  },
  brand: {
    title: "브랜드 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 브랜드별 매출과 성장 지표가 이 화면에 반영됩니다."
  },
  sku: {
    title: "SKU 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 SKU별 판매 추이와 우선순위가 이 화면에 반영됩니다."
  },
  category: {
    title: "제품군 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 기능구분별 제품군 순위와 SKU 분포가 이 화면에 반영됩니다."
  },
  season: {
    title: "시즌 캘린더 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 월별 피크와 시즌 수요 패턴이 이 화면에 반영됩니다."
  },
  ingredient: {
    title: "성분 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 성분별 트렌드와 브랜드 분포가 이 화면에 반영됩니다."
  },
  cross: {
    title: "교차분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 국가·브랜드·SKU·성분 교차 결과가 이 화면에 반영됩니다."
  },
  report: {
    title: "브랜드 리포트 분석이 필요합니다",
    description: "아직 이번 세션에서 분석 시작이 실행되지 않았습니다. 데이터 입력 탭에서 분석 시작을 누르면 리포트 생성에 필요한 분석 블록이 이 화면에 반영됩니다."
  }
};

export const orderNav = [
  { id: "prep", label: "데이터 입력", icon: Database },
  { id: "order", label: "발주분석 V1", icon: ListChecks },
  { id: "order-v2", label: "발주분석 V2", icon: Sigma },
  { id: "order-v3", label: "발주분석 V3", icon: FlaskConical, statusLabel: "BETA" }
] satisfies NavItem[];

export const overviewNav = [
  { id: "overview", label: "전사 재고 현황", icon: Box }
] satisfies NavItem[];

const ingredientNavItem = { id: "ingredient", label: "성분", icon: FlaskConical } satisfies NavItem;

export const insightNav = [
  { id: "idata", label: "데이터 입력", icon: Upload },
  { id: "country", label: "국가", icon: Globe2 },
  { id: "brand", label: "브랜드", icon: Tag },
  { id: "category", label: "제품군", icon: Layers },
  { id: "sku", label: "SKU", icon: Box },
  ...(INGREDIENT_ANALYSIS_ENABLED ? [ingredientNavItem] : [])
] satisfies NavItem[];

export const deferredInsightNav = INGREDIENT_ANALYSIS_ENABLED
  ? []
  : [{ ...ingredientNavItem, disabled: true, statusLabel: "준비 중" }] satisfies NavItem[];

export const deepInsightNav = [
  { id: "season", label: "시즌 캘린더", icon: CalendarDays },
  { id: "cross", label: "교차분석", icon: Grid3X3 },
  { id: "report", label: "브랜드 리포트", icon: FileText }
] satisfies NavItem[];

export const qualityNav = [
  { id: "diag", label: "데이터 진단", icon: Check }
] satisfies NavItem[];

export const supportNav = [
  { id: "support", label: "고객센터", icon: MessageCircleMore }
] satisfies NavItem[];

export const v3SettingsNav = [
  { id: "season-factor", label: "계절지수 관리", icon: SlidersHorizontal }
] satisfies NavItem[];

export const allNavItems: NavItem[] = [...overviewNav, ...orderNav, ...insightNav, ...deepInsightNav, ...qualityNav, ...v3SettingsNav, ...supportNav];

export const titles: Record<Screen, { crumb: string; title: string; description: string }> = {
  overview: {
    crumb: "경영 · OVERVIEW",
    title: "전사 재고 현황",
    description: "전사 보유 재고를 법인과 창고 단위로 확인합니다."
  },
  prep: {
    crumb: "발주 · QUANTITATIVE",
    title: "데이터 입력",
    description: "분석 기준일, 환율, 리드타임과 업로드 원천을 먼저 정리합니다."
  },
  diag: {
    crumb: "발주 · QUANTITATIVE",
    title: "데이터 진단",
    description: "상품코드, 바코드, 브랜드, 카테고리 매핑 누락을 발주 전에 점검합니다."
  },
  order: {
    crumb: "발주 · QUANTITATIVE",
    title: "발주분석 V1",
    description: "MOI와 이동 중 재고를 반영해 발주 필요 SKU를 우선순위로 정리합니다."
  },
  "order-v2": {
    crumb: "발주 · QUANTITATIVE",
    title: "발주분석 V2",
    description: "최근 13주 상당 수요·변동성·리드타임·서비스 수준을 반영한 통계 기반 발주 제안입니다."
  },
  "order-v3": {
    crumb: "발주 · QUANTITATIVE",
    title: "발주분석 V3",
    description: "SKU별 수요 패턴과 계절성을 자동 분류하고 계산 근거를 함께 검토하는 발주 제안 화면입니다."
  },
  "season-factor": {
    crumb: "관리자 · V3 설정",
    title: "계절지수 관리",
    description: "자동 검증을 통과한 계절지수를 발주분석 V3에 적용합니다."
  },
  gap: {
    crumb: "발주 · QUANTITATIVE",
    title: "재고 공백",
    description: "ETA 이전에 품절 가능성이 있는 SKU와 긴급 보충 필요 수량을 확인합니다."
  },
  season: {
    crumb: "분석 · INSIGHT",
    title: "시즌 캘린더",
    description: "월별 수요 패턴과 피크월을 확인해 시즌성 흐름을 판단합니다."
  },
  final: {
    crumb: "발주 · QUANTITATIVE",
    title: "최종 발주",
    description: "중복, 고위험, 예산 제한을 반영한 최종 발주 후보를 확정합니다."
  },
  idata: {
    crumb: "분석 · INSIGHT",
    title: "데이터 입력",
    description: "국가, 권역, SKU 인사이트 분석에 필요한 판매·상품 데이터를 준비합니다."
  },
  country: {
    crumb: "분석 · INSIGHT",
    title: "국가 분석",
    description: "권역별 판매 비중과 국가별 성장률을 비교해 시장 우선순위를 봅니다."
  },
  brand: {
    crumb: "분석 · INSIGHT",
    title: "브랜드 분석",
    description: "브랜드 매출, 성장률, MOI를 함께 보며 경쟁 위치와 건강도를 확인합니다."
  },
  sku: {
    crumb: "분석 · INSIGHT",
    title: "SKU 분석",
    description: "핵심 SKU의 판매 추이, 피크월, 재고 위험을 한 화면에서 비교합니다."
  },
  category: {
    crumb: "분석 · INSIGHT",
    title: "제품군 분석",
    description: "기능구분별 제품군 순위와 제품군 내 SKU 경쟁 위치를 확인합니다."
  },
  ingredient: {
    crumb: "분석 · INSIGHT",
    title: "성분 분석",
    description: "성분 키워드별 성장률과 브랜드 분포를 추적합니다."
  },
  cross: {
    crumb: "분석 · INSIGHT",
    title: "교차 분석",
    description: "국가, 브랜드, SKU 조합을 매트릭스로 비교해 숨은 기회를 찾습니다."
  },
  report: {
    crumb: "분석 · INSIGHT",
    title: "브랜드 자동 리포트",
    description: "브랜드를 선택해 주요 판매·재고 인사이트를 자동으로 조립하고 PDF로 출력합니다."
  },
  support: {
    crumb: "지원 · SUPPORT",
    title: "고객센터",
    description: "자주 묻는 질문을 확인하거나 문의를 접수하고 처리 상태를 확인합니다."
  }
};

export const metrics: Record<Screen, Metric[]> = {
  overview: [],
  prep: [
    { label: "분석 기준일", value: todayKst, sub: "KST 기준", tone: "muted" },
    { label: "EUR/KRW", value: "1,760.03", sub: "자동 조회", tone: "green" },
    { label: "업로드 파일", value: "6", sub: "필수 6종", tone: "muted" },
    { label: "보정값", value: "3", sub: "리드타임 2 · 안전재고 1", tone: "brand" }
  ],
  diag: [
    { label: "검증 파일", value: "6", sub: "전체 통과", tone: "green" },
    { label: "미분류 SKU", value: "18", sub: "확인 필요", tone: "brand" },
    { label: "중복 바코드", value: "3", sub: "병합 후보", tone: "amber" },
    { label: "매핑 성공률", value: "98.4%", sub: "+1.2%p", tone: "green" }
  ],
  order: [
    { label: "발주 권장 SKU", value: "126", sub: "검토 필요", tone: "muted" },
    { label: "긴급 SKU", value: "18", sub: "MOI < 1.5", tone: "brand" },
    { label: "권장 발주 금액", value: "₩8.4억", sub: "환율 반영", tone: "muted" },
    { label: "평균 MOI", value: "2.3개월", sub: "목표 3.0개월", tone: "amber" }
  ],
  "order-v2": [],
  "order-v3": [],
  "season-factor": [],
  gap: [
    { label: "입고 전 품절 SKU", value: "34", sub: "ETA 이후 입고", tone: "brand" },
    { label: "7일 이상 품절 SKU", value: "11", sub: "장기 공백", tone: "brand" },
    { label: "품절 예상 수량", value: "5,330", sub: "공백 기간 기준", tone: "green" },
    { label: "입고일 미확인 SKU", value: "18", sub: "ETA 확인 필요", tone: "amber" }
  ],
  season: [
    { label: "피크 월", value: "7월", sub: "선케어 집중", tone: "brand" },
    { label: "계수 적용 SKU", value: "84", sub: "카테고리 기준", tone: "green" },
    { label: "상향 조정", value: "23%", sub: "전월 대비", tone: "amber" },
    { label: "계절 리스크", value: "중간", sub: "보정 필요", tone: "muted" }
  ],
  final: [
    { label: "최종 발주 SKU", value: "72", sub: "승인 후보", tone: "muted" },
    { label: "총 발주 금액", value: "₩5.6억", sub: "예산 82%", tone: "brand" },
    { label: "고위험 제외", value: "14", sub: "중복 제거", tone: "green" },
    { label: "평균 리드타임", value: "64일", sub: "운송 기준", tone: "muted" }
  ],
  idata: [
    { label: "원천 데이터", value: "4종", sub: "상품·판매·재고·PO", tone: "muted" },
    { label: "분석 준비율", value: "67%", sub: "2개 대기", tone: "amber" },
    { label: "최근 갱신", value: "09:24", sub: "KST", tone: "green" },
    { label: "필수 매핑", value: "12건", sub: "확인 필요", tone: "brand" }
  ],
  country: [
    { label: "전체 매출", value: "₩194.3억", sub: "+16.8% YoY", tone: "brand" },
    { label: "매출 발생 국가", value: "23개국", sub: "+3개국", tone: "green" },
    { label: "매출 발생 브랜드", value: "38개", sub: "신규 5개", tone: "green" },
    { label: "매출 발생 SKU", value: "1,284", sub: "+112", tone: "green" }
  ],
  brand: [
    { label: "상위 브랜드 매출", value: "₩27.6억", sub: "아누아 기준", tone: "brand" },
    { label: "성장 브랜드", value: "12개", sub: "+4 YoY", tone: "green" },
    { label: "평균 MOI", value: "2.4개월", sub: "안정권", tone: "muted" },
    { label: "집중 리스크", value: "중간", sub: "상위 3개 42%", tone: "amber" }
  ],
  sku: [
    { label: "피크 SKU", value: "42개", sub: "시즌 집중", tone: "brand" },
    { label: "고성장 SKU", value: "118", sub: "+22 YoY", tone: "green" },
    { label: "평균 리드타임", value: "64일", sub: "운송 기준", tone: "muted" },
    { label: "품절 위험 SKU", value: "16", sub: "MOI < 1.5", tone: "brand" }
  ],
  category: [
    { label: "전체 제품군", value: "36개", sub: "기능구분 1·2", tone: "muted" },
    { label: "최대 제품군", value: "썬케어 > 크림", sub: "25% 비중", tone: "brand" },
    { label: "구성 SKU", value: "1,284", sub: "제품군 합계", tone: "green" },
    { label: "집중 제품군", value: "상위 5", sub: "62% 비중", tone: "amber" }
  ],
  ingredient: [
    { label: "트렌드 성분", value: "24개", sub: "상승 구간", tone: "brand" },
    { label: "고성장 키워드", value: "PDRN", sub: "+48% YoY", tone: "green" },
    { label: "신규 조합", value: "9개", sub: "브랜드 확장", tone: "amber" },
    { label: "검토 필요", value: "6건", sub: "성분명 매핑", tone: "muted" }
  ],
  cross: [
    { label: "교차 조합", value: "184", sub: "국가 × 브랜드", tone: "brand" },
    { label: "중복 통합", value: "31건", sub: "리포트 반영", tone: "green" },
    { label: "핵심 매트릭스", value: "6개", sub: "공유 가능", tone: "muted" },
    { label: "비정상 조합", value: "7건", sub: "검토 필요", tone: "brand" }
  ],
  report: [
    { label: "담은 블록", value: "5개", sub: "국가·브랜드·SKU", tone: "brand" },
    { label: "출력 형식", value: "2종", sub: "PDF · DOCX", tone: "muted" },
    { label: "보고 옵션", value: "거래처용", sub: "원가 제거", tone: "amber" },
    { label: "생성 준비", value: "완료", sub: "표지·요약 포함", tone: "green" }
  ],
  support: []
};

export const rows: Record<Screen, { headers: string[]; rows: TableRow[] }> = {
  overview: {
    headers: [],
    rows: []
  },
  prep: {
    headers: ["파일", "상태", "행 수", "마지막 갱신", "다음 작업"],
    rows: [
      ["상품목록", "완료", "12,480", "09:12", "매핑 확인"],
      ["판매이력", "완료", "184,220", "09:14", "분석 가능"],
      ["현재재고", "대기", "-", "-", "업로드 필요"],
      ["미입고 PO", "대기", "-", "-", "업로드 필요"]
    ]
  },
  diag: {
    headers: ["SKU", "브랜드", "상태", "판매수량", "조치"],
    rows: [
      ["DRAS01", "닥터알토", "카테고리 미매핑", "8,210", "검토"],
      ["ANUA-SET-02", "아누아", "바코드 중복", "5,880", "병합"],
      ["BOJ-SUN-NEW", "조선미녀", "신규 SKU", "3,420", "등록"],
      ["MEDI-AGE-R", "메디큐브", "성분명 누락", "2,180", "보강"]
    ]
  },
  order: {
    headers: ["SKU", "브랜드", "EU 가용", "월수요", "MOI", "운송중", "권장 발주", "상태"],
    rows: [
      ["ANUA-HEART-TONER", "아누아", "1,240", "3,850", "1.0", "600", "4,800", "긴급"],
      ["MEDICUBE-AGE-R", "메디큐브", "880", "6,210", "1.2", "0", "3,600", "긴급"],
      ["BOJ-RELIEF-SUN", "조선미녀", "2,140", "7,420", "2.0", "1,200", "2,900", "주의"],
      ["CELIMAX-NONI-AMPOULE", "셀리맥스", "1,530", "3,880", "2.8", "600", "1,700", "정상"]
    ]
  },
  "order-v2": {
    headers: [],
    rows: []
  },
  "order-v3": {
    headers: [],
    rows: []
  },
  "season-factor": {
    headers: [],
    rows: []
  },
  gap: {
    headers: ["SKU", "브랜드", "현재 MOI", "ETA", "공백일", "보완 수량", "위험"],
    rows: [
      ["ANUA-HEART-TONER", "아누아", "1.0", "07-18", "16일", "4,800", "높음"],
      ["ROMAND-TINT-05", "롬앤", "1.3", "07-26", "21일", "3,100", "높음"],
      ["TORRIDEN-SERUM", "토리든", "1.7", "07-09", "8일", "1,800", "중간"],
      ["COSRX-SNAIL", "코스알엑스", "2.0", "07-03", "4일", "900", "낮음"]
    ]
  },
  season: {
    headers: ["카테고리", "피크월", "1Q", "2Q", "3Q", "4Q", "계수"],
    rows: [
      ["선케어", "7월", "0.72", "1.18", "1.42", "0.88", "1.34"],
      ["진정 토너", "5월", "0.94", "1.22", "1.08", "0.96", "1.12"],
      ["립틴트", "11월", "0.88", "0.96", "1.02", "1.31", "1.18"],
      ["앰플", "3월", "1.16", "1.04", "0.91", "1.08", "1.06"]
    ]
  },
  final: {
    headers: ["SKU", "브랜드", "초안 수량", "조정", "최종 수량", "금액", "승인"],
    rows: [
      ["ANUA-HEART-TONER", "아누아", "4,800", "+12%", "5,376", "₩8,420만", "대기"],
      ["BOJ-RELIEF-SUN", "조선미녀", "2,900", "+8%", "3,132", "₩4,820만", "대기"],
      ["TORRIDEN-SERUM", "토리든", "1,800", "-10%", "1,620", "₩2,610만", "검토"],
      ["ROMAND-TINT-05", "롬앤", "3,100", "0%", "3,100", "₩3,940만", "대기"]
    ]
  },
  idata: {
    headers: ["데이터", "상태", "범위", "품질", "비고"],
    rows: [
      ["국가별 판매", "완료", "2025.01-2026.06", "정상", "분석 가능"],
      ["브랜드 매핑", "완료", "38개 브랜드", "정상", "alias 적용"],
      ["SKU 성분", "진행", "1,284 SKU", "주의", "성분명 6건 확인"],
      ["경쟁 브랜드", "대기", "-", "-", "파일 필요"]
    ]
  },
  country: {
    headers: ["순위", "국가", "매출", "YoY", "점유율"],
    rows: [
      ["1", "미국", "₩42.8억", "+24.8%", "18.6%"],
      ["2", "프랑스", "₩31.4억", "+18.2%", "13.7%"],
      ["3", "아랍에미리트", "₩26.9억", "+15.1%", "11.8%"],
      ["4", "일본", "₩22.1억", "+9.6%", "9.4%"]
    ]
  },
  brand: {
    headers: ["순위", "브랜드", "매출", "YoY", "MOI"],
    rows: [
      ["1", "아누아", "₩27.6억", "+22.8%", "2.4개월"],
      ["2", "조선미녀", "₩23.1억", "+18.4%", "2.7개월"],
      ["3", "메디큐브", "₩18.2억", "+11.2%", "1.9개월"],
      ["4", "셀리맥스", "₩13.8억", "+8.8%", "3.1개월"]
    ]
  },
  sku: {
    headers: ["SKU", "브랜드", "피크월", "매출", "MOI"],
    rows: [
      ["ANUA-HEART-TONER", "아누아", "6월", "₩4.8억", "1.7개월"],
      ["BOJ-RELIEF-SUN", "조선미녀", "5월", "₩3.9억", "2.2개월"],
      ["MEDICUBE-AGE-R", "메디큐브", "7월", "₩3.2억", "1.4개월"],
      ["CELIMAX-NONI-AMPOULE", "셀리맥스", "4월", "₩2.6억", "2.8개월"]
    ]
  },
  category: {
    headers: ["순위", "제품군", "SKU", "판매량", "비중"],
    rows: [
      ["1", "썬케어 > 크림", "42", "128,400", "25.0%"],
      ["2", "스킨케어 > 세럼", "58", "102,700", "20.0%"],
      ["3", "스킨케어 > 수분크림", "31", "56,500", "11.0%"],
      ["4", "클렌징 > 오일/워터/밀크", "27", "51,300", "10.0%"]
    ]
  },
  ingredient: {
    headers: ["성분", "대표 브랜드", "SKU", "YoY", "메모"],
    rows: [
      ["PDRN", "메디큐브", "28", "+48%", "앰플·크림 확장"],
      ["레티놀", "조선미녀", "34", "+31%", "고기능 라인 성장"],
      ["어성초", "아누아", "42", "+24%", "진정 카테고리 핵심"],
      ["나이아신아마이드", "토리든", "37", "+18%", "밝기 개선 수요"]
    ]
  },
  cross: {
    headers: ["조합", "매출", "YoY", "대표 SKU", "리포트"],
    rows: [
      ["미국 × 아누아", "₩8.2억", "+28%", "HEARTLEAF TONER", "담기"],
      ["프랑스 × 조선미녀", "₩6.4억", "+19%", "RELIEF SUN", "담기"],
      ["UAE × 메디큐브", "₩5.1억", "+16%", "AGE-R BOOSTER", "담기"],
      ["일본 × 셀리맥스", "₩3.8억", "+11%", "NONI AMPOULE", "담기"]
    ]
  },
  report: {
    headers: ["블록", "렌즈", "용도", "마스킹", "출력"],
    rows: [
      ["권역별 매출 비중", "국가", "내부·거래처", "선택", "PDF"],
      ["브랜드별 판매 순위", "브랜드", "내부", "없음", "DOCX"],
      ["월별 SKU 판매 추이", "SKU", "영업", "가격 제외", "PDF"],
      ["국가 × 브랜드 매트릭스", "교차", "거래처", "원가 제거", "PDF"]
    ]
  },
  support: {
    headers: [],
    rows: []
  }
};
