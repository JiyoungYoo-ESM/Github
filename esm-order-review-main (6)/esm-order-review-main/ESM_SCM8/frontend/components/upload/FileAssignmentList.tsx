"use client";

import { Loader2, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { UploadRole } from "@/types/api";
import {
  assignmentHasVerificationData,
  confidenceText,
  confidenceVariant,
  joinPreview,
  roleLabels,
  roleReviewRequired,
  uploadItems,
  type RoleAssignment
} from "./upload-utils";

type FileAssignmentListProps = {
  assignments: RoleAssignment[];
  onAssignmentChange: (index: number, role: UploadRole | "") => void;
  onConfirmAssignment: (index: number) => void;
  onRemoveFile: (index: number) => void;
};

export function FileAssignmentList({
  assignments,
  onAssignmentChange,
  onConfirmAssignment,
  onRemoveFile
}: FileAssignmentListProps) {
  if (assignments.length === 0) {
    return null;
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="bg-slate-25 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">파일명</th>
            <th className="px-4 py-3">파일 종류</th>
            <th className="px-4 py-3">분류 상태</th>
            <th className="px-4 py-3">상세</th>
            <th className="px-4 py-3">확인</th>
            <th className="px-4 py-3">삭제</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-white">
          {assignments.map((assignment) => {
            const needsReview = roleReviewRequired(assignment);
            const selectedRoleLabel = assignment.role ? roleLabels[assignment.role] : "분석 제외";
            const hasVerificationData = assignmentHasVerificationData(assignment);
            const confidenceLabel = !hasVerificationData
              ? "검증 대기"
              : assignment.confirmed
                ? "사용자 확인"
                : confidenceText(assignment.confidence);
            const confidenceBadgeVariant = !hasVerificationData
              ? "default"
              : assignment.confirmed
                ? "success"
                : confidenceVariant(assignment.confidence);
            return (
              <tr key={`${assignment.index}-${assignment.original_name}`}>
                <td className="max-w-[240px] px-4 py-3 font-medium text-ink">
                  <p className="truncate">{assignment.original_name}</p>
                  {assignment.error ? (
                    <p className="mt-1 text-xs text-brand">{assignment.error}</p>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <select
                    value={assignment.role}
                    onChange={(event) =>
                      onAssignmentChange(assignment.index, event.target.value as UploadRole | "")
                    }
                    className="h-10 min-w-[210px] rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none focus:border-brand"
                  >
                    <option value="">분석 제외</option>
                    {uploadItems.map((item) => (
                      <option key={item.role} value={item.role}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  {assignment.suggested_role ? (
                    <p className="mt-1 text-xs text-slate-500">
                      추천: {roleLabels[assignment.suggested_role as UploadRole] ?? assignment.suggested_role}
                    </p>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {!hasVerificationData && assignment.role ? (
                      <Loader2 className="h-4 w-4 animate-spin text-brand" />
                    ) : null}
                    <Badge variant={confidenceBadgeVariant}>{confidenceLabel}</Badge>
                  </div>
                </td>
                <td className="min-w-[280px] px-4 py-3 text-xs leading-5 text-slate-600">
                  {hasVerificationData ? (
                    <details>
                      <summary className="cursor-pointer font-semibold text-slate-700">검증 상세 보기</summary>
                      <div className="mt-2 space-y-1">
                        <p>
                          <span className="font-semibold text-slate-800">확신 점수</span>:{" "}
                          {assignment.score ?? "-"}
                        </p>
                        <p>
                          <span className="font-semibold text-slate-800">행/열</span>:{" "}
                          {assignment.rows.toLocaleString()} / {assignment.columns.toLocaleString()}
                        </p>
                        <p>
                          <span className="font-semibold text-slate-800">감지 컬럼</span>:{" "}
                          {joinPreview(assignment.detected_columns, "분류 후 표시")}
                        </p>
                        <p>
                          <span className="font-semibold text-slate-800">필수 매칭</span>:{" "}
                          {joinPreview(assignment.matched_required_columns)}
                        </p>
                        {(assignment.missing_required_columns?.length ?? 0) > 0 ? (
                          <p className="text-amber-700">
                            <span className="font-semibold">미감지</span>:{" "}
                            {joinPreview(assignment.missing_required_columns)}
                          </p>
                        ) : null}
                        {assignment.evidence?.length ? (
                          <p className="text-slate-500">{assignment.evidence.slice(0, 2).join(" / ")}</p>
                        ) : null}
                        {assignment.candidates.length > 1 ? (
                          <p className="text-slate-500">
                            다른 후보:{" "}
                            {assignment.candidates
                              .slice(1, 4)
                              .map((candidate) => `${roleLabels[candidate.role] ?? candidate.role}(${candidate.score})`)
                              .join(", ")}
                          </p>
                        ) : null}
                      </div>
                    </details>
                  ) : (
                    <span className="text-slate-500">분류가 끝나면 표시됩니다.</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {!hasVerificationData && assignment.role ? (
                    <Badge variant="default">분류 대기</Badge>
                  ) : needsReview ? (
                    assignment.confirmed ? (
                      <Badge variant="success">확인됨</Badge>
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => onConfirmAssignment(assignment.index)}
                      >
                        {selectedRoleLabel} 확인
                      </Button>
                    )
                  ) : (
                    <Badge variant="success">자동 확인</Badge>
                  )}
                </td>
                <td className="px-4 py-3">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 text-slate-500 hover:text-brand"
                    onClick={() => onRemoveFile(assignment.index)}
                    aria-label={`${assignment.original_name} 삭제`}
                    title="파일 삭제"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
