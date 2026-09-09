"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeFileList,
  analyzeFiles,
  analyzeFromCms,
  classifyFiles,
  clearLastAnalysisResult,
  clearSeasonTrendResult,
  getExchangeRate,
  MAX_UPLOAD_FILE_BYTES,
  saveLastAnalysisResult,
  type AnalyzeOptions
} from "@/lib/api";
import { buildLeadTimeOverrides } from "@/lib/lead-times";
import { useSharedLeadTimes } from "@/lib/shared-lead-times";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import type { AnalyzeResponse, ExchangeRateResponse, UploadRole } from "@/types/api";
import {
  assignmentHasVerificationData,
  assignmentWithSelectedRole,
  fileListFromFiles,
  fileListSignature,
  formatFileSize,
  parseNumberInput,
  pendingFileAssignments,
  roleLabels,
  roleReviewRequired,
  requiredUploadItems,
  uploadItems,
  validateUploadSizes,
  type RoleAssignment,
  type UploadMode
} from "./upload-utils";

export function useUploadWorkflow() {
  const { selectedEntity } = useAuthSession();
  const currencyCode = selectedEntity === "USA" ? "USD" : "EUR";
  const quickInputRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<UploadMode>(() => {
    if (typeof window !== "undefined") {
      return new URLSearchParams(window.location.search).get("mode") === "manual" ? "manual" : "quick";
    }
    return "quick";
  });
  const [quickFiles, setQuickFiles] = useState<File[]>([]);
  const [assignments, setAssignments] = useState<RoleAssignment[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Partial<Record<UploadRole, File | null>>>({});
  const [safetyMonths, setSafetyMonths] = useState("3");
  const {
    methods: leadTimeMethods,
    values: leadTimeValues,
    loading: leadTimeLoading,
    error: leadTimeError,
    setLeadTime
  } = useSharedLeadTimes();
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [exchangeRate, setExchangeRate] = useState<ExchangeRateResponse | null>(null);
  const [exchangeRateError, setExchangeRateError] = useState("");
  const [exchangeRateInput, setExchangeRateInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [cmsAsOf, setCmsAsOf] = useState(() => new Date().toISOString().slice(0, 10));
  const [cmsLoading, setCmsLoading] = useState(false);

  const requiredRoles = useMemo(() => requiredUploadItems.map((item) => item.role), []);

  const perfLog = (message: string, fields: Record<string, unknown> = {}) => {
    if (typeof window !== "undefined") {
      console.info(`[perf][upload-workflow] ${message}`, fields);
    }
  };

  const manualUploadedCount = useMemo(
    () => uploadItems.filter((item) => selectedFiles[item.role]).length,
    [selectedFiles]
  );

  const assignedRoleCounts = useMemo(() => {
    const counts = new Map<UploadRole, number>();
    for (const assignment of assignments) {
      if (assignment.role) {
        counts.set(assignment.role, (counts.get(assignment.role) ?? 0) + 1);
      }
    }
    return counts;
  }, [assignments]);

  const quickReadyRoleCount = useMemo(
    () => requiredRoles.filter((role) => assignedRoleCounts.get(role) === 1).length,
    [assignedRoleCounts, requiredRoles]
  );

  const currentUploadedCount = mode === "quick" ? quickReadyRoleCount : manualUploadedCount;

  const changeMode = (nextMode: UploadMode) => {
    setMode(nextMode);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (nextMode === "manual") {
        url.searchParams.set("mode", "manual");
      } else {
        url.searchParams.delete("mode");
      }
      window.history.replaceState(null, "", url.toString());
    }
  };

  const missingRoles = useMemo(
    () => requiredRoles.filter((role) => (assignedRoleCounts.get(role) ?? 0) === 0),
    [assignedRoleCounts, requiredRoles]
  );

  const duplicateRoles = useMemo(
    () => requiredRoles.filter((role) => (assignedRoleCounts.get(role) ?? 0) > 1),
    [assignedRoleCounts, requiredRoles]
  );

  const reviewRequiredAssignments = useMemo(
    () => assignments.filter((assignment) => roleReviewRequired(assignment) && !assignment.confirmed),
    [assignments]
  );

  const manualMissingItems = useMemo(
    () => requiredUploadItems.filter((item) => !selectedFiles[item.role]),
    [selectedFiles]
  );
  const submitDisabled = loading || cmsLoading || (mode === "quick" && classifyLoading);
  const resetAnalysisResult = () => {
    clearLastAnalysisResult();
    clearSeasonTrendResult();
    setResult(null);
  };

  useEffect(() => {
    let cancelled = false;

    getExchangeRate(currencyCode)
      .then((response) => {
        if (!cancelled) {
          setExchangeRate(response);
          setExchangeRateError("");
          setExchangeRateInput(String(response.eur_krw_rate));
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          setExchangeRate(null);
          setExchangeRateError(caught instanceof Error ? caught.message : "환율 조회 실패");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currencyCode]);

  const buildAnalyzeOptions = (): AnalyzeOptions => {
    if (leadTimeLoading) {
      throw new Error("선택한 법인의 운송 리드타임을 불러오는 중입니다.");
    }
    if (leadTimeError) {
      throw new Error(leadTimeError);
    }
    const trimmedExchangeRate = exchangeRateInput.trim();
    return {
      eurKrwRate: trimmedExchangeRate
        ? parseNumberInput(trimmedExchangeRate, `${currencyCode}/KRW 환율`)
        : undefined,
      safetyMonths: parseNumberInput(safetyMonths, "안전재고 개월수"),
      leadTimeOverrides: buildLeadTimeOverrides(leadTimeMethods, leadTimeValues)
    };
  };

  const runClassification = async (files: File[]) => {
    setError("");
    resetAnalysisResult();
    if (files.length === 0) {
      setAssignments([]);
      return;
    }

    setClassifyLoading(true);
    try {
      const response = await classifyFiles(files);
      setAssignments(
        response.files.map((item) => ({
          ...item,
          file: files[item.index],
          role: item.suggested_role,
          confirmed: false
        }))
      );
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "자동 분류 중 오류가 발생했습니다.";
      setError(message.includes("Failed to fetch") ? "분석 서버와 연결되지 않았습니다. 잠시 후 다시 시도해주세요." : message);
      setAssignments([]);
    } finally {
      setClassifyLoading(false);
    }
  };

  const handleQuickFilesChange = (files: FileList | null) => {
    const nextFiles = Array.from(files ?? []);
    setQuickFiles(nextFiles);
    setError("");
    resetAnalysisResult();
    if (nextFiles.length === 0) {
      setAssignments([]);
      return;
    }
    const sizeError = validateUploadSizes(nextFiles);
    if (sizeError) {
      setAssignments([]);
      setError(sizeError);
      return;
    }

    setAssignments(pendingFileAssignments(nextFiles));
    void runClassification(nextFiles);
  };
  const handleQuickFilesChangeRef = useRef(handleQuickFilesChange);
  useEffect(() => {
    handleQuickFilesChangeRef.current = handleQuickFilesChange;
  });

  const applyQuickInputFiles = () => {
    handleQuickFilesChange(quickInputRef.current?.files ?? null);
  };

  const removeQuickFile = (index: number) => {
    const nextFiles = quickFiles.filter((_, fileIndex) => fileIndex !== index);
    if (quickInputRef.current) {
      quickInputRef.current.files = fileListFromFiles(nextFiles);
    }
    setQuickFiles(nextFiles);
    setError("");
    resetAnalysisResult();
    if (nextFiles.length === 0) {
      setAssignments([]);
      return;
    }
    const sizeError = validateUploadSizes(nextFiles);
    if (sizeError) {
      setAssignments([]);
      setError(sizeError);
      return;
    }
    setAssignments(pendingFileAssignments(nextFiles));
    void runClassification(nextFiles);
  };

  useEffect(() => {
    if (mode !== "quick") {
      return undefined;
    }
    const syncInputFiles = () => {
      const inputFiles = Array.from(quickInputRef.current?.files ?? []);
      if (inputFiles.length === 0) {
        return;
      }
      if (fileListSignature(inputFiles) !== fileListSignature(quickFiles)) {
        handleQuickFilesChangeRef.current(quickInputRef.current?.files ?? null);
      }
    };
    syncInputFiles();
    const timer = window.setInterval(syncInputFiles, 500);
    return () => window.clearInterval(timer);
  }, [mode, quickFiles]);

  const handleAssignmentChange = (index: number, role: UploadRole | "") => {
    setAssignments((current) =>
      current.map((assignment) =>
        assignment.index === index ? assignmentWithSelectedRole(assignment, role) : assignment
      )
    );
    setError("");
    resetAnalysisResult();
  };

  const confirmAssignment = (index: number) => {
    setAssignments((current) =>
      current.map((assignment) =>
        assignment.index === index && assignmentHasVerificationData(assignment)
          ? { ...assignment, confirmed: true }
          : assignment
      )
    );
    setError("");
    resetAnalysisResult();
  };

  const handleManualFileChange = (role: UploadRole, file: File | null) => {
    if (file && file.size > MAX_UPLOAD_FILE_BYTES) {
      setError(`파일 1개 최대 용량은 ${formatFileSize(MAX_UPLOAD_FILE_BYTES)}입니다. ${file.name} 파일은 ${formatFileSize(file.size)}입니다.`);
      resetAnalysisResult();
      return;
    }
    setSelectedFiles((current) => ({
      ...current,
      [role]: file
    }));
    setError("");
    resetAnalysisResult();
  };

  const handleQuickSubmit = async (options: AnalyzeOptions) => {
    if (quickFiles.length === 0) {
      setError("먼저 엑셀 파일을 여러 개 선택해주세요.");
      return;
    }
    const sizeError = validateUploadSizes(quickFiles);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    if (assignments.length === 0) {
      await runClassification(quickFiles);
      return;
    }
    if (missingRoles.length > 0) {
      setError(`필수 파일이 부족합니다: ${missingRoles.map((role) => roleLabels[role]).join(", ")}`);
      return;
    }
    if (duplicateRoles.length > 0) {
      setError(`같은 종류의 파일이 중복되었습니다: ${duplicateRoles.map((role) => roleLabels[role]).join(", ")}`);
      return;
    }
    if (reviewRequiredAssignments.length > 0) {
      setError(
        `자동 분류 확인이 필요한 파일이 있습니다: ${reviewRequiredAssignments
          .map((assignment) => assignment.original_name)
          .join(", ")}`
      );
      return;
    }

    const activeAssignments = assignments.filter((assignment) => assignment.role);
    const files = activeAssignments.map((assignment) => assignment.file);
    const roles = activeAssignments.map((assignment) => assignment.role as UploadRole);
    const response = await analyzeFileList(files, roles, options);
    await saveLastAnalysisResult(response, { markExecuted: true });
    setResult(response);
  };

  const handleManualSubmit = async (options: AnalyzeOptions) => {
    const missing = requiredUploadItems.filter((item) => !selectedFiles[item.role]);
    if (missing.length > 0) {
      setError(`필수 파일이 부족합니다: ${missing.map((item) => item.label).join(", ")}`);
      return;
    }

    const filesByRole = {} as Partial<Record<UploadRole, File>>;
    for (const item of uploadItems) {
      const file = selectedFiles[item.role];
      if (file) {
        filesByRole[item.role] = file;
      }
    }
    const sizeError = validateUploadSizes(Object.values(filesByRole));
    if (sizeError) {
      setError(sizeError);
      return;
    }
    const response = await analyzeFiles(filesByRole, options);
    await saveLastAnalysisResult(response, { markExecuted: true });
    setResult(response);
  };

  const handleCmsSubmit = async () => {
    const startedAt = performance.now();
    perfLog("cms_submit_started", { asOf: cmsAsOf });
    setError("");
    resetAnalysisResult();

    if (!/^\d{4}-\d{2}-\d{2}$/.test(cmsAsOf)) {
      setError("CMS 분석 기준일을 YYYY-MM-DD 형식으로 입력해주세요.");
      return;
    }

    let options: AnalyzeOptions;
    try {
      options = buildAnalyzeOptions();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석 기준값을 확인해주세요.");
      return;
    }

    setCmsLoading(true);
    try {
      const apiStartedAt = performance.now();
      const response = await analyzeFromCms(cmsAsOf, options);
      perfLog("cms_api_returned", { seconds: Number(((performance.now() - apiStartedAt) / 1000).toFixed(3)), jobId: response.job_id });
      const saveStartedAt = performance.now();
      await saveLastAnalysisResult(response, { markExecuted: true });
      perfLog("cms_result_saved", { seconds: Number(((performance.now() - saveStartedAt) / 1000).toFixed(3)), jobId: response.job_id });
      setResult(response);
      perfLog("cms_submit_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)), jobId: response.job_id });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "CMS 분석 요청 중 오류가 발생했습니다.";
      setError(message.includes("Failed to fetch") ? "분석 서버와 연결되지 않았습니다. 잠시 후 다시 시도해주세요." : message);
    } finally {
      setCmsLoading(false);
    }
  };

  const handleSubmit = async () => {
    const startedAt = performance.now();
    perfLog("upload_submit_started", { mode });
    setError("");
    resetAnalysisResult();

    let options: AnalyzeOptions;
    try {
      options = buildAnalyzeOptions();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "분석 기준값을 확인해주세요.");
      return;
    }

    setLoading(true);
    try {
      if (mode === "quick") {
        await handleQuickSubmit(options);
      } else {
        await handleManualSubmit(options);
      }
      perfLog("upload_submit_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)), mode });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "분석 요청 중 오류가 발생했습니다.";
      setError(message.includes("Failed to fetch") ? "분석 서버와 연결되지 않았습니다. 잠시 후 다시 시도해주세요." : message);
    } finally {
      setLoading(false);
    }
  };

  return {
    quickInputRef,
    mode,
    changeMode,
    quickFiles,
    assignments,
    selectedFiles,
    safetyMonths,
    setSafetyMonths,
    leadTimeMethods,
    leadTimeValues,
    leadTimeLoading,
    leadTimeError,
    setLeadTime,
    error,
    result,
    exchangeRate,
    exchangeRateError,
    exchangeRateInput,
    setExchangeRateInput,
    loading,
    classifyLoading,
    assignedRoleCounts,
    currentUploadedCount,
    missingRoles,
    reviewRequiredAssignments,
    manualUploadedCount,
    manualMissingItems,
    submitDisabled,
    runClassification,
    handleQuickFilesChange,
    applyQuickInputFiles,
    removeQuickFile,
    handleAssignmentChange,
    confirmAssignment,
    handleManualFileChange,
    handleSubmit,
    cmsAsOf,
    setCmsAsOf,
    cmsLoading,
    handleCmsSubmit
  };
}
