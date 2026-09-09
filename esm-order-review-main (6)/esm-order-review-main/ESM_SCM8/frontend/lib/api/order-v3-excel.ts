import { apiFetch, ApiRequestError, parseApiError } from "./client";
import { getActiveEntityCode } from "../entity-session";
import type { V3ExcelOptions } from "../../components/redesign/screens/order-v3/excelExport";

export async function downloadOrderV3Excel(options: V3ExcelOptions, signal: AbortSignal, onProgress?: (bytes: number) => void): Promise<Blob> {
  const assertActive = () => {
    signal.throwIfAborted();
    if (getActiveEntityCode() !== options.result.entity_code) throw new DOMException("분석 대상 법인이 변경되었습니다.", "AbortError");
  };
  assertActive();
  const selected = new Set([...options.skus, ...(options.attentionSkus ?? [])]);
  const response = await apiFetch("/api/order-v3-excel", {
    method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId: options.result.job_id, entityCode: options.result.entity_code,
      snapshotId: options.result.source_snapshot_id ?? null, scenario: options.scenario,
      skus: options.skus, attentionSkus: options.attentionSkus ?? [],
      decisions: Object.fromEntries(Object.entries(options.decisions).filter(([sku]) => selected.has(sku))),
      viewTitle: options.viewTitle, attentionScope: options.attentionScope ?? options.viewTitle,
      brandScope: options.brandScope ?? null })
  });
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
  assertActive();
  const reader = response.body?.getReader();
  if (!reader) throw new Error("엑셀 파일을 받지 못했습니다.");
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", cancel, { once: true });
  const parts: ArrayBuffer[] = []; let received = 0, lastReport = 0;
  try {
    for (;;) {
      assertActive();
      const { done, value } = await reader.read();
      assertActive();
      if (done) break;
      parts.push(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer);
      received += value.byteLength;
      // Thousands of ZIP chunks must not rerender the 40k-SKU review screen.
      if (Date.now() - lastReport >= 250) { onProgress?.(received); lastReport = Date.now(); }
    }
    onProgress?.(received);
    assertActive();
    return new Blob(parts, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  } finally { signal.removeEventListener("abort", cancel); reader.releaseLock(); }
}
