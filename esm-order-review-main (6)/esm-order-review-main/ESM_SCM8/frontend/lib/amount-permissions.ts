export type UserPermissions = {
  canViewAmountData: boolean;
  canDownloadAmountData: boolean;
  canExportAmountReport: boolean;
};

export const AMOUNT_DATA_ALLOWED_USERS = new Set(["adminmaster", "ia"]);

const NON_AMOUNT_TOKENS = [
  "ratio", "share", "percentage", "percent", "contribution", "marketshare",
  "growthrate", "rank", "점유율", "비중", "구성비", "증감률", "순위"
] as const;
const AMOUNT_TOKENS = [
  "amount", "revenue", "salesvalue", "inventoryvalue", "inventorycost",
  "stockvalue", "orderamount", "purchaseamount", "totalamount", "unitprice",
  "averageprice", "avgprice", "currencyamount", "krwamount", "salesprice",
  "purchaseprice", "매출액", "판매금액", "발주금액", "구매금액", "재고금액",
  "금액", "총매출", "재고자본", "매입단가", "판매단가", "평균단가", "평균판매단가",
  "원화환산", "환산금액", "합계금액", "총액"
] as const;
const EXACT_AMOUNT_KEYS = new Set([
  "amount", "revenue", "sales", "price", "cost", "매출", "금액", "단가", "원화"
]);
const CONTEXT_LABEL_KEYS = new Set(["metric", "metricname", "metriclabel", "measure", "basis", "기준", "지표", "항목"]);
const CONTEXT_VALUE_KEYS = new Set(["value", "값", "current", "previous", "현재", "이전", "display", "표시값"]);
const CURRENCY_VALUE_PATTERN =
  /(?:(?:KRW|EUR|USD|GBP|PLN)\s*)?[₩€$£]\s*-?[\d,.]+(?:\s*(?:억|만|천))?|-?[\d,.]+\s*(?:원|억원|만원)/gi;

export function normalizeUsername(username?: string | null): string {
  return username?.trim().toLowerCase() ?? "";
}

export function canViewAmountData(username?: string | null): boolean {
  return AMOUNT_DATA_ALLOWED_USERS.has(normalizeUsername(username));
}

export function getUserPermissions(username?: string | null): UserPermissions {
  const allowed = canViewAmountData(username);
  return {
    canViewAmountData: allowed,
    canDownloadAmountData: allowed,
    canExportAmountReport: allowed
  };
}

function normalizeFieldName(value: unknown): string {
  return String(value ?? "").replace(/[\s_\-./()[\]]+/g, "").toLowerCase();
}

export function isAmountField(fieldName: unknown): boolean {
  const normalized = normalizeFieldName(fieldName);
  if (!normalized || NON_AMOUNT_TOKENS.some((token) => normalized.includes(token))) return false;
  return EXACT_AMOUNT_KEYS.has(normalized) || AMOUNT_TOKENS.some((token) => normalized.includes(token));
}

export function redactAmountText(value: string): string {
  return value.replace(CURRENCY_VALUE_PATTERN, "[금액 제한]");
}

export function sanitizeAmountData<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeAmountData(item)) as T;
  }
  if (value && typeof value === "object") {
    const source = value as Record<string, unknown>;
    const amountContext = Object.entries(source).some(
      ([key, item]) =>
        CONTEXT_LABEL_KEYS.has(normalizeFieldName(key)) &&
        typeof item === "string" &&
        isAmountField(item)
    );
    const sanitized: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(source)) {
      const normalizedKey = normalizeFieldName(key);
      if (isAmountField(key)) continue;
      if (amountContext && CONTEXT_VALUE_KEYS.has(normalizedKey)) continue;
      if (normalizedKey === "htmlsnapshot" || normalizedKey === "__htmlsnapshot") {
        sanitized[key] = null;
        continue;
      }
      sanitized[key] = sanitizeAmountData(item);
    }
    return sanitized as T;
  }
  return (typeof value === "string" ? redactAmountText(value) : value) as T;
}
