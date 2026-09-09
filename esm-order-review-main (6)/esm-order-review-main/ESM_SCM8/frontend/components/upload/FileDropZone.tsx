"use client";

import { Loader2, Trash2, UploadCloud, Wand2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type FileDropZoneProps = {
  quickInputRef: React.MutableRefObject<HTMLInputElement | null>;
  quickFiles: File[];
  classifyLoading: boolean;
  onFilesChange: (files: FileList | null) => void;
  onApplyInputFiles: () => void;
  onRemoveFile: (index: number) => void;
  onReclassify: () => void;
};

export function FileDropZone({
  quickInputRef,
  quickFiles,
  classifyLoading,
  onFilesChange,
  onApplyInputFiles,
  onRemoveFile,
  onReclassify
}: FileDropZoneProps) {
  const handleQuickFilesDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    onFilesChange(event.dataTransfer.files);
  };

  return (
    <>
      <div
        className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-red-100 bg-red-50/40 px-6 py-10 text-center hover:bg-red-50"
        onDragOver={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onDrop={handleQuickFilesDrop}
      >
        <UploadCloud className="h-8 w-8 text-brand" />
        <span className="mt-3 text-sm font-bold text-ink">엑셀 파일 여러 개 선택</span>
        <span className="mt-1 text-xs text-slate-500">.xls, .xlsx, .xlsm 파일을 6개 이상 선택할 수 있습니다.</span>
        <input
          type="file"
          multiple
          accept=".xls,.xlsx,.xlsm"
          ref={quickInputRef}
          className="mt-4 block w-full max-w-md cursor-pointer rounded-2xl border border-line bg-white text-sm file:mr-4 file:border-0 file:bg-black file:px-4 file:py-3 file:font-semibold file:text-white"
          onChange={(event) => {
            onFilesChange(event.target.files);
          }}
          onInput={(event) => {
            onFilesChange(event.currentTarget.files);
          }}
        />
        <Button type="button" variant="secondary" size="sm" className="mt-3" onClick={onApplyInputFiles}>
          선택 파일 반영
        </Button>
      </div>

      {quickFiles.length > 0 ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="default">{quickFiles.length}개 파일 선택</Badge>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={onReclassify}
              disabled={classifyLoading}
            >
              {classifyLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              자동 분류 다시 실행
            </Button>
          </div>
          {classifyLoading ? (
            <div className="flex items-center gap-3 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-brand">
              <Loader2 className="h-5 w-5 animate-spin" />
              <div>
                <p className="font-semibold">파일을 분류중입니다</p>
                <p className="text-xs text-brand">파일명과 컬럼 정보를 확인해 각 파일 종류를 자동 추천하고 있습니다.</p>
              </div>
            </div>
          ) : null}
          <div className="grid gap-2 rounded-2xl border border-line bg-white p-3 text-sm text-slate-700 md:grid-cols-2">
            {quickFiles.map((file, index) => (
              <div
                key={`${file.name}-${file.size}-${file.lastModified}`}
                className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-slate-100 px-3 py-2"
              >
                <span className="truncate">{file.name}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 shrink-0 p-0 text-slate-500 hover:text-brand"
                  onClick={() => onRemoveFile(index)}
                  aria-label={`${file.name} 삭제`}
                  title="파일 삭제"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
