export type LeadTimeMethod = {
  code: string;
  label: string;
  lead_time_days: number;
  entity_code?: string;
  transport_code?: string;
  transport_group?: string | null;
  service_type?: string | null;
  display_name?: string;
  source?: string;
  effective_date?: string;
};

export type LeadTimeReference = {
  entity_code: string;
  effective_date: string;
  source: string;
  methods: LeadTimeMethod[];
};

export type LeadTimeInputValues = Record<string, string>;
export type LeadTimeOverrides = Record<string, number>;

export type EffectiveLeadTimeMethod = {
  code: string;
  label: string;
  days: number;
};

export const LEAD_TIME_STORAGE_PREFIX = "esm_scm_lead_time_overrides";
const TRANSPORT_TIE_PRIORITY: Record<string, number> = {
  OCEAN: 0,
  RAIL: 1,
  TRUCKING: 2,
  AIR_TS: 3,
  AIR: 4,
  AIR_DIR: 4
};

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`리드타임 응답의 ${field} 값이 올바르지 않습니다.`);
  }
  return value.trim();
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function nullableString(value: unknown): string | null | undefined {
  return value === null ? null : optionalString(value);
}

export function parseLeadTimeReference(payload: unknown): LeadTimeReference {
  if (!payload || typeof payload !== "object") {
    throw new Error("리드타임 응답 형식이 올바르지 않습니다.");
  }
  const record = payload as Record<string, unknown>;
  if (!Array.isArray(record.methods)) {
    throw new Error("리드타임 응답에 운송수단 목록이 없습니다.");
  }

  const seenCodes = new Set<string>();
  const methods = record.methods.map((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`리드타임 응답의 ${index + 1}번째 운송수단이 올바르지 않습니다.`);
    }
    const method = item as Record<string, unknown>;
    const code = requiredString(method.code, `methods[${index}].code`);
    if (seenCodes.has(code)) {
      throw new Error(`리드타임 응답에 중복 운송수단 코드가 있습니다: ${code}`);
    }
    seenCodes.add(code);
    const leadTimeDays = Number(method.lead_time_days);
    if (!Number.isInteger(leadTimeDays) || leadTimeDays <= 0) {
      throw new Error(`리드타임 응답의 ${code} 일수는 양의 정수여야 합니다.`);
    }
    return {
      code,
      label: requiredString(method.label, `methods[${index}].label`),
      lead_time_days: leadTimeDays,
      entity_code: optionalString(method.entity_code),
      transport_code: optionalString(method.transport_code),
      transport_group: nullableString(method.transport_group),
      service_type: nullableString(method.service_type),
      display_name: optionalString(method.display_name),
      source: optionalString(method.source),
      effective_date: optionalString(method.effective_date)
    };
  });

  return {
    entity_code: requiredString(record.entity_code, "entity_code"),
    effective_date: requiredString(record.effective_date, "effective_date"),
    source: requiredString(record.source, "source"),
    methods
  };
}

export function leadTimeStorageKey(username: string, entityCode: string): string {
  return `${LEAD_TIME_STORAGE_PREFIX}:${encodeURIComponent(username)}:${encodeURIComponent(entityCode)}`;
}

export function leadTimeValuesFromMethods(
  methods: LeadTimeMethod[],
  storedOverrides: LeadTimeInputValues = {}
): LeadTimeInputValues {
  return Object.fromEntries(
    methods.map((method) => [
      method.code,
      Object.prototype.hasOwnProperty.call(storedOverrides, method.code)
        ? storedOverrides[method.code]
        : String(method.lead_time_days)
    ])
  );
}

export function resolveLeadTime(
  methods: LeadTimeMethod[],
  values: LeadTimeInputValues,
  transportCode: string
): number | null {
  if (!methods.some((method) => method.code === transportCode)) {
    return null;
  }
  const parsed = Number(values[transportCode]);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function buildLeadTimeOverrides(
  methods: LeadTimeMethod[],
  values: LeadTimeInputValues
): LeadTimeOverrides {
  const overrides: LeadTimeOverrides = {};
  for (const method of methods) {
    const days = resolveLeadTime(methods, values, method.code);
    if (days === null) {
      throw new Error(`${method.label} 리드타임은 0보다 큰 정수로 입력해 주세요.`);
    }
    if (days !== method.lead_time_days) {
      overrides[method.code] = days;
    }
  }
  return overrides;
}

export function effectiveLeadTimeMethods(
  methods: LeadTimeMethod[],
  values: LeadTimeInputValues
): EffectiveLeadTimeMethod[] {
  return methods.flatMap((method) => {
    const days = resolveLeadTime(methods, values, method.code);
    return days === null ? [] : [{ code: method.code, label: method.label, days }];
  });
}

export function chooseTransportForAvailableDays(
  methods: EffectiveLeadTimeMethod[],
  availableDays: number
): EffectiveLeadTimeMethod | null {
  const candidates = methods
    .filter((method) => Number.isInteger(method.days) && method.days > 0)
    .sort((left, right) => {
      const daysDifference = right.days - left.days;
      if (daysDifference !== 0) return daysDifference;
      return (TRANSPORT_TIE_PRIORITY[left.code] ?? 100) -
        (TRANSPORT_TIE_PRIORITY[right.code] ?? 100);
    });
  if (candidates.length === 0) {
    return null;
  }
  return candidates.find((method) => availableDays >= method.days) ?? candidates[candidates.length - 1];
}
