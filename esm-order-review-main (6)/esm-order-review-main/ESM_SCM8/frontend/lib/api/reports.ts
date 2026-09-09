import { apiFetch, ApiRequestError, clientHeaders, FASTAPI_BASE_URL, parseApiError } from "./client";
import { getVerifiedUser } from "@/lib/auth";
import { sanitizeAmountData } from "@/lib/amount-permissions";

export type ReportAudience = "internal" | "partner" | "sales";
export type ReportExportFormat = "ppt" | "pdf" | "html" | "xlsx";
export type ReportBlockKind = "kpi" | "share" | "ranking" | "trend" | "matrix";
export type ReportBlockSection = "summary" | "region" | "brand" | "sku" | "cross" | "season" | "ingredient";
export type ReportBlockSize = "full" | "half";
export type ReportBlockSnapshot = {
  columns?: string[];
  rows: Array<Record<string, unknown>>;
};

export type ReportExportBlock = {
  id: string;
  title: string;
  subtitle: string;
  meta: string;
  type?: string;
  kind?: ReportBlockKind;
  section?: ReportBlockSection;
  size?: ReportBlockSize;
  params?: Record<string, unknown>;
  snapshot?: ReportBlockSnapshot | null;
  htmlSnapshot?: string | null;
};

export type ReportExportResult = {
  blob: Blob;
  fileName: string;
};

const REPORT_EXPORT_TIMEOUT_MS = 180_000;

export async function exportReportFromTemplate({
  audience,
  format,
  title,
  blocks
}: {
  audience: ReportAudience;
  format: ReportExportFormat;
  title?: string;
  blocks: ReportExportBlock[];
}): Promise<ReportExportResult> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REPORT_EXPORT_TIMEOUT_MS);
  let response: Response;
  const canExportAmountReport = getVerifiedUser()?.permissions?.canExportAmountReport === true;
  const safeBlocks = canExportAmountReport
    ? blocks
    : blocks.map((block) => ({
        ...sanitizeAmountData(block),
        htmlSnapshot: null,
        params: sanitizeAmountData({
          ...(block.params ?? {}),
          __html_snapshot: null,
          __html_snapshot_length: 0,
          __html_snapshot_status: "removed_by_amount_policy"
        })
      }));
  try {
    response = await apiFetch(`${FASTAPI_BASE_URL}/reports/export`, {
      method: "POST",
      headers: {
        ...clientHeaders(),
        "Content-Type": "application/json"
      },
      signal: controller.signal,
      body: JSON.stringify({ audience, format, title, blocks: safeBlocks })
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiRequestError(
        `보고서 생성 응답이 제한 시간(${Math.round(REPORT_EXPORT_TIMEOUT_MS / 1000)}초)을 넘었습니다. 잠시 후 다시 시도해 주세요.`,
        408
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  return {
    blob: await response.blob(),
    fileName: filenameFromDisposition(response.headers.get("content-disposition")) ?? defaultFileName(audience, format)
  };
}

function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    return decodeURIComponent(utf8Match[1]);
  }
  const asciiMatch = value.match(/filename="?([^";]+)"?/i);
  return asciiMatch?.[1] ?? null;
}

function defaultFileName(audience: ReportAudience, format: ReportExportFormat): string {
  const label = audience === "internal" ? "내부용" : audience === "partner" ? "거래처용" : "판매용";
  const extension = format === "ppt" ? "pptx" : format === "html" ? "html" : format;
  return `${label}_장바구니_보고서.${extension}`;
}
