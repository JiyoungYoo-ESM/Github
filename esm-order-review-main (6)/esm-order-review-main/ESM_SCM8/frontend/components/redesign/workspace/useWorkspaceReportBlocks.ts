"use client";

import { useCallback, useEffect, useState } from "react";
import { sanitizeAmountData } from "@/lib/amount-permissions";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { captureReportCardHtmlSnapshot, rememberReportCardClickTarget } from "../lib/report-card-snapshot";
import { MAX_REPORT_BLOCKS } from "../lib/workspace-format";
import type { ReportBlock } from "../lib/types";

export function useWorkspaceReportBlocks() {
  const permissions = useUserPermissions();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerStep, setDrawerStep] = useState<1 | 2 | 3 | 4>(1);
  const [blocks, setBlocks] = useState<ReportBlock[]>([]);
  const [limitNotice, setLimitNotice] = useState<string | null>(null);

  useEffect(() => {
    document.addEventListener("pointerdown", rememberReportCardClickTarget, true);
    document.addEventListener("click", rememberReportCardClickTarget, true);
    return () => {
      document.removeEventListener("pointerdown", rememberReportCardClickTarget, true);
      document.removeEventListener("click", rememberReportCardClickTarget, true);
    };
  }, []);

  const openDrawer = useCallback(() => {
    setDrawerOpen(true);
    setDrawerStep(1);
  }, []);

  const prepareBlock = useCallback(
    (block: ReportBlock): ReportBlock => {
      if (permissions.canViewAmountData) {
        return {
          ...block,
          htmlSnapshot: block.htmlSnapshot ?? captureReportCardHtmlSnapshot(block)
        };
      }
      return {
        ...sanitizeAmountData(block),
        htmlSnapshot: null
      };
    },
    [permissions.canViewAmountData]
  );

  const toggleBlock = useCallback((block: ReportBlock) => {
    setBlocks((current) => {
      if (current.some((item) => item.id === block.id)) {
        return current.filter((item) => item.id !== block.id);
      }
      if (current.length >= MAX_REPORT_BLOCKS) {
        setLimitNotice(`보고서에는 최대 ${MAX_REPORT_BLOCKS}개까지 담을 수 있습니다. 담긴 블록을 정리한 뒤 다시 추가해주세요.`);
        return current;
      }
      setLimitNotice(null);
      return [...current, prepareBlock(block)];
    });
  }, [prepareBlock]);

  const syncBlock = useCallback((block: ReportBlock) => {
    const preparedBlock = prepareBlock(block);
    const withoutSnapshot = ({ htmlSnapshot: _htmlSnapshot, ...rest }: ReportBlock) => rest;
    const nextSignature = JSON.stringify(withoutSnapshot(preparedBlock));
    setBlocks((current) => {
      const index = current.findIndex((item) => item.id === block.id);
      if (index < 0 || JSON.stringify(withoutSnapshot(current[index])) === nextSignature) return current;
      const next = [...current];
      next[index] = permissions.canViewAmountData
        ? { ...preparedBlock, htmlSnapshot: preparedBlock.htmlSnapshot ?? current[index].htmlSnapshot ?? null }
        : preparedBlock;
      return next;
    });
  }, [permissions.canViewAmountData, prepareBlock]);

  useEffect(() => {
    if (permissions.canViewAmountData) return;
    setBlocks((current) => current.map((block) => prepareBlock(block)));
  }, [permissions.canViewAmountData, prepareBlock]);

  const removeBlock = useCallback((id: string) => {
    setBlocks((current) => current.filter((item) => item.id !== id));
  }, []);

  const reorderBlock = useCallback((draggedId: string, targetId: string) => {
    setBlocks((current) => {
      const fromIndex = current.findIndex((item) => item.id === draggedId);
      const toIndex = current.findIndex((item) => item.id === targetId);
      if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return current;
      const next = [...current];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!limitNotice) return;
    const timer = window.setTimeout(() => setLimitNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [limitNotice]);

  return {
    blocks,
    closeDrawer: () => setDrawerOpen(false),
    drawerOpen,
    drawerStep,
    limitNotice,
    openDrawer,
    removeBlock,
    reorderBlock,
    setDrawerStep,
    syncBlock,
    toggleBlock
  };
}
