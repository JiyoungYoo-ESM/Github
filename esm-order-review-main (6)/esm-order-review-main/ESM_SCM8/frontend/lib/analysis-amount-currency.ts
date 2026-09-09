let currentAnalysisAmountCurrencyCode = "";

export function setAnalysisAmountCurrencyCode(value: unknown) {
  const code = String(value ?? "").trim().toUpperCase();
  currentAnalysisAmountCurrencyCode = code === "KRW" ? "KRW" : "";
}

export function getAnalysisAmountCurrencyCode() {
  return currentAnalysisAmountCurrencyCode;
}
