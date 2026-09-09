"use client";

import { FileSpreadsheet } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { UploadRole } from "@/types/api";
import { uploadItems } from "./upload-utils";

type ManualUploadCardProps = {
  selectedFiles: Partial<Record<UploadRole, File | null>>;
  onFileChange: (role: UploadRole, file: File | null) => void;
};

export function ManualUploadCard({ selectedFiles, onFileChange }: ManualUploadCardProps) {
  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>정확 업로드</CardTitle>
        <CardDescription>
          파일 역할을 직접 지정합니다. 자동 분류가 애매한 경우 이 방식을 사용하세요.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        {uploadItems.map((item) => (
          <label key={item.role} className="rounded-2xl border border-line bg-slate-25 p-5 shadow-sm">
            <div className="flex items-start gap-4">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-brand">
                <FileSpreadsheet className="h-5 w-5" />
              </span>
              <div>
                <p className="font-bold text-ink">
                  {item.label}
                  {item.optional ? <span className="ml-2 text-xs font-semibold text-slate-400">(선택)</span> : null}
                </p>
                <p className="mt-1 text-sm leading-6 text-slate-500">{item.description}</p>
              </div>
            </div>
            <input
              type="file"
              accept=".xls,.xlsx,.xlsm"
              className="mt-5 block w-full cursor-pointer rounded-2xl border border-line bg-white text-sm file:mr-4 file:border-0 file:bg-black file:px-4 file:py-3 file:font-semibold file:text-white"
              onChange={(event) => onFileChange(item.role, event.target.files?.[0] ?? null)}
            />
            {selectedFiles[item.role] ? (
              <p className="mt-3 truncate text-sm font-semibold text-brand">
                {selectedFiles[item.role]?.name}
              </p>
            ) : null}
          </label>
        ))}
      </CardContent>
    </Card>
  );
}
