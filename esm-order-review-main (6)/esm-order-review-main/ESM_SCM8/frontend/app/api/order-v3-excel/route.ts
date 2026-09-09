import { Readable } from "node:stream";
import { resolveServerApiBase } from "../../../lib/api/base-url.ts";
import {
  cleanupExcelSpool, ExcelExportError, openExcelSpool, prepareExcelSpool,
  runExcelSpoolWorker, type V3ExcelSpool, validateExportRequest,
} from "../../../lib/server/order-v3-excel.ts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;
let activeExport: symbol | null = null;

function firstForwardedValue(value: string | null): string | null {
  return value?.split(",", 1)[0]?.trim() || null;
}

function requestOriginIsAllowed(request: Request): boolean {
  if (request.headers.get("x-requested-with") !== "fetch") return false;
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  const origin = request.headers.get("origin");
  if (!origin) return true;
  let suppliedOrigin: string;
  try {
    suppliedOrigin = new URL(origin).origin;
  } catch {
    return false;
  }
  const requestUrl = new URL(request.url);
  const forwardedHost = firstForwardedValue(request.headers.get("x-forwarded-host"));
  const forwardedProto = firstForwardedValue(request.headers.get("x-forwarded-proto"));
  const host = firstForwardedValue(request.headers.get("host"));
  const candidates = new Set([requestUrl.origin]);
  for (const candidateHost of [forwardedHost, host]) {
    if (!candidateHost) continue;
    for (const protocol of new Set([forwardedProto, requestUrl.protocol.replace(":", "")])) {
      if (!protocol || !["http", "https"].includes(protocol)) continue;
      try { candidates.add(new URL(`${protocol}://${candidateHost}`).origin); } catch { /* invalid proxy host */ }
    }
  }
  return candidates.has(suppliedOrigin);
}

export async function POST(request: Request) {
  // Native same-origin route: no long-running backend rewrite or browser workbook.
  // Next/Railway can expose an internal request URL (localhost/private host)
  // while the browser correctly sends the public/LAN Origin. Compare against
  // Host and trusted proxy-facing host/proto candidates as well as request.url.
  if (!requestOriginIsAllowed(request)) {
    return Response.json({ detail: "허용되지 않은 요청입니다." }, { status: 403 });
  }
  if (activeExport) return Response.json({ detail: "다른 엑셀 파일을 생성하고 있습니다. 완료 후 다시 시도해 주세요." }, { status: 429 });
  const exportTicket = Symbol("order-v3-export");
  const controller = new AbortController();
  const abort = () => controller.abort();
  request.signal.addEventListener("abort", abort, { once: true });
  if (request.signal.aborted) abort();
  const release = () => {
    if (activeExport === exportTicket) activeExport = null;
    request.signal.removeEventListener("abort", abort);
  };
  let spool: V3ExcelSpool | null = null;
  try {
    const reader = request.body?.getReader();
    if (!reader) throw new ExcelExportError("엑셀 요청이 비어 있습니다.", 422);
    const chunks: Uint8Array[] = []; let size = 0;
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > 8 * 1024 * 1024) { await reader.cancel(); throw new ExcelExportError("엑셀 선택 요청이 너무 큽니다.", 413); }
      chunks.push(value);
    }
    const body = validateExportRequest(JSON.parse(Buffer.concat(chunks).toString("utf8")));
    if (body.entityCode !== request.headers.get("x-entity-code")) throw new ExcelExportError("선택한 법인이 일치하지 않습니다.", 403);
    const headers = new Headers();
    for (const key of ["cookie", "authorization", "x-client-id", "x-entity-code"]) {
      const value = request.headers.get(key); if (value) headers.set(key, value);
    }
    const base = resolveServerApiBase(process.env.FASTAPI_INTERNAL_BASE_URL);
    const readJson = async (path: string) => {
      const response = await fetch(`${base}${path}`, { headers, cache: "no-store",
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]) });
      if (!response.ok) {
        let message = "분석 결과를 받지 못했습니다. 잠시 후 엑셀 내보내기를 다시 시도해 주세요.";
        const error = await response.json().catch(() => null);
        if (typeof error?.error?.message === "string") message = error.error.message;
        else if (typeof error?.detail === "string") message = error.detail;
        throw new ExcelExportError(message, response.status);
      }
      return response.json();
    };
    // Reserve the memory-intensive slot only after authentication; an unfinished
    // unauthenticated upload must not block every user's exports.
    const auth = await readJson("/auth/me");
    if (activeExport) throw new ExcelExportError("다른 엑셀 파일을 생성하고 있습니다. 완료 후 다시 시도해 주세요.", 429);
    activeExport = exportTicket;
    spool = await prepareExcelSpool(body, path => path === "/auth/me" ? Promise.resolve(auth) : readJson(path), controller.signal);
    await runExcelSpoolWorker(spool, controller.signal);
    const stream = openExcelSpool(spool);
    const activeSpool = spool;
    let finalized = false;
    const finalize = () => {
      if (finalized) return;
      finalized = true;
      release();
      void cleanupExcelSpool(activeSpool);
    };
    const stopStream = () => stream.destroy(new Error("엑셀 다운로드가 중단되었습니다."));
    controller.signal.addEventListener("abort", stopStream, { once: true });
    stream.on("close", () => {
      controller.signal.removeEventListener("abort", stopStream);
      finalize();
    });
    return new Response(Readable.toWeb(stream) as ReadableStream<Uint8Array>, { headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": 'attachment; filename="order-v3.xlsx"', "Cache-Control": "no-store"
    } });
  } catch (error) {
    controller.abort(); release();
    await cleanupExcelSpool(spool);
    return Response.json({ detail: error instanceof Error ? error.message : "엑셀 생성 실패" },
      { status: error instanceof ExcelExportError ? error.status : error instanceof SyntaxError ? 422 : 500 });
  }
}
