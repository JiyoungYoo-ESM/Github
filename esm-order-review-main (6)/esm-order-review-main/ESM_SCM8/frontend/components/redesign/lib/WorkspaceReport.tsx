"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Check, Download, ShoppingBag, X } from "lucide-react";
import { exportReportFromTemplate, type ReportAudience, type ReportExportFormat } from "@/lib/api";
import { sanitizeAmountData } from "@/lib/amount-permissions";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { cn } from "@/lib/utils";
import { captureReportCardHtmlSnapshot } from "./report-card-snapshot";
import { compactReportExportId, MAX_REPORT_BLOCKS } from "./workspace-format";
import type { ReportBlock, ReportBlockSection } from "./types";

export type ReportDrawerStep = 1 | 2 | 3 | 4;

const reportDownloadFormats: Array<{ title: string; desc: string; format: Extract<ReportExportFormat, "ppt" | "html"> }> = [
  {
    title: "PPT",
    desc: "슬라이드 편집용",
    format: "ppt"
  },
  {
    title: "HTML",
    desc: "열람용",
    format: "html"
  }
] as const;

const reportAudienceOptions: Array<{
  audience: ReportAudience;
  title: string;
  badge: string;
  desc: string;
  disabled?: boolean;
}> = [
  {
    audience: "internal",
    title: "내부용",
    badge: "전체",
    desc: "원가·마진·타사 데이터 포함"
  },
  {
    audience: "partner",
    title: "거래처용",
    badge: "마스킹",
    desc: "경쟁사 익명화 · 원가 제거",
    disabled: true
  },
  {
    audience: "sales",
    title: "판매용",
    badge: "공개용",
    desc: "거래처 식별 제거 · 경쟁사 익명화",
    disabled: true
  }
];

const reportSectionLabels: Record<ReportBlockSection, string> = {
  summary: "요약",
  region: "국가·권역",
  brand: "브랜드",
  sku: "SKU",
  cross: "교차분석",
  season: "시즌 캘린더",
  ingredient: "성분 분석"
};

function getReportSectionLabel(section?: ReportBlockSection) {
  return section ? reportSectionLabels[section] : reportSectionLabels.summary;
}

function getReportAudiencePreviewNote(audience: ReportAudience) {
  if (audience === "partner") return "거래처용: 필요한 항목만 선별해 생성됩니다.";
  if (audience === "sales") return "판매용: 식별 정보 없이 집계 중심으로 생성됩니다.";
  return "내부용: 실명과 원본 지표 기준으로 PPT/HTML이 생성됩니다.";
}

function ReportStepperDots({ step }: { step: ReportDrawerStep }) {
  return (
    <div className="mt-[14px] grid grid-cols-[18px_1fr_18px_1fr_18px_1fr_18px] items-center">
      {[1, 2, 3, 4].map((item, index) => (
        <div key={item} className="contents">
          <div
            className={cn(
              "grid h-[18px] w-[18px] place-items-center rounded-full text-[11px] font-black",
              item < step ? "bg-pos text-white" : item === step ? "bg-brand text-white" : "border border-border bg-surface text-muted2"
            )}
          >
            {item < step ? <Check className="h-3 w-3" /> : item}
          </div>
          {index < 3 ? <div className={cn("h-px", item < step ? "bg-pos" : "bg-border")} /> : null}
        </div>
      ))}
    </div>
  );
}

export function ReportDrawer({
  open,
  step,
  blocks,
  onRemoveBlock,
  onReorderBlock,
  onStep,
  onClose
}: {
  open: boolean;
  step: ReportDrawerStep;
  blocks: ReportBlock[];
  onRemoveBlock: (id: string) => void;
  onReorderBlock: (draggedId: string, targetId: string) => void;
  onStep: (step: ReportDrawerStep) => void;
  onClose: () => void;
}) {
  const permissions = useUserPermissions();
  const [draggingBlockId, setDraggingBlockId] = useState<string | null>(null);
  const [selectedAudience, setSelectedAudience] = useState<ReportAudience>("internal");
  const [exportingReport, setExportingReport] = useState<Extract<ReportExportFormat, "ppt" | "html"> | null>(null);
  const [exportReportError, setExportReportError] = useState<string | null>(null);
  const draggingBlockIdRef = useRef<string | null>(null);
  const selectedAudienceOption = reportAudienceOptions.find((option) => option.audience === selectedAudience) ?? reportAudienceOptions[0];
  const selectedAudiencePreviewNote = getReportAudiencePreviewNote(selectedAudience);
  const safeBlocks = useMemo(
    () => permissions.canViewAmountData
      ? blocks
      : blocks.map((block) => ({ ...sanitizeAmountData(block), htmlSnapshot: null })),
    [blocks, permissions.canViewAmountData]
  );
  const previewBlocks = safeBlocks.slice(0, 6);
  const previewSectionLabels = Array.from(new Set(safeBlocks.map((block) => getReportSectionLabel(block.section))));
  const previewSectionText = previewSectionLabels.length > 0 ? previewSectionLabels.join(" · ") : "-";

  const reportExportBlocks = useMemo(
    () =>
      safeBlocks.map((block, index) => {
        const htmlSnapshot = permissions.canExportAmountReport
          ? block.htmlSnapshot ?? captureReportCardHtmlSnapshot(block) ?? null
          : null;
        return {
          id: compactReportExportId(block.id, index),
          title: block.title,
          subtitle: block.subtitle,
          meta: block.meta,
          type: block.type ?? "summary",
          kind: block.kind,
          section: block.section,
          size: block.size,
          params: {
            ...(block.params ?? {}),
            __html_snapshot_status: htmlSnapshot ? "captured" : "missing",
            __html_snapshot_length: htmlSnapshot ? htmlSnapshot.length : 0,
            __html_snapshot: htmlSnapshot ?? ""
          },
          snapshot: block.snapshot ?? null,
          htmlSnapshot
        };
      }),
    [permissions.canExportAmountReport, safeBlocks]
  );

  const handlePrepareReport = useCallback(() => {
    if (safeBlocks.length === 0) {
      setExportReportError("보고서에 담긴 블록이 없습니다. 분석 화면에서 먼저 + 담기를 눌러주세요.");
      return;
    }
    setExportReportError(null);
    onStep(4);
  }, [onStep, safeBlocks.length]);

  const handleDownloadReport = useCallback(async (format: Extract<ReportExportFormat, "ppt" | "html">) => {
    if (exportingReport) return;
    if (safeBlocks.length === 0) {
      setExportReportError("보고서에 담긴 블록이 없습니다. 분석 화면에서 먼저 + 담기를 눌러주세요.");
      return;
    }
    setExportingReport(format);
    setExportReportError(null);
    try {
      const result = await exportReportFromTemplate({
        audience: selectedAudience,
        format,
        title: "ESM 데이터 분석 리포트",
        blocks: reportExportBlocks
      });
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportReportError(error instanceof Error ? error.message : "보고서 생성에 실패했습니다.");
    } finally {
      setExportingReport(null);
    }
  }, [exportingReport, reportExportBlocks, safeBlocks.length, selectedAudience]);

  if (!open) return null;

  return (
    <aside className="fixed right-0 top-0 z-50 flex h-screen w-[min(520px,calc(100vw-24px))] flex-col overflow-hidden border-l border-border bg-surface shadow-soft">
      <div className="shrink-0 px-[28px] pt-[24px]">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-[10px]">
            <div className="grid h-[28px] w-[28px] place-items-center rounded-[8px] border border-brand/20 bg-brand-50 text-brand">
              <ShoppingBag className="h-4 w-4" />
            </div>
            <div>
              <p className="text-[10px] font-black uppercase tracking-[.12em] text-muted2">REPORT BUILDER</p>
              <h2 className="text-[15px] font-black leading-none text-ink">보고서 장바구니</h2>
            </div>
          </div>
          <button type="button" onClick={onClose} className="grid h-8 w-8 place-items-center rounded-[8px] text-muted2">
            <X className="h-5 w-5" />
          </button>
        </div>
        <ReportStepperDots step={step} />
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-[28px] pt-[20px]">
        {exportReportError ? (
          <p className="mb-3 shrink-0 rounded-[8px] border border-brand/20 bg-brand-50 px-3 py-2 text-[12px] font-bold text-brand">
            {exportReportError}
          </p>
        ) : null}
        {step === 1 ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="shrink-0 flex items-center justify-between text-[12px] font-semibold text-muted2">
              <span>{safeBlocks.length}개 블록 · 위→아래가 보고서 순서</span>
              <span>↕ 드래그</span>
            </div>
            {safeBlocks.length > 0 ? (
              <div className="mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain pb-4 pr-1 [scrollbar-gutter:stable]">
                <div className="grid gap-3">
                {safeBlocks.map((block, index) => (
                  <div
                    key={block.id}
                    draggable
                    onDragStart={(event) => {
                      draggingBlockIdRef.current = block.id;
                      setDraggingBlockId(block.id);
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", block.id);
                    }}
                    onDragOver={(event) => {
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                    }}
                    onDragEnter={(event) => {
                      event.preventDefault();
                      const draggedId = draggingBlockIdRef.current ?? draggingBlockId ?? event.dataTransfer.getData("text/plain");
                      if (draggedId && draggedId !== block.id) {
                        onReorderBlock(draggedId, block.id);
                      }
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      const draggedId = draggingBlockIdRef.current ?? draggingBlockId ?? event.dataTransfer.getData("text/plain");
                      if (draggedId && draggedId !== block.id) {
                        onReorderBlock(draggedId, block.id);
                      }
                      draggingBlockIdRef.current = null;
                      setDraggingBlockId(null);
                    }}
                    onDragEnd={() => {
                      draggingBlockIdRef.current = null;
                      setDraggingBlockId(null);
                    }}
                    className={cn(
                      "select-none cursor-grab rounded-[12px] border border-border bg-surface px-4 py-3 shadow-soft transition active:cursor-grabbing",
                      draggingBlockId === block.id && "opacity-50"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] bg-brand-50 text-[12px] font-black text-brand">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-black text-ink">{block.title}</p>
                        <p className="mt-1 text-[12px] font-semibold text-muted2">{block.subtitle}</p>
                        <p className="mt-2 text-[11px] font-black text-brand">{block.meta}</p>
                      </div>
                      <button
                        type="button"
                        aria-label={`${block.title} 보고서 장바구니에서 제거`}
                        title="보고서 장바구니에서 제거"
                        onClick={() => onRemoveBlock(block.id)}
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] text-muted2 transition hover:bg-row hover:text-ink"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
                </div>
              </div>
            ) : null}
            {safeBlocks.length === 0 ? <div className="grid flex-1 place-items-center pb-[120px] text-center">
              <div>
                <div className="mx-auto grid h-[48px] w-[48px] place-items-center rounded-[14px] bg-row text-[24px]">
                  <ShoppingBag className="h-7 w-7 text-muted2" />
                </div>
                <p className="mt-[18px] text-[15px] font-black text-ink">아직 담은 블록이 없습니다</p>
                <p className="mx-auto mt-[12px] max-w-[320px] text-[13px] font-semibold leading-5 text-muted2">
                  국가·브랜드·SKU 탭에서 + 담기 버튼을 눌러 인사이트 블록을 모아주세요
                </p>
              </div>
            </div> : null}
          </div>
        ) : null}

        {step === 2 ? (
          <div className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1 [scrollbar-gutter:stable]">
            <h3 className="text-[15px] font-black text-ink">누구에게 보낼 보고서인가요?</h3>
            <p className="mt-[5px] text-[12px] font-semibold text-muted2">보고 대상에 맞게 표시 항목이 구성됩니다.</p>
            <div className="mt-[12px] grid gap-[10px]">
              {reportAudienceOptions.map(({ audience, title, badge, desc, disabled }) => (
                <button
                  key={title}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    setSelectedAudience(audience);
                    onStep(3);
                  }}
                  className={cn(
                    "rounded-[10px] border px-[12px] py-[12px] text-left transition",
                    disabled
                      ? "cursor-not-allowed border-border bg-row/70 opacity-60"
                      : selectedAudience === audience
                        ? "border-brand/40 bg-brand-50/30 shadow-soft"
                        : "border-border bg-surface shadow-soft hover:border-brand/30"
                  )}
                >
                  <p className={cn("text-[13px] font-black", disabled ? "text-muted2" : "text-ink")}>
                    {title}{" "}
                    <span
                      className={cn(
                        "ml-1 rounded-full px-2 py-[2px] text-[10px]",
                        disabled ? "bg-surface text-muted2" : selectedAudience === audience ? "bg-brand-50 text-brand" : "bg-row text-muted2"
                      )}
                    >
                      {badge}
                    </span>
                  </p>
                  <p className="mt-[6px] text-[12px] font-semibold text-muted2">{desc}</p>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1 [scrollbar-gutter:stable]">
            <h3 className="text-[15px] font-black text-ink">생성 전 확인</h3>
            <p className="mt-[5px] text-[12px] font-semibold text-muted2">선택한 용도와 장바구니 순서대로 보고서가 생성됩니다.</p>
            <div className="mt-[12px] rounded-[12px] border border-border bg-surface p-[14px] shadow-soft">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-black tracking-[.12em] text-brand">SILICON2 · REPORT CART</p>
                  <h3 className="mt-[4px] text-[14px] font-black leading-tight text-ink">보고서 장바구니 미리보기</h3>
                </div>
                <span className="shrink-0 rounded-full bg-brand-50 px-[9px] py-[4px] text-[10px] font-black text-brand">
                  {selectedAudienceOption.title} 미리보기
                </span>
              </div>

              <div className="mt-[12px] grid grid-cols-3 overflow-hidden rounded-[9px] border border-divider bg-surface-soft">
                <div className="min-w-0 border-r border-divider px-[10px] py-[9px]">
                  <p className="text-[10px] font-black text-muted2">담긴 블록</p>
                  <p className="mt-[3px] text-[15px] font-black text-ink">{safeBlocks.length} / {MAX_REPORT_BLOCKS}개</p>
                </div>
                <div className="min-w-0 border-r border-divider px-[10px] py-[9px]">
                  <p className="text-[10px] font-black text-muted2">보고 용도</p>
                  <p className="mt-[3px] truncate text-[15px] font-black text-ink">{selectedAudienceOption.title}</p>
                </div>
                <div className="min-w-0 px-[10px] py-[9px]">
                  <p className="text-[10px] font-black text-muted2">섹션</p>
                  <p className="mt-[3px] text-[15px] font-black text-ink">{previewSectionLabels.length || 0}개</p>
                </div>
              </div>

              <p className="mt-[8px] rounded-[8px] bg-row px-[10px] py-[7px] text-[11px] font-bold leading-4 text-muted2">
                포함 섹션: {previewSectionText}
              </p>

              <div className="mt-[12px] overflow-hidden rounded-[9px] border border-divider">
                <div className="flex items-center justify-between bg-surface-soft px-[10px] py-[7px] text-[11px] font-black text-muted2">
                  <span>보고서 순서</span>
                  <span>{safeBlocks.length}개 블록</span>
                </div>
                <div className="divide-y divide-rowline">
                  {previewBlocks.map((block, index) => (
                    <div key={block.id} className="grid grid-cols-[28px_1fr_auto] gap-[8px] px-[10px] py-[9px]">
                      <span className="grid h-6 w-6 place-items-center rounded-[7px] bg-brand-50 text-[11px] font-black text-brand">
                        {index + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-[12px] font-black text-ink">{block.title}</p>
                        <p className="mt-[2px] truncate text-[11px] font-semibold text-muted2">{block.subtitle}</p>
                        <p className="mt-[4px] truncate text-[10px] font-black text-brand">{block.meta}</p>
                      </div>
                      <span className="shrink-0 self-start whitespace-nowrap rounded-full bg-row px-[7px] py-[3px] text-[10px] font-black text-muted2">
                        {getReportSectionLabel(block.section)}
                      </span>
                    </div>
                  ))}
                  {safeBlocks.length === 0 ? (
                    <div className="px-[10px] py-[18px] text-center text-[12px] font-semibold text-muted2">
                      담긴 블록이 없습니다. 이전 단계에서 분석 블록을 추가해주세요.
                    </div>
                  ) : null}
                </div>
              </div>

              {safeBlocks.length > previewBlocks.length ? (
                <p className="mt-[8px] text-[11px] font-semibold text-muted2">외 {safeBlocks.length - previewBlocks.length}개 블록은 생성 시 이어서 반영됩니다.</p>
              ) : null}
              <p className="mt-[10px] text-[11px] font-semibold leading-4 text-muted2">{selectedAudiencePreviewNote}</p>
            </div>
            <p className="mt-[12px] text-[12px] font-semibold text-muted2">수정이 필요하면 이전 단계에서 삭제·순서를 조정하세요.</p>
          </div>
        ) : null}

        {step === 4 ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="grid flex-1 content-start justify-items-center pt-[54px] text-center">
              <div>
                <div className="mx-auto grid h-[48px] w-[48px] place-items-center rounded-full bg-pos/10 text-pos">
                  <Check className="h-6 w-6" />
                </div>
                <p className="mt-[18px] text-[15px] font-black text-ink">보고서 준비 완료</p>
                <p className="mt-[8px] text-[12px] font-semibold text-muted2">동일 템플릿 · 표지·요약·워터마크 자동 생성</p>
              </div>
            </div>
            <div className="grid gap-[8px] pb-[8px]">
              {reportDownloadFormats.map(({ title, desc, format }) => (
                <button
                  key={title}
                  type="button"
                  onClick={() => void handleDownloadReport(format)}
                  disabled={exportingReport !== null}
                  className="flex h-[52px] items-center justify-between rounded-[9px] border border-border bg-surface px-[15px] text-left transition hover:border-brand/30 hover:bg-brand-50/40 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <span>
                    <span className="block text-[13px] font-black text-ink">{title}</span>
                    <span className="text-[11px] font-semibold text-muted2">{exportingReport === format ? "생성 중..." : desc}</span>
                  </span>
                  <Download className="h-4 w-4 text-muted2" />
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="shrink-0 border-t border-divider bg-surface px-[28px] pb-[18px] pt-[10px]">
        <div className="grid gap-[10px]">
        {step === 1 ? (
          <>
            <button type="button" onClick={() => onStep(2)} className="h-[31px] rounded-[9px] border border-dashed border-border bg-surface text-[12px] font-black text-muted2">
              + 분석 화면에서 더 담기
            </button>
            <button type="button" onClick={() => onStep(2)} className="h-[44px] rounded-[10px] bg-brand text-[15px] font-black text-white transition hover:bg-brandDark">
              용도 선택 →
            </button>
          </>
        ) : step === 2 ? (
          <div className="grid grid-cols-[72px_1fr] gap-[10px]">
            <button type="button" onClick={() => onStep(1)} className="h-[44px] rounded-[10px] border border-border bg-surface text-[13px] font-black text-ink">
              ← 이전
            </button>
            <button type="button" onClick={() => onStep(3)} className="h-[44px] rounded-[10px] bg-brand text-[14px] font-black text-white transition hover:bg-brandDark">
              미리보기 →
            </button>
          </div>
        ) : step === 3 ? (
          <div className="grid grid-cols-[72px_1fr] gap-[10px]">
            <button type="button" onClick={() => onStep(2)} className="h-[44px] rounded-[10px] border border-border bg-surface text-[13px] font-black text-ink">
              ← 이전
            </button>
            <button type="button" onClick={handlePrepareReport} className="h-[44px] rounded-[10px] bg-brand text-[14px] font-black text-white">
              보고서 생성 →
            </button>
          </div>
        ) : null}
        </div>
      </div>
    </aside>
  );
}

export function ReportPreviewOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-ink text-white">
      <div className="flex h-[54px] items-center justify-between border-b border-white/10 bg-sidebar px-[16px]">
        <h2 className="text-[15px] font-black">통합 트렌드 보고서</h2>
        <div className="flex items-center gap-[10px]">
          <div className="flex rounded-[9px] bg-black/40 p-1">
            {["PDF", "DOCX"].map((item, index) => (
              <button key={item} type="button" className={cn("h-[28px] rounded-[7px] px-[15px] text-[12px] font-black", index === 0 ? "bg-surface text-ink" : "text-row")}>
                {item}
              </button>
            ))}
          </div>
          <button type="button" className="h-[32px] rounded-[9px] bg-brand px-[16px] text-[12px] font-black text-white">
            생성
          </button>
          <button type="button" onClick={onClose} className="grid h-[32px] w-[32px] place-items-center rounded-[9px] bg-white/10">
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      <div className="h-[calc(100vh-54px)] overflow-y-auto py-[28px]">
        <article className="mx-auto w-[720px] rounded-[6px] bg-surface text-ink shadow-2xl">
          <div className="px-[34px] py-[32px]">
            <p className="text-[12px] font-black tracking-[.2em] text-brand">SILICON2 · TREND REPORT</p>
            <h1 className="mt-[14px] text-[28px] font-black leading-tight">유럽 시장 트렌드 분석<br />2025 연간 · 스킨케어</h1>
            <p className="mt-[18px] text-[13px] font-semibold text-ink3">대상 권역 유럽 (Poland 중심) · 기간 2025.01-12</p>
            <p className="mt-[4px] text-[13px] font-semibold text-ink3">생성일 2026-06-23 · 수신 내부 SCM팀</p>
            <div className="mt-[22px] grid gap-[8px] text-[13px] font-black">
              <p><span className="mr-2 inline-block h-3 w-3 rounded-[3px] bg-blue-600" />1. 국가 — 시장 규모와 성장</p>
              <p><span className="mr-2 inline-block h-3 w-3 rounded-[3px] bg-pos" />2. 브랜드 — 경쟁 위치와 건강도</p>
              <p><span className="mr-2 inline-block h-3 w-3 rounded-[3px] bg-warn" />3. SKU — 인기 제품과 묶음</p>
            </div>
          </div>
          {[
            ["1. 국가 — 시장 규모와 성장", "유럽 국가별 판매 순위", ["Poland", "Germany", "France"], ["3.4M", "2.1M", "1.8M"], ["▲32%", "▲15%", "▼6%"]],
            ["2. 브랜드 — 경쟁 위치와 건강도", "브랜드 MOI(시장 기여도) 순위 · Market Opportunity Index, 0-100", ["OO 브랜드 (귀사)", "토리든", "롬앤"], ["82", "76", "68"], ["▲24%", "▲41%", "▼5%"]],
            ["3. SKU — 인기 제품과 묶음", "급상승 SKU", ["바이오 콜라겐 마스크", "레티놀 샷 부스터", "345 릴리프 크림"], ["▲58%", "신규", "▲32%"], ["+ 345 토너", "+ 아이 패치", "+ 쑥 선크림"]]
          ].map(([title, sub, names, vals, growth]) => (
            <section key={String(title)} className="border-t border-divider px-[34px] py-[26px]">
              <div className="mb-[16px] flex items-center justify-between">
                <h2 className="text-[18px] font-black text-ink">{title as string}</h2>
                <span className="rounded-[7px] bg-row px-[10px] py-[4px] text-[11px] font-black text-muted2">이 블록 분석에서 담음</span>
              </div>
              <p className="mb-[10px] text-[12px] font-black text-ink3">{sub as string}</p>
              <div className="grid grid-cols-2 gap-[24px]">
                <div>
                  {(names as string[]).map((name, index) => (
                    <div key={`${name}-${index}`} className="grid grid-cols-[24px_1fr_70px] border-b border-rowline py-[8px] text-[13px]">
                      <span className="font-black text-muted2">{index + 1}</span>
                      <span className="font-black">{name}</span>
                      <span className="text-right font-black">{(vals as string[])[index]}</span>
                    </div>
                  ))}
                </div>
                <div>
                  {(growth as string[]).map((item, index) => (
                    <div key={item} className="mb-[8px] rounded-[7px] border border-rowline px-[12px] py-[8px] text-right text-[13px] font-black">
                      {item}
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-[16px] rounded-[8px] border border-warn-border bg-warn-bg px-[14px] py-[11px] text-[12px] font-black text-warn">
                요약 — 유럽 내 Poland가 최대·최고 성장 시장. 스킨케어가 절반 이상이며, 선케어가 차세대 성장 카테고리.
              </div>
            </section>
          ))}
        </article>
      </div>
    </div>
  );
}
