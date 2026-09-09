import { MAX_UPLOAD_FILE_BYTES, MAX_UPLOAD_FILES, MAX_UPLOAD_TOTAL_BYTES } from "@/lib/api";
import type { ClassificationItem, UploadRole } from "@/types/api";

export type UploadMode = "quick" | "manual";

export type UploadItem = {
  role: UploadRole;
  label: string;
  description: string;
  optional?: boolean;
};

export type RoleAssignment = ClassificationItem & {
  file: File;
  role: UploadRole | "";
  confirmed?: boolean;
};

export const uploadItems: UploadItem[] = [
  {
    role: "eu_stock",
    label: "EU 현지 재고",
    description: "유럽 현지 창고의 현재 재고, 단가, 판매 가능 수량 파일"
  },
  {
    role: "hq_eu_stock",
    label: "본사 EU 창고 재고",
    description: "본사 또는 실리콘투 EU 창고 기준 재고 파일"
  },
  {
    role: "sales_detail",
    label: "유럽 판매내역상세",
    description: "EU 현지 B2B 판매내역상세 및 수요 산정 기준 파일"
  },
  {
    role: "hq_to_eu_sales_detail",
    label: "본사->EU 판매/출고내역",
    description: "본사에서 유럽 법인으로 출고한 판매/출고내역 파일"
  },
  {
    role: "shipping",
    label: "해상컨테이너 상세내역",
    description: "해상, 항공, 철송, 트럭 등 이동 중 상세내역 파일"
  },
  {
    role: "inbound",
    label: "미입고현황",
    description: "발주 후 아직 입고되지 않은 미입고현황 파일"
  }
];

export const requiredUploadItems = uploadItems.filter((item) => !item.optional);

export const roleLabels = Object.fromEntries(uploadItems.map((item) => [item.role, item.label])) as Record<
  UploadRole,
  string
>;

const localFilenameHints: Partial<Record<UploadRole, string[]>> = {
  eu_stock: ["eu현지재고", "현지재고", "eu_stock", "localstock"],
  hq_eu_stock: ["본사eu창고재고", "본사재고", "창고재고", "hq_eu_stock", "hqstock"],
  sales_detail: ["eu현지판매내역상세", "판매내역상세", "판매상세", "sales_detail"],
  hq_to_eu_sales_detail: ["본사eu출고내역", "본사eu", "본사->eu", "본사출고", "hq_to_eu"],
  shipping: ["해상컨테이너상세내역", "컨테이너상세", "해상", "shipping", "shipment"],
  inbound: ["미입고현황", "미입고", "openpo", "open_po"]
};


function normalizeFilename(value: string) {
  return value.toLowerCase().replace(/[\s._()[\]\\/\\-]+/g, "");
}

export function localFilenameRole(file: File): UploadRole | "" {
  const normalized = normalizeFilename(file.name);
  const scored = uploadItems
    .map((item) => ({
      role: item.role,
      score: (localFilenameHints[item.role] ?? []).some((hint) => normalized.includes(normalizeFilename(hint))) ? 1 : 0
    }))
    .filter((item) => item.score > 0);
  return scored.length === 1 ? scored[0].role : "";
}

export function localFilenameAssignments(files: File[]): RoleAssignment[] {
  return files.map((file, index) => {
    const role = localFilenameRole(file);
    return {
      index,
      original_name: file.name,
      suggested_role: role,
      suggested_key: role === "inbound" ? "open_po" : role,
      score: role ? 999 : null,
      confidence: role ? "high" : "low",
      rows: 0,
      columns: 0,
      detected_columns: [],
      matched_required_columns: [],
      missing_required_columns: [],
      evidence: role ? ["파일명 힌트가 이 파일 종류와 일치합니다."] : [],
      candidates: role
        ? [
            {
              role,
              key: role === "inbound" ? "open_po" : role,
              score: 999,
              rows: 0,
              columns: 0,
              detected_columns: [],
              matched_required_columns: [],
              missing_required_columns: [],
              assigned: true
            }
          ]
        : [],
      error: null,
      file,
      role,
      confirmed: false
    };
  });
}

export function pendingFileAssignments(files: File[]): RoleAssignment[] {
  return files.map((file, index) => ({
    index,
    original_name: file.name,
    suggested_role: "",
    suggested_key: "",
    score: null,
    confidence: "low",
    rows: 0,
    columns: 0,
    detected_columns: [],
    matched_required_columns: [],
    missing_required_columns: [],
    evidence: [],
    candidates: [],
    error: null,
    file,
    role: "",
    confirmed: false
  }));
}

export function fileListSignature(files: File[]) {
  return files.map((file) => `${file.name}:${file.size}:${file.lastModified}`).join("|");
}

export function fileListFromFiles(files: File[]) {
  const transfer = new DataTransfer();
  files.forEach((file) => transfer.items.add(file));
  return transfer.files;
}

export function parseNumberInput(value: string, label: string, allowZero = false): number {
  const number = Number(value);
  const validRange = allowZero ? number >= 0 : number > 0;
  if (!Number.isFinite(number) || !validRange) {
    throw new Error(`${label}은 숫자로 입력해 주세요.`);
  }
  return number;
}

export function parseIntegerInput(value: string, label: string): number {
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) {
    throw new Error(`${label}은 1 이상의 정수로 입력해 주세요.`);
  }
  return number;
}

export function confidenceText(confidence: ClassificationItem["confidence"]) {
  if (confidence === "high") return "높음";
  if (confidence === "medium") return "보통";
  return "확인 필요";
}

export function confidenceVariant(confidence: ClassificationItem["confidence"]) {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "default";
  return "danger";
}

export function formatExchangeRate(rate: number | undefined) {
  if (typeof rate !== "number" || !Number.isFinite(rate)) {
    return "-";
  }
  return rate.toLocaleString("ko-KR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatFileSize(bytes: number) {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)}KB`;
  }
  return `${bytes}B`;
}

export function validateUploadSizes(files: File[]) {
  if (files.length > MAX_UPLOAD_FILES) {
    return `한 번에 업로드할 수 있는 파일은 최대 ${MAX_UPLOAD_FILES}개입니다.`;
  }
  const oversized = files.find((file) => file.size > MAX_UPLOAD_FILE_BYTES);
  if (oversized) {
    return `파일 1개 최대 용량은 ${formatFileSize(MAX_UPLOAD_FILE_BYTES)}입니다. ${oversized.name} 파일은 ${formatFileSize(oversized.size)}입니다.`;
  }
  const totalSize = files.reduce((total, file) => total + file.size, 0);
  if (totalSize > MAX_UPLOAD_TOTAL_BYTES) {
    return `전체 업로드 최대 용량은 ${formatFileSize(MAX_UPLOAD_TOTAL_BYTES)}입니다. 현재 선택한 파일 합계는 ${formatFileSize(totalSize)}입니다.`;
  }
  return "";
}

export function exchangeRateSourceText(source: string | undefined) {
  if (source === "api") return "자동 조회";
  if (source === "default") return "기본값 적용";
  if (source === "manual") return "수동 입력";
  return source || "확인 중";
}

export function numberInputValue(value: string) {
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMonthValue(value: number | null) {
  if (value === null) {
    return "-";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, "");
}

export function roleReviewRequired(assignment: RoleAssignment) {
  if (!assignment.role) {
    return false;
  }
  if (!assignmentHasVerificationData(assignment)) {
    return true;
  }
  if (assignment.role !== assignment.suggested_role) {
    return true;
  }
  return assignment.confidence !== "high" || (assignment.missing_required_columns?.length ?? 0) > 0;
}

export function assignmentHasVerificationData(assignment: RoleAssignment) {
  return assignment.score !== null && assignment.rows > 0 && assignment.columns > 0;
}

function confidenceForSelectedCandidate(candidate: RoleAssignment["candidates"][number]): ClassificationItem["confidence"] {
  const missingCount = candidate.missing_required_columns?.length ?? 0;
  if (missingCount === 0 && candidate.score >= 200) {
    return "high";
  }
  if (missingCount <= 1 && candidate.score >= 120) {
    return "medium";
  }
  return "low";
}

export function assignmentWithSelectedRole(assignment: RoleAssignment, role: UploadRole | ""): RoleAssignment {
  if (!role) {
    return {
      ...assignment,
      role,
      confirmed: false
    };
  }

  const selectedCandidate = assignment.candidates.find((candidate) => candidate.role === role);
  if (!selectedCandidate) {
    return {
      ...assignment,
      role,
      confidence: "low",
      score: null,
      rows: 0,
      columns: 0,
      detected_columns: [],
      matched_required_columns: [],
      missing_required_columns: [],
      confirmed: false
    };
  }

  return {
    ...assignment,
    role,
    suggested_key: selectedCandidate.key,
    score: selectedCandidate.score,
    confidence: confidenceForSelectedCandidate(selectedCandidate),
    rows: selectedCandidate.rows,
    columns: selectedCandidate.columns,
    detected_columns: selectedCandidate.detected_columns,
    matched_required_columns: selectedCandidate.matched_required_columns,
    missing_required_columns: selectedCandidate.missing_required_columns,
    confirmed: false
  };
}

export function joinPreview(values: string[] | undefined, empty = "-") {
  if (!values || values.length === 0) {
    return empty;
  }
  return values.slice(0, 8).join(", ");
}
