"use client";

import { AlertCircle, CheckCircle2, Loader2, PlayCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalyzeResponse, UploadRole } from "@/types/api";
import { AnalysisProgress } from "./AnalysisProgress";
import { AnalysisResultPanel } from "./AnalysisResultPanel";
import {
  requiredUploadItems,
  roleLabels,
  uploadItems,
  type RoleAssignment,
  type UploadItem,
  type UploadMode
} from "./upload-utils";

type AnalysisStatusPanelProps = {
  mode: UploadMode;
  quickFiles: File[];
  selectedFiles: Partial<Record<UploadRole, File | null>>;
  assignedRoleCounts: Map<UploadRole, number>;
  currentUploadedCount: number;
  missingRoles: UploadRole[];
  reviewRequiredAssignments: RoleAssignment[];
  manualUploadedCount: number;
  manualMissingItems: UploadItem[];
  loading: boolean;
  submitDisabled: boolean;
  error: string;
  result: AnalyzeResponse | null;
  onSubmit: () => void;
};

export function AnalysisStatusPanel({
  mode,
  quickFiles,
  selectedFiles,
  assignedRoleCounts,
  currentUploadedCount,
  missingRoles,
  reviewRequiredAssignments,
  manualUploadedCount,
  manualMissingItems,
  loading,
  submitDisabled,
  error,
  result,
  onSubmit
}: AnalysisStatusPanelProps) {
  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>필요 파일 목록</CardTitle>
        <CardDescription>
          현재 {currentUploadedCount} / {requiredUploadItems.length}개 필수 파일 준비
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {uploadItems.map((item) => {
          const ready =
            mode === "quick" ? assignedRoleCounts.get(item.role) === 1 : Boolean(selectedFiles[item.role]);
          const duplicated = mode === "quick" && (assignedRoleCounts.get(item.role) ?? 0) > 1;
          return (
            <div key={item.role} className="flex items-center gap-3 rounded-2xl bg-slate-25 px-4 py-3">
              <CheckCircle2
                className={`h-4 w-4 ${ready ? "text-brand" : duplicated ? "text-brand" : "text-slate-300"}`}
              />
              <span className="text-sm font-medium text-slate-700">{item.label}</span>
              {item.optional ? <Badge variant="slate">선택</Badge> : null}
              {duplicated ? <Badge variant="danger">중복</Badge> : null}
            </div>
          );
        })}

        {mode === "quick" && quickFiles.length > 0 && missingRoles.length > 0 ? (
          <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            미확정: {missingRoles.map((role) => roleLabels[role]).join(", ")}
          </div>
        ) : null}

        {mode === "quick" && reviewRequiredAssignments.length > 0 ? (
          <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm leading-6 text-brand">
            <p className="font-semibold">자동 분류 확인 필요</p>
            <p className="mt-1">
              {reviewRequiredAssignments.map((assignment) => assignment.original_name).join(", ")}
            </p>
          </div>
        ) : null}

        {mode === "manual" && manualUploadedCount > 0 && manualMissingItems.length > 0 ? (
          <div className="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            미업로드: {manualMissingItems.map((item) => item.label).join(", ")}
          </div>
        ) : null}

        <AnalysisProgress loading={loading} />

        <Button className="mt-4 w-full" onClick={onSubmit} disabled={submitDisabled}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
          {loading ? "분석 중입니다" : "분석 시작"}
        </Button>

        {error ? (
          <div className="flex items-start gap-2 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-brand">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {result ? <AnalysisResultPanel result={result} /> : null}
      </CardContent>
    </Card>
  );
}
