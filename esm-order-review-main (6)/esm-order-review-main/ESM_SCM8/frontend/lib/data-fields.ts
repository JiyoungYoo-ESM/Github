export function numberValue(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function textValue(value: unknown) {
  return value === null || value === undefined ? "" : String(value).trim();
}

export function findKey(row: Record<string, unknown> | undefined, candidates: string[]) {
  const keys = Object.keys(row ?? {});
  return keys.find((key) => candidates.some((candidate) => key.toLowerCase().includes(candidate.toLowerCase()))) ?? "";
}

export function monthValue(row: Record<string, unknown>) {
  return numberValue(row.month ?? row["월"]);
}

export function yearValue(row: Record<string, unknown>) {
  return numberValue(row.year ?? row["연도"] ?? row["년"]);
}
