import { getCountryRegion } from "./region-groups.ts";

export type CountrySummary = {
  country: string;
  region: string;
  qty: number;
  amount: number;
  share: number;
};

export type SkuRow = {
  code: string;
  name: string;
  brand: string;
  category1: string;
  category2: string;
  qty: number;
  amount: number;
  stockStatus?: string;
};

export type IngredientRow = {
  name: string;
  qty: number;
  amount: number;
  skuCount: number;
  brandCount: number;
};

export type BrandRow = {
  brand: string;
  qty: number;
  amount: number;
  skuCount: number;
  share: number;
};

// NFKC 정규화는 비싸고, 컬럼 키·후보 문자열은 종류가 한정적이라 결과를 캐시한다.
const normalizeKeyCache = new Map<string, string>();

function normalizeKey(value: string) {
  const cached = normalizeKeyCache.get(value);
  if (cached !== undefined) {
    return cached;
  }
  const result = value.normalize("NFKC").replace(/\s+/g, "").toLowerCase();
  normalizeKeyCache.set(value, result);
  return result;
}

// 한 데이터셋의 모든 행은 컬럼 구조가 동일하다. 정규화 키→원본 키 매핑을 컬럼
// 시그니처별로 캐시해 행마다 Map을 다시 만들지 않는다(대용량 조회의 주요 병목).
const shapeMapCache = new Map<string, Map<string, string>>();

export function field(row: Record<string, unknown> | undefined, candidates: string[]) {
  if (!row) {
    return "";
  }
  const keys = Object.keys(row);
  const signature = keys.join("");
  let normalized = shapeMapCache.get(signature);
  if (!normalized) {
    normalized = new Map(keys.map((key) => [normalizeKey(key), key]));
    shapeMapCache.set(signature, normalized);
  }
  for (const candidate of candidates) {
    const key = normalized.get(normalizeKey(candidate));
    if (key) {
      return key;
    }
  }
  return "";
}

export function textValue(value: unknown) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value).trim();
}

export function numberValue(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const text = String(value ?? "").replace(/,/g, "").trim();
  const number = Number(text);
  return Number.isFinite(number) ? number : 0;
}

export function countryOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["국가", "국가명", "판매국가", "수출국가", "배송국가", "권역국가", "country", "nation", "site", "Site"])]) || "미상";
}

export function category1Of(row: Record<string, unknown>) {
  return textValue(row[field(row, ["기능구분1", "대분류", "category1", "class1"])]) || "미분류";
}

export function category2Of(row: Record<string, unknown>) {
  return textValue(row[field(row, ["기능구분2", "중분류", "category2", "class2"])]) || "미분류";
}

export function skuCodeOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["상품코드", "SKU", "sku", "prod_cd", "product_code"])]) || "-";
}

export function productNameOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["상품명", "product_name", "prod_nm", "name"])]) || "-";
}

export function brandOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["브랜드", "brand"])]) || "미분류 브랜드";
}

export function ingredientOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["성분", "ingredient", "keyword"])]) || "미분류 성분";
}

export function qtyOf(row: Record<string, unknown>) {
  return numberValue(row[field(row, ["판매수량", "수량", "qty"])]);
}

export function amountOf(row: Record<string, unknown>) {
  return numberValue(row[field(row, ["판매금액", "환산금액", "금액", "amount"])]);
}

export function monthKeyOf(row: Record<string, unknown>) {
  const monthNumber = numberValue(row[field(row, ["month", "월", "monthNo", "month_no"])]);
  if (monthNumber >= 1 && monthNumber <= 12) {
    const yearValue = numberValue(row[field(row, ["year", "연도", "년도", "YYYY"])]);
    const yearText = yearValue > 0 ? String(Math.trunc(yearValue)) : "";
    const monthText = String(Math.trunc(monthNumber)).padStart(2, "0");
    return yearText ? `${yearText}-${monthText}` : monthText;
  }

  const value = textValue(row[field(row, ["출고일", "판매일", "주문일", "일자", "날짜", "date", "sales_date", "shipment_date"])]);
  if (!value) return "";

  const normalized = value.replace(/[./]/g, "-").trim();
  const ymdMatch = normalized.match(/(\d{4})-(\d{1,2})/);
  if (ymdMatch) {
    return `${ymdMatch[1]}-${ymdMatch[2].padStart(2, "0")}`;
  }

  const compactMatch = normalized.match(/^(\d{4})(\d{2})(\d{2})?/);
  if (compactMatch) {
    return `${compactMatch[1]}-${compactMatch[2]}`;
  }

  return "";
}

export function same(left: string, right: string) {
  return left.normalize("NFKC").trim().toLowerCase() === right.normalize("NFKC").trim().toLowerCase();
}

export function cleanCode(value: string) {
  const text = value.trim();
  return text.endsWith(".0") ? text.slice(0, -2) : text;
}

export function regionOfCountry(country: string) {
  const detailedRegion = getCountryRegion(country).region;
  const continentByRegion: Record<string, string> = {
    북유럽: "유럽",
    서유럽: "유럽",
    남유럽: "유럽",
    중동유럽: "유럽",
    동아시아: "아시아",
    동남아시아: "아시아",
    남아시아: "아시아",
    중앙아시아: "아시아",
    중동: "아시아",
    북미: "북아메리카",
    // region-groups.ts의 RegionGroup 키("중미·카리브")와 반드시 일치해야 한다.
    "중미·카리브": "남아메리카",
    남미: "남아메리카",
    북아프리카: "아프리카",
    서아프리카: "아프리카",
    동아프리카: "아프리카",
    중앙아프리카: "아프리카",
    남아프리카: "아프리카",
    오세아니아: "오세아니아"
  };

  return continentByRegion[detailedRegion] ?? detailedRegion;
}

export function hasKnownCountry(country: string) {
  const normalized = country.normalize("NFKC").trim().toLowerCase();
  return Boolean(normalized) && !["미상", "unknown", "n/a", "nan", "none"].includes(normalized);
}

export function monthLabel(month: number) {
  return `${month}월`;
}

export function recommendedMonth(peakMonth: number) {
  return ((peakMonth + 9 - 1) % 12) + 1;
}

export function buildCountrySummary(rows: Array<Record<string, unknown>>): CountrySummary[] {
  const totals = new Map<string, { qty: number; amount: number }>();
  rows.forEach((row) => {
    const country = countryOf(row);
    if (!hasKnownCountry(country)) return;
    const current = totals.get(country) ?? { qty: 0, amount: 0 };
    current.qty += qtyOf(row);
    current.amount += amountOf(row);
    totals.set(country, current);
  });
  const totalQty = Array.from(totals.values()).reduce((sum, item) => sum + item.qty, 0);
  return Array.from(totals.entries())
    .map(([country, item]) => ({
      country,
      region: regionOfCountry(country),
      qty: item.qty,
      amount: item.amount,
      share: totalQty > 0 ? (item.qty / totalQty) * 100 : 0
    }))
    .filter((item) => item.qty > 0)
    .sort((a, b) => b.qty - a.qty);
}
