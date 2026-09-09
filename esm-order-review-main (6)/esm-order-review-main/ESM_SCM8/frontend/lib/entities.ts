export const ENTITY_OPTIONS = [
  { code: "HQ", displayName: "본사", legalName: "Silicon2 Co., Ltd.", integrated: true, orderIntegrated: false, insightIntegrated: true },
  { code: "PL", displayName: "폴란드", legalName: "SKO Sp. z o.o.", integrated: true, orderIntegrated: true, insightIntegrated: true },
  { code: "UK", displayName: "영국", legalName: "STYLEKOREAN UK LIMITED", integrated: false, orderIntegrated: false, insightIntegrated: false },
  { code: "USA", displayName: "미국", legalName: "Stylekorean Inc.", integrated: true, orderIntegrated: true, insightIntegrated: true },
  { code: "ME", displayName: "중동·두바이", legalName: "STYLEKOREAN MIDDLE EAST TRADING FZE", integrated: false, orderIntegrated: false, insightIntegrated: false },
  { code: "MX", displayName: "멕시코", legalName: "STYLEKOREAN MX S. DE R.L. DE C.V.", integrated: false, orderIntegrated: false, insightIntegrated: false },
  { code: "MY", displayName: "말레이시아", legalName: "STYLEKOREAN MY SDN. BHD.", integrated: false, orderIntegrated: false, insightIntegrated: false },
  { code: "VN", displayName: "베트남", legalName: "STYLEKOREAN VIETNAM", integrated: false, orderIntegrated: false, insightIntegrated: false }
] as const;

export type EntityCode = (typeof ENTITY_OPTIONS)[number]["code"];
export type EntityOption = (typeof ENTITY_OPTIONS)[number];

export const ENTITY_BY_CODE = Object.fromEntries(
  ENTITY_OPTIONS.map((entity) => [entity.code, entity])
) as Record<EntityCode, EntityOption>;

export function isEntityCode(value: unknown): value is EntityCode {
  return typeof value === "string" && value in ENTITY_BY_CODE;
}

export function allowedEntityOptions(codes: readonly string[]): EntityOption[] {
  const allowed = new Set(codes);
  return ENTITY_OPTIONS.filter((entity) => allowed.has(entity.code));
}
