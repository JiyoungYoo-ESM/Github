"use client";

import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Loader2,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuthSession } from "@/components/auth/AuthSessionContext";
import {
  getActiveSeasonFactorArtifact,
  getSeasonFactorRefreshStatus,
  refreshSeasonFactorArtifact,
  type SeasonFactorRefreshStatus,
  type SeasonFactorArtifact,
  type SeasonFactorProfile,
  type SeasonFactorProfileError
} from "@/lib/api/order-logic-v3";
import { cn } from "@/lib/utils";
import { hasCurrentSalesPolicy, refreshFailure, refreshProgress } from "./refreshProgress";

const MONTH_LABELS = Array.from({ length: 12 }, (_, index) => `${index + 1}월`);
const CLASS1_AGGREGATE = "__FUNCTION_CLASS_1__";
const RECONNECT_NOTICE = "갱신 상태 연결을 다시 확인하고 있습니다. 서버 작업을 재실행하지 않습니다.";

type FactorListItem =
  | { id: string; kind: "profile"; value: SeasonFactorProfile }
  | { id: string; kind: "error"; value: SeasonFactorProfileError };

function itemKey(scope: string, class1: string, class2: string) {
  return `${scope}:${class1}:${class2}`;
}

function itemLabel(item: SeasonFactorProfile | SeasonFactorProfileError) {
  if (item.scope === "FUNCTION_CLASS_1" || item.function_class_2_code === CLASS1_AGGREGATE) {
    return `${item.function_class_1_code} · 기능구분1 기준`;
  }
  return `${item.function_class_1_code} · ${item.function_class_2_code}`;
}

function dateRangeLabel(artifact: SeasonFactorArtifact) {
  return `${artifact.window_start.replaceAll("-", ".")} ~ ${artifact.window_end.replaceAll("-", ".")}`;
}

function timestampLabel(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}

function factorValue(profile: SeasonFactorProfile, month: number) {
  return profile.factors.find((factor) => factor.calendar_month === month)?.factor ?? null;
}

function StatusChip({ artifact }: { artifact: SeasonFactorArtifact }) {
  const active = artifact.status === "active" && artifact.validation.passed && hasCurrentSalesPolicy(artifact);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black",
        active
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-amber-200 bg-amber-50 text-amber-800"
      )}
    >
      {active ? <CheckCircle2 className="h-3.5 w-3.5" /> : <CircleAlert className="h-3.5 w-3.5" />}
      {active ? "V3 자동 적용 중" : "판매 기준 갱신 필요"}
    </span>
  );
}

function EmptyState({ error, onRefresh, refreshing, canRefresh }: {
  error: string;
  onRefresh: () => void;
  refreshing: boolean;
  canRefresh: boolean;
}) {
  return (
    <section className="mx-auto mt-5 max-w-[1320px] px-4 pb-8 lg:px-[25px]">
      <div className="rounded-[14px] border border-amber-200 bg-amber-50/70 px-5 py-6 shadow-soft">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-amber-100 text-amber-700">
              <AlertCircle className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-[15px] font-black text-ink">활성 계절지수가 없습니다</h2>
              <p className="mt-1.5 max-w-[720px] text-[12px] font-semibold leading-5 text-muted">
                {error || "계절지수를 갱신하고 자동 검증을 통과해야 발주분석 V3을 계산할 수 있습니다."}
              </p>
            </div>
          </div>
          {canRefresh ? (
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[8px] bg-brand px-4 text-[11px] font-black text-white transition hover:bg-brand/90 disabled:cursor-wait disabled:opacity-60"
            >
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              계절지수 갱신
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export function SeasonFactorManagementScreen() {
  const { user, selectedEntity } = useAuthSession();
  const canRefresh = user?.is_admin === true;
  const [artifact, setArtifact] = useState<SeasonFactorArtifact | null>(null);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshJob, setRefreshJob] = useState<SeasonFactorRefreshStatus | null>(null);
  const generation = useRef(0);

  const loadArtifact = useCallback(async () => {
    const current = generation.current;
    setLoading(true);
    setError("");
    try {
      const nextArtifact = await getActiveSeasonFactorArtifact();
      if (current !== generation.current) return;
      setArtifact(nextArtifact);
      return true;
    } catch (caught) {
      if (current !== generation.current) return;
      setArtifact(null);
      setError(caught instanceof Error ? caught.message : "활성 계절지수를 불러오지 못했습니다.");
      return false;
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    generation.current += 1;
    const current = generation.current;
    let timer: ReturnType<typeof setTimeout>;
    let handledJob: string | undefined;
    setArtifact(null);
    setRefreshing(false);
    setRefreshJob(null);
    setNotice("");
    void loadArtifact();
    const poll = async () => {
      try {
        const job = await getSeasonFactorRefreshStatus();
        if (current !== generation.current) return;
        if (job.entity_code !== selectedEntity) throw new Error("법인 전환 중입니다. 상태를 다시 확인합니다.");
        setRefreshJob(job);
        setNotice(previous => previous === RECONNECT_NOTICE ? "" : previous);
        setRefreshing(job.status === "queued" || job.status === "running");
        if (job.status === "queued" || job.status === "running") setError("");
        if (job.job_id !== handledJob && (job.status === "succeeded" || job.status === "failed")) {
          if (job.status === "succeeded") {
            const loaded = await loadArtifact();
            if (current !== generation.current) return;
            if (!loaded) return;
            handledJob = job.job_id;
            setNotice("자동 검증을 통과해 새 계절지수가 발주분석 V3에 적용되었습니다.");
          } else {
            handledJob = job.job_id;
            setNotice("");
            setError(refreshFailure(job));
          }
        }
      } catch {
        if (current === generation.current) setNotice(RECONNECT_NOTICE);
      } finally {
        if (current === generation.current) timer = setTimeout(poll, 5_000);
      }
    };
    void poll();
    return () => { generation.current += 1; clearTimeout(timer); };
  }, [loadArtifact, selectedEntity]);

  const items = useMemo<FactorListItem[]>(() => {
    if (!artifact) return [];
    const profiles = [...artifact.profiles]
      .sort((left, right) => itemLabel(left).localeCompare(itemLabel(right), "ko"))
      .map((value) => ({
        id: itemKey(value.scope, value.function_class_1_code, value.function_class_2_code),
        kind: "profile" as const,
        value
      }));
    const errors = [...artifact.errors]
      .sort((left, right) => itemLabel(left).localeCompare(itemLabel(right), "ko"))
      .map((value) => ({
        id: itemKey(value.scope, value.function_class_1_code, value.function_class_2_code),
        kind: "error" as const,
        value
      }));
    return [...profiles, ...errors];
  }, [artifact]);

  useEffect(() => {
    if (!items.length) {
      setSelectedItemId("");
      return;
    }
    if (!items.some((item) => item.id === selectedItemId)) {
      setSelectedItemId(items[0].id);
    }
  }, [items, selectedItemId]);

  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;

  const refreshArtifact = async () => {
    if (refreshing) return;
    const current = generation.current;
    if (!canRefresh || refreshing) return;
    setRefreshing(true);
    setError("");
    setNotice("");
    try {
      const job = await refreshSeasonFactorArtifact();
      if (current !== generation.current) return;
      if (job.entity_code !== selectedEntity) throw new Error("갱신 요청의 법인이 일치하지 않습니다. 다시 확인해 주세요.");
      setRefreshJob(job);
      setNotice("갱신 요청을 접수했습니다. 화면을 이동해도 서버 작업은 계속됩니다.");
    } catch (caught) {
      if (current !== generation.current) return;
      setError(caught instanceof Error ? caught.message : "계절지수 갱신에 실패했습니다.");
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div className="grid min-h-[440px] place-items-center">
        <div className="inline-flex items-center gap-2 text-[12px] font-black text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> 계절지수 상태를 불러오는 중입니다.
        </div>
      </div>
    );
  }

  if (!artifact) {
    return <EmptyState error={refreshProgress(refreshJob) || error} onRefresh={refreshArtifact} refreshing={refreshing} canRefresh={canRefresh} />;
  }

  return (
    <div className="mx-auto max-w-[1460px] px-4 pb-8 pt-5 lg:px-[25px] lg:pt-6">
      <section className="rounded-[14px] border border-border bg-surface px-5 py-5 shadow-soft lg:px-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip artifact={artifact} />
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-soft px-2.5 py-1 text-[10px] font-black text-muted">
                <CalendarDays className="h-3.5 w-3.5" /> 자동 갱신 · 매월 1일
              </span>
            </div>
            <h2 className="mt-3 text-[18px] font-black tracking-tight text-ink">현재 적용 중인 계절지수</h2>
            <p className="mt-1.5 max-w-[760px] text-[12px] font-semibold leading-5 text-muted">
              최근 24개월 판매 데이터를 기준으로 갱신합니다. 자동 검증을 통과한 결과만 이 법인의 발주분석 V3 계산에 바로 반영됩니다.
            </p>
          </div>
          <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
            <span className="inline-flex h-10 items-center justify-center gap-2 rounded-[8px] border border-border bg-surface-soft px-3 text-[10.5px] font-bold text-muted">
              <Clock3 className="h-4 w-4" /> 최근 갱신 {timestampLabel(artifact.calculated_at)}
            </span>
            {canRefresh ? (
              <button
                type="button"
                onClick={refreshArtifact}
                disabled={refreshing}
                data-testid="season-factor-refresh"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-[8px] bg-brand px-4 text-[10.5px] font-black text-white transition hover:bg-brand/90 disabled:cursor-wait disabled:opacity-60"
              >
                {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                계절지수 갱신
              </button>
            ) : (
              <span className="inline-flex h-10 items-center justify-center rounded-[8px] border border-border bg-surface-soft px-3 text-[10px] font-black text-muted">관리자만 갱신 가능</span>
            )}
          </div>
        </div>
        {notice && !error && refreshJob?.status !== "failed" ? (
          <div className="mt-4 flex items-start gap-2 rounded-[9px] border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-[11px] font-bold text-emerald-800">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> {notice}
          </div>
        ) : null}
        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-[9px] border border-amber-200 bg-amber-50 px-3 py-2.5 text-[11px] font-bold text-amber-800">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /> {error}
          </div>
        ) : null}
        {refreshProgress(refreshJob) ? (
          <div role="status" className="mt-4 flex items-center gap-2 rounded-[9px] border border-border bg-surface-soft px-3 py-3 text-[11px] font-bold text-ink">
            <Loader2 className="h-4 w-4 animate-spin" /> {refreshProgress(refreshJob)}
          </div>
        ) : null}
      </section>

      <section className="mt-4 overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
        <div className="grid min-h-[580px] xl:grid-cols-[250px_320px_minmax(0,1fr)]">
          <aside className="border-b border-border bg-surface-soft/45 p-4 xl:border-b-0 xl:border-r">
            <p className="text-[11px] font-black text-ink">적용 버전</p>
            <button
              type="button"
              className="mt-3 w-full rounded-[10px] border border-emerald-200 bg-emerald-50 px-3 py-3 text-left shadow-sm"
              aria-label="현재 적용 중인 계절지수 버전"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] font-black text-ink">현재 적용 버전</span>
                <StatusChip artifact={artifact} />
              </div>
              <p className="mt-2 break-all text-[10px] font-black text-emerald-800">{artifact.version}</p>
              <p className="mt-2 text-[10.5px] font-semibold text-muted">{dateRangeLabel(artifact)}</p>
              <p className="mt-1 text-[10.5px] font-semibold text-muted">프로파일 {artifact.profiles.length}개 · 기본값 1.0 {artifact.profiles.filter((profile) => profile.application_status === "DEFAULT_1").length}개 · 계산 보류 {artifact.errors.length}개</p>
            </button>
            <div className="mt-4 rounded-[10px] border border-border bg-white px-3 py-3">
              <div className="flex items-center gap-2 text-[10.5px] font-black text-ink"><ShieldCheck className="h-4 w-4 text-emerald-600" /> 자동 검증 기준</div>
              <p className="mt-2 text-[10px] font-semibold leading-4 text-muted">24개월 범위, 1~12월 계수, 계수 평균 1.0, 중복·법인 일치를 확인합니다.</p>
            </div>
          </aside>

          <aside className="border-b border-border xl:border-b-0 xl:border-r">
            <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
              <h3 className="text-[11px] font-black text-ink">기능구분별 계절지수</h3>
              <span className="text-[10px] font-bold text-muted">{items.length}개</span>
            </div>
            <div className="max-h-[530px] overflow-y-auto p-2.5">
              {items.map((item) => {
                const selected = item.id === selectedItemId;
                const isProfile = item.kind === "profile";
                const isDefault = item.value.application_status === "DEFAULT_1";
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedItemId(item.id)}
                    className={cn(
                      "mb-1.5 flex w-full items-center justify-between gap-3 rounded-[9px] border px-3 py-2.5 text-left transition last:mb-0",
                      selected
                        ? isProfile ? "border-brand/35 bg-brand-50" : "border-amber-300 bg-amber-50"
                        : "border-transparent hover:border-border hover:bg-surface-soft"
                    )}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-[11px] font-black text-ink">{itemLabel(item.value)}</span>
                      <span className="mt-1 block text-[9.5px] font-semibold text-muted">{isDefault ? "계산 보류 → 기본값 1.0 적용" : isProfile ? "자동 적용 가능" : "계산 보류"}</span>
                    </span>
                    <span className={cn("shrink-0 rounded-full px-2 py-1 text-[9px] font-black", isProfile && !isDefault ? "bg-white text-emerald-700" : "bg-white text-amber-800")}>{isDefault ? "기본값" : isProfile ? "적용" : "보류"}</span>
                  </button>
                );
              })}
            </div>
          </aside>

          <article className="min-w-0 p-4 lg:p-5">
            {selectedItem?.kind === "profile" ? (
              <>
                <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-[10px] font-black text-brand">월별 상세</p>
                    <h3 className="mt-1 text-[18px] font-black tracking-tight text-ink">{itemLabel(selectedItem.value)}</h3>
                    <p className="mt-1 text-[10.5px] font-semibold text-muted">
                      {selectedItem.value.scope === "FUNCTION_CLASS_1"
                        ? "기능구분2가 없거나 미분류인 SKU에도 이 기능구분1 계절지수를 적용합니다."
                        : "기능구분1·2가 모두 있는 SKU에 적용하는 세부 계절지수입니다."}
                    </p>
                  </div>
                  {selectedItem.value.application_status === "DEFAULT_1" ? (
                    <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[10px] font-black text-amber-800"><AlertCircle className="h-3.5 w-3.5" /> 기본값 1.0 적용</span>
                  ) : (
                    <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-black text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> 검증 통과</span>
                  )}
                </div>
                {selectedItem.value.application_status === "DEFAULT_1" ? (
                  <div className="mt-4 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-[11px] font-semibold leading-5 text-amber-900">
                    <p>계절지수 계산 실패로 1~12월 모두 기본값 1.0을 적용합니다. V3는 계절성에 의한 가감 없이 계산하며, 분류·판매이력 등 다른 계산 조건은 유지됩니다.</p>
                  </div>
                ) : null}
                <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                  {MONTH_LABELS.map((label, index) => {
                    const value = factorValue(selectedItem.value, index + 1);
                    return (
                      <div key={label} className="rounded-[10px] border border-border bg-surface-soft/45 px-3 py-3 text-center">
                        <p className="text-[10px] font-bold text-muted">{label}</p>
                        <p className="mt-1.5 text-[16px] font-black tracking-tight text-ink">{value == null ? "-" : value.toFixed(3)}</p>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-5 rounded-[10px] border border-border bg-surface-soft/40 px-4 py-3">
                  <p className="text-[10.5px] font-black text-ink">적용 방식</p>
                  <p className="mt-1 text-[10.5px] font-semibold leading-5 text-muted">V3 계산은 이 활성 버전만 참조합니다. 다음 갱신 결과가 검증을 통과할 때까지 현재 버전은 그대로 유지됩니다.</p>
                </div>
              </>
            ) : selectedItem?.kind === "error" ? (
              <div className="rounded-[12px] border border-amber-200 bg-amber-50/70 px-5 py-5">
                <div className="flex items-start gap-3">
                  <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
                  <div>
                    <p className="text-[10px] font-black text-amber-800">계절지수 계산 보류</p>
                    <h3 className="mt-1 text-[18px] font-black text-ink">{itemLabel(selectedItem.value)}</h3>
                    <p className="mt-3 text-[11px] font-semibold leading-5 text-amber-900">{selectedItem.value.message}</p>
                    <p className="mt-2 text-[10px] font-bold text-muted">사유 코드: {selectedItem.value.reason_code}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid min-h-[360px] place-items-center text-center">
                <div><p className="text-[13px] font-black text-ink">표시할 기능구분이 없습니다.</p><p className="mt-1 text-[11px] font-semibold text-muted">계절지수를 갱신하면 기능구분별 결과가 표시됩니다.</p></div>
              </div>
            )}
          </article>
        </div>
      </section>
    </div>
  );
}
