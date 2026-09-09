export function validCrossLabel(value: string) {
  const normalized = value.normalize("NFKC").trim().toLowerCase();
  return Boolean(normalized) && !["-", "미상", "unknown", "n/a", "nan", "none"].includes(normalized) && !value.includes("미분류");
}
