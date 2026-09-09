import ExcelJS from "exceljs";
import { createReadStream, createWriteStream } from "node:fs";
import { mkdtemp, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { PassThrough } from "node:stream";
import { finished } from "node:stream/promises";
import { once } from "node:events";
import { setImmediate as yieldToIO } from "node:timers/promises";
import { generateV3Excel, type V3ExcelOptions, type V3ExcelProgress } from "../../components/redesign/screens/order-v3/excelExport.ts";
import type { OrderLogicV3ApiRow, OrderLogicV3Result } from "../api/order-logic-v3.ts";

export type ExcelExportRequest = Pick<V3ExcelOptions, "scenario" | "skus" | "attentionSkus" | "decisions" | "viewTitle" | "attentionScope" | "brandScope"> & {
  jobId: string; entityCode: OrderLogicV3Result["entity_code"]; snapshotId: string | null;
};
export class ExcelExportError extends Error {
  status: number;
  constructor(message: string, status = 409) { super(message); this.status = status; }
}
export function validateExportRequest(value: unknown): ExcelExportRequest {
  const body = value as ExcelExportRequest | null;
  const codes = (items: unknown) => Array.isArray(items) && items.length <= 100_000 && items.every(item => typeof item === "string" && item.length > 0 && item.length <= 256);
  if (!body || typeof body.jobId !== "string" || !/^[a-zA-Z0-9_-]{1,100}$/.test(body.jobId) ||
    !["HQ", "PL", "USA"].includes(body.entityCode) || !["CASH", "SHORTAGE"].includes(body.scenario) ||
    !(body.snapshotId === null || typeof body.snapshotId === "string") ||
    !codes(body.skus) || !codes(body.attentionSkus) ||
    typeof body.viewTitle !== "string" || body.viewTitle.length > 256 ||
    typeof body.attentionScope !== "string" || body.attentionScope.length > 512 ||
    !(body.brandScope === null || (typeof body.brandScope === "string" && body.brandScope.length > 0 && body.brandScope.length <= 256)) ||
    !body.decisions || typeof body.decisions !== "object" || Array.isArray(body.decisions) ||
    Object.values(body.decisions).some(item => !item || !["미검토", "권고 유지", "수량 수정", "발주 보류"].includes(item.decision) || !Number.isFinite(item.finalQty))) {
    throw new ExcelExportError("엑셀 내보내기 요청을 확인해 주세요.", 422);
  }
  if (new Set(body.skus).size !== body.skus.length || new Set(body.attentionSkus).size !== body.attentionSkus!.length) {
    throw new ExcelExportError("엑셀 대상 상품코드가 중복되었습니다.", 422);
  }
  return body;
}

type ResultPage = {
  job_id: string; entity_code: string; snapshot_id: string | null; offset: number; next_offset: number | null; total: number;
  counts: Record<"rows" | "CASH" | "SHORTAGE", number>; result?: OrderLogicV3Result;
  scenarios: OrderLogicV3Result["scenarios"];
};

// All source values come from the ownership- and amount-checked backend pages.
// The browser sends selection/review intent only, never trusted financial data.
export async function prepareExcelOptions(
  body: ExcelExportRequest, readJson: (path: string) => Promise<unknown>, signal: AbortSignal,
): Promise<V3ExcelOptions> {
  const selectedRows: OrderLogicV3ApiRow[] = [];
  const prepared = await scanExcelRows(body, readJson, signal, row => { selectedRows.push(row); });
  prepared.result.scenarios[body.scenario].rows = selectedRows;
  return { result: prepared.result, scenario: body.scenario, skus: body.skus, attentionSkus: body.attentionSkus,
    decisions: body.decisions, viewTitle: body.viewTitle, attentionScope: body.attentionScope,
    brandScope: body.brandScope, canViewAmountData: prepared.canViewAmountData };
}

async function scanExcelRows(
  body: ExcelExportRequest, readJson: (path: string) => Promise<unknown>, signal: AbortSignal,
  onSelected: (row: OrderLogicV3ApiRow) => void | Promise<void>,
): Promise<{ result: OrderLogicV3Result; canViewAmountData: boolean }> {
  // 발주분석 V3 엑셀은 모든 계정에 발주금액 컬럼을 노출한다(2026-09-02 사용자 요청).
  // 이 게이트는 V3 엑셀 내보내기 경로 전용이며 대시보드·크로스분석 등 다른 화면의
  // 금액 sanitize 정책에는 영향을 주지 않는다.
  await readJson("/auth/me");
  const selected = new Set([...body.skus, ...(body.attentionSkus ?? [])]);
  const seen = new Set<string>();
  let selectedCount = 0;
  let result: OrderLogicV3Result | undefined;
  let offset = 0, received = 0;
  let counts: ResultPage["counts"] | undefined;
  for (;;) {
    signal.throwIfAborted();
    const page = await readJson(`/order-logic-v3/jobs/${encodeURIComponent(body.jobId)}/result?offset=${offset}`) as ResultPage;
    const invalid = () => new ExcelExportError("화면과 서버의 분석 결과가 일치하지 않습니다. 다시 분석해 주세요.");
    if (!page || page.job_id !== body.jobId || page.entity_code !== body.entityCode || page.offset !== offset ||
      (page.snapshot_id ?? null) !== body.snapshotId || !page.counts) throw invalid();
    if (offset === 0) {
      result = page.result; counts = page.counts;
      if (!result || result.job_id !== body.jobId || result.entity_code !== body.entityCode ||
        (result.source_snapshot_id ?? null) !== body.snapshotId) throw invalid();
    }
    for (const key of ["rows", "CASH", "SHORTAGE"] as const) {
      if (!Number.isSafeInteger(page.counts[key]) || page.counts[key] < 0 || page.counts[key] !== counts?.[key]) throw invalid();
    }
    if (page.total !== Math.max(page.counts.rows, page.counts.CASH, page.counts.SHORTAGE)) throw invalid();
    const end = page.next_offset ?? page.total;
    if (!Number.isSafeInteger(end) || end < offset || end > page.total || (page.next_offset !== null && end <= offset)) throw invalid();
    const rows = page.scenarios?.[body.scenario]?.rows;
    if (!Array.isArray(rows) || rows.length !== Math.max(0, Math.min(end, page.counts[body.scenario]) - offset)) throw invalid();
    for (const row of rows) {
      if (!row || typeof row.sku_code !== "string" || seen.has(row.sku_code)) throw invalid();
      seen.add(row.sku_code);
      if (selected.has(row.sku_code)) {
        if (body.brandScope !== null && row.brand !== body.brandScope) {
          throw new ExcelExportError("선택한 브랜드와 엑셀 대상 상품이 일치하지 않습니다.");
        }
        await onSelected(row);
        selectedCount += 1;
      }
    }
    received += rows.length;
    if (page.next_offset === null) break;
    offset = end;
  }
  if (!result || received !== counts?.[body.scenario] || selectedCount !== selected.size) {
    throw new ExcelExportError("엑셀 대상 상품과 분석 결과가 일치하지 않습니다.");
  }
  return { result, canViewAmountData: true };
}

export type V3ExcelSpool = {
  directory: string;
  metadataPath: string;
  rowsPath: string;
  outputPath: string;
};

async function cleanupStaleExcelSpools() {
  const cutoff = Date.now() - 6 * 60 * 60 * 1000;
  try {
    const entries = await readdir(tmpdir(), { withFileTypes: true });
    await Promise.all(entries.filter(entry => entry.isDirectory() && entry.name.startsWith("esm-order-v3-excel-")).map(async entry => {
      const path = join(tmpdir(), entry.name);
      try { if ((await stat(path)).mtimeMs < cutoff) await rm(path, { recursive: true, force: true }); } catch { /* already removed */ }
    }));
  } catch { /* OS temporary directory cleanup is best-effort */ }
}

export async function prepareExcelSpool(
  body: ExcelExportRequest, readJson: (path: string) => Promise<unknown>, signal: AbortSignal,
): Promise<V3ExcelSpool> {
  await cleanupStaleExcelSpools();
  const directory = await mkdtemp(join(tmpdir(), "esm-order-v3-excel-"));
  const rowsPath = join(directory, "selected-rows.ndjson");
  const metadataPath = join(directory, "metadata.json");
  const outputPath = join(directory, "order-v3.xlsx");
  const sink = createWriteStream(rowsPath, { encoding: "utf8", mode: 0o600 });
  try {
    // Do not let fast validation failures remove the directory before the
    // asynchronously-created file stream has finished opening.
    await once(sink, "open");
    const prepared = await scanExcelRows(body, readJson, signal, async row => {
      signal.throwIfAborted();
      if (!sink.write(`${JSON.stringify(row)}\n`)) await once(sink, "drain");
    });
    sink.end();
    await finished(sink);
    prepared.result.scenarios[body.scenario].rows = [];
    const options: V3ExcelOptions = {
      result: prepared.result, scenario: body.scenario, skus: body.skus,
      attentionSkus: body.attentionSkus, decisions: body.decisions,
      viewTitle: body.viewTitle, attentionScope: body.attentionScope,
      brandScope: body.brandScope, canViewAmountData: prepared.canViewAmountData,
    };
    await writeFile(metadataPath, JSON.stringify({ options }), { encoding: "utf8", mode: 0o600 });
    return { directory, metadataPath, rowsPath, outputPath };
  } catch (error) {
    sink.destroy();
    await rm(directory, { recursive: true, force: true });
    throw error;
  }
}

export async function runExcelSpoolWorker(spool: V3ExcelSpool, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  const workerPath = resolve(process.cwd(), "scripts", "order-v3-excel-worker.mjs");
  const child = spawn(process.execPath, ["--experimental-strip-types", workerPath, spool.metadataPath, spool.rowsPath, spool.outputPath], {
    cwd: process.cwd(), windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
  });
  let stderr = "";
  child.stderr?.setEncoding("utf8");
  child.stderr?.on("data", chunk => { if (stderr.length < 16_384) stderr += String(chunk).slice(0, 16_384 - stderr.length); });
  const abort = () => child.kill();
  signal.addEventListener("abort", abort, { once: true });
  try {
    const code = await new Promise<number | null>((resolveExit, rejectExit) => {
      child.once("error", rejectExit);
      child.once("exit", resolveExit);
    }).catch(error => {
      signal.throwIfAborted();
      console.error("[order_v3_excel_worker] spawn_failed", JSON.stringify({ errorType: error instanceof Error ? error.name : "unknown" }));
      throw new ExcelExportError("엑셀 생성 프로세스를 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", 500);
    });
    signal.throwIfAborted();
    if (code !== 0) {
      console.error("[order_v3_excel_worker] failed", JSON.stringify({ code, stderrPresent: Boolean(stderr.trim()) }));
      throw new ExcelExportError("엑셀 파일 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.", 500);
    }
    if ((await stat(spool.outputPath)).size <= 0) throw new ExcelExportError("엑셀 파일이 비어 있습니다.", 500);
  } finally {
    signal.removeEventListener("abort", abort);
  }
}

export function openExcelSpool(spool: V3ExcelSpool) {
  return createReadStream(spool.outputPath);
}

export async function cleanupExcelSpool(spool: V3ExcelSpool | null | undefined): Promise<void> {
  if (spool) await rm(spool.directory, { recursive: true, force: true });
}

export function createExcelStream(options: V3ExcelOptions, signal: AbortSignal, onProgress?: (progress: V3ExcelProgress) => void) {
  const stream = new PassThrough({ highWaterMark: 64 * 1024 });
  // Prevent an unhandled error if cancellation occurs before the HTTP consumer attaches.
  stream.on("error", () => {});
  // Shared strings also preserve literal empty strings distinctly from null.
  const workbook = new ExcelJS.stream.xlsx.WorkbookWriter({ stream, useStyles: true, useSharedStrings: true, zip: { zlib: { level: 1 } } });
  const archive = (workbook as unknown as { zip: { abort(): void } }).zip;
  const abort = () => { archive.abort(); stream.destroy(new Error("엑셀 내보내기가 중단되었습니다.")); };
  signal.addEventListener("abort", abort, { once: true });
  const started = performance.now();
  const done = (async () => {
    try {
      signal.throwIfAborted();
      for (const progress of generateV3Excel(workbook as unknown as ExcelJS.Workbook, options)) {
        signal.throwIfAborted();
        onProgress?.(progress);
        await yieldToIO(); // let compression, HTTP and cancellation run every 250 rows
      }
      signal.throwIfAborted();
      let rejectCommit: () => void = () => {};
      const aborted = new Promise<never>((_, reject) => {
        rejectCommit = () => reject(new DOMException("엑셀 내보내기가 중단되었습니다.", "AbortError"));
        signal.addEventListener("abort", rejectCommit, { once: true });
      });
      try { await Promise.race([workbook.commit(), aborted]); }
      finally { signal.removeEventListener("abort", rejectCommit); }
      console.info("[perf][order_v3_excel]", JSON.stringify({
        proposalRows: options.skus.length, attentionRows: options.attentionSkus?.length,
        generationSeconds: Number(((performance.now() - started) / 1000).toFixed(3))
      }));
    } catch (error) {
      archive.abort(); stream.destroy(error instanceof Error ? error : new Error("엑셀 생성 실패"));
      throw error;
    } finally { signal.removeEventListener("abort", abort); }
  })();
  return { stream, done };
}
