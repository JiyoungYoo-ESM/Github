"use client";

import { useState } from "react";
import { Check, ChevronDown, Lock, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { deepInsightNav, insightNav } from "./nav-config";
import type { Metric, NavItem, Screen, TableRow } from "./types";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { allowedEntityOptions, ENTITY_BY_CODE } from "@/lib/entities";

function toneClass(tone: Metric["tone"]) {
  if (tone === "brand") return "text-brand";
  if (tone === "green") return "text-emerald-600";
  if (tone === "amber") return "text-amber-600";
  return "text-muted";
}

export function CorporationSelector() {
  const [open, setOpen] = useState(false);
  const { user, selectedEntity, selectEntity } = useAuthSession();
  const corporationOptions = allowedEntityOptions(user?.allowed_entities ?? []);
  const activeCorporation = selectedEntity ? ENTITY_BY_CODE[selectedEntity] : corporationOptions[0];

  if (!user || !activeCorporation) return null;

  return (
    <div className="border-b border-white/[.08] px-[14px] py-[10px]">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-[9px] rounded-[8px] border border-white/[.10] bg-white/[.035] px-[10px] py-[8px] text-left transition hover:border-white/[.16] hover:bg-white/[.06]"
      >
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-[7px]">
            <span className="text-[10px] font-black uppercase tracking-[.12em] text-muted">법인</span>
            <span className="rounded-full bg-brand/15 px-[6px] py-[1px] text-[9.5px] font-black text-brand">
              {activeCorporation.orderIntegrated
                ? "전체 연동"
                : activeCorporation.insightIntegrated
                  ? "분석 연동"
                  : "준비 중"}
            </span>
          </span>
          <span className="mt-[5px] block truncate text-[12.5px] font-extrabold text-row">{activeCorporation.legalName}</span>
        </span>
        <ChevronDown
          className={cn("h-[15px] w-[15px] shrink-0 text-muted2 transition-transform", open ? "rotate-180" : "")}
          strokeWidth={2.4}
        />
      </button>
      {open ? (
        <div className="analytics-sidebar-scroll mt-[8px] max-h-[280px] overflow-y-auto rounded-[10px] border border-white/[.10] bg-dropdownpanel py-[5px] shadow-[0_18px_38px_rgba(0,0,0,0.32)]">
          {corporationOptions.map((option) => (
            <button
              key={option.code}
              type="button"
              onClick={() => {
                void selectEntity(option.code);
                setOpen(false);
              }}
              title={option.integrated ? option.displayName : `${option.displayName}: 데이터 연동 준비 중`}
              className={cn(
                "flex w-full items-start gap-[8px] px-[10px] py-[8px] text-left",
                option.code === selectedEntity
                  ? "bg-brand text-white"
                  : "text-muted2 hover:bg-white/[.06] hover:text-row"
              )}
            >
              {option.code === selectedEntity ? (
                <Check className="mt-[1px] h-[14px] w-[14px] shrink-0" strokeWidth={2.4} />
              ) : !option.integrated ? (
                <Lock className="mt-[1px] h-[13px] w-[13px] shrink-0" strokeWidth={2.2} />
              ) : <span className="h-[14px] w-[14px] shrink-0" />}
              <span className="min-w-0 flex-1">
                <span className="block break-words text-[11.5px] font-extrabold leading-[1.28] tracking-normal">
                  {option.displayName} · {option.legalName}
                </span>
                {!option.integrated ? (
                  <span className="mt-[3px] block text-[9.5px] font-black leading-none text-muted2/70">데이터 연동 준비 중</span>
                ) : null}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function NavSection({
  label,
  items,
  screen,
  onNavigate,
  favoriteIds,
  onToggleFavorite
}: {
  label: string;
  items: NavItem[];
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  favoriteIds: Screen[];
  onToggleFavorite: (screen: Screen) => void;
}) {
  if (items.length === 0) return null;

  return (
    <div className="mb-[22px]">
      <p className="mb-2 px-2 text-[10.5px] font-extrabold uppercase tracking-[.12em] text-muted">
        {label}
      </p>
      <nav className="flex flex-col gap-[3px]">
        {items.map((item) => {
          const Icon = item.icon;
          const active = screen === item.id || (item.id === "order" && screen === "gap");
          const favorite = favoriteIds.includes(item.id);
          const disabled = Boolean(item.disabled);
          return (
            <div
              key={item.id}
              className={cn(
                "group flex min-h-[38px] w-full items-center rounded-[10px] py-1 transition-colors",
                disabled
                  ? "cursor-not-allowed text-muted opacity-60"
                  : active
                    ? "bg-brand text-white"
                    : "text-muted2 hover:bg-white/10 hover:text-white"
              )}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onNavigate(item.id)}
                aria-label={disabled ? `${item.label} ${item.statusLabel ?? "준비 중"}` : undefined}
                className="flex min-h-full min-w-0 flex-1 items-center gap-[11px] px-3 text-left text-[13.5px] font-bold disabled:cursor-not-allowed disabled:text-muted"
              >
                <Icon className="h-[17px] w-[17px] shrink-0" strokeWidth={active ? 2.5 : 2} />
                <span className="min-w-0 whitespace-normal break-keep leading-[1.15]">{item.label}</span>
                {item.statusLabel ? (
                  <span className="ml-auto shrink-0 self-start rounded-full border border-white/[.12] px-[6px] py-[2px] text-[9px] font-black text-current">
                    {item.statusLabel}
                  </span>
                ) : null}
              </button>
              {!disabled && !item.statusLabel ? (
                <button
                  type="button"
                  onClick={() => onToggleFavorite(item.id)}
                  aria-label={favorite ? `${item.label} 즐겨찾기 해제` : `${item.label} 즐겨찾기 추가`}
                  title={favorite ? "즐겨찾기 해제" : "즐겨찾기 추가"}
                  className={cn(
                    "mr-2 grid h-7 w-7 shrink-0 place-items-center rounded-md transition",
                    favorite
                      ? "text-amber-300"
                      : "text-muted opacity-0 hover:text-white group-hover:opacity-100 focus:opacity-100"
                  )}
                >
                  <Star className={cn("h-[14px] w-[14px]", favorite ? "fill-current" : "")} strokeWidth={2.2} />
                </button>
              ) : null}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

function NavSubSection({
  label,
  items,
  screen,
  onNavigate,
  favoriteIds,
  onToggleFavorite
}: {
  label: string;
  items: NavItem[];
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  favoriteIds: Screen[];
  onToggleFavorite: (screen: Screen) => void;
}) {
  return (
    <div className="mb-[13px]">
      <p className="mb-2 px-2 text-[10.5px] font-extrabold uppercase tracking-[.12em] text-muted">
        {label}
      </p>
      <nav className="flex flex-col gap-[3px]">
        {items.map((item) => {
          const Icon = item.icon;
          const active = screen === item.id;
          const favorite = favoriteIds.includes(item.id);
          const disabled = Boolean(item.disabled);
          return (
            <div
              key={item.id}
              className={cn(
                "group flex h-[34px] w-full items-center rounded-[9px] transition-colors",
                disabled
                  ? "cursor-not-allowed text-muted opacity-60"
                  : active
                    ? "bg-brand text-white"
                    : "text-muted2 hover:bg-white/10 hover:text-white"
              )}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onNavigate(item.id)}
                aria-label={disabled ? `${item.label} ${item.statusLabel ?? "준비 중"}` : undefined}
                className="flex h-full min-w-0 flex-1 items-center gap-[10px] px-3 text-left text-[13px] font-bold disabled:cursor-not-allowed disabled:text-muted"
              >
                <Icon className="h-[15px] w-[15px] shrink-0" strokeWidth={active ? 2.4 : 2} />
                <span className="min-w-0 truncate">{item.label}</span>
                {item.statusLabel ? (
                  <span className="ml-auto shrink-0 rounded-full border border-white/[.12] px-[6px] py-[2px] text-[9px] font-black text-current">
                    {item.statusLabel}
                  </span>
                ) : null}
              </button>
              {!disabled && !item.statusLabel ? (
                <button
                  type="button"
                  onClick={() => onToggleFavorite(item.id)}
                  aria-label={favorite ? `${item.label} 즐겨찾기 해제` : `${item.label} 즐겨찾기 추가`}
                  title={favorite ? "즐겨찾기 해제" : "즐겨찾기 추가"}
                  className={cn(
                    "mr-2 grid h-7 w-7 shrink-0 place-items-center rounded-md transition",
                    favorite
                      ? "text-amber-300"
                      : "text-muted opacity-0 hover:text-white group-hover:opacity-100 focus:opacity-100"
                  )}
                >
                  <Star className={cn("h-[14px] w-[14px]", favorite ? "fill-current" : "")} strokeWidth={2.2} />
                </button>
              ) : null}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

export function InsightNavSection({
  screen,
  onNavigate,
  favoriteIds,
  onToggleFavorite
}: {
  screen: Screen;
  onNavigate: (screen: Screen) => void;
  favoriteIds: Screen[];
  onToggleFavorite: (screen: Screen) => void;
}) {
  return (
    <div className="mb-[22px]">
      <p className="mb-2 px-2 text-[10.5px] font-extrabold uppercase tracking-[.12em] text-muted">
        분석 · INSIGHT
      </p>
      <NavSubSection
        label="차원별"
        items={insightNav}
        screen={screen}
        onNavigate={onNavigate}
        favoriteIds={favoriteIds}
        onToggleFavorite={onToggleFavorite}
      />
      <NavSubSection
        label="심화"
        items={deepInsightNav}
        screen={screen}
        onNavigate={onNavigate}
        favoriteIds={favoriteIds}
        onToggleFavorite={onToggleFavorite}
      />
    </div>
  );
}

export function MetricCard({ metric }: { metric: Metric }) {
  return (
    <div className="rounded-[14px] border border-border bg-surface px-5 py-[17px] shadow-soft">
      <p className="text-[12.5px] font-semibold text-muted">{metric.label}</p>
      <p className="mt-[9px] text-[25px] font-black leading-none tracking-normal text-ink">
        {metric.value}
      </p>
      <p className={cn("mt-[10px] text-[12px] font-extrabold", toneClass(metric.tone))}>
        {metric.sub}
      </p>
    </div>
  );
}

export function DataTable({ headers, rows: tableRows }: { headers: string[]; rows: TableRow[] }) {
  return (
    <div className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse">
          <thead className="bg-surface-soft">
            <tr>
              {headers.map((header) => (
                <th
                  key={header}
                  className="border-b border-divider px-[18px] py-[12px] text-left text-[11.5px] font-black text-muted"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => (
              <tr key={row.join("-")} className="transition-colors hover:bg-surface-soft">
                {row.map((cell, index) => (
                  <td
                    key={`${cell}-${index}`}
                    className={cn(
                      "border-b border-rowline px-[18px] py-[13px] text-[13px] last:border-b-0",
                      index === 0 ? "font-black text-ink" : "font-bold text-ink3"
                    )}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Stepper({
  screen,
  analysisReady,
  onNavigate
}: {
  screen: Screen;
  analysisReady: boolean;
  onNavigate: (screen: Screen) => void;
}) {
  const steps = [
    { label: "데이터 입력", screen: "prep" },
    { label: "발주 분석", screen: "order" }
  ] satisfies Array<{ label: string; screen: Screen }>;
  const currentScreen = screen === "gap" ? "order" : screen;
  const currentIndex = Math.max(0, steps.findIndex((step) => step.screen === currentScreen));

  return (
    <div className="flex h-[52px] items-center justify-center overflow-hidden border-t border-divider px-4 sm:px-[25px]">
      <div className="flex w-full items-center sm:w-auto">
        {steps.map((step, index) => {
          const done = index < currentIndex && analysisReady;
          const current = index === currentIndex;
          return (
            <div key={step.screen} className={cn("flex min-w-0 items-center", index === 0 && "flex-1 sm:flex-none")}>
              <button
                type="button"
                onClick={() => onNavigate(step.screen)}
                className={cn(
                  "grid h-6 w-6 shrink-0 place-items-center rounded-full text-[12px] font-black",
                  done ? "bg-pos text-white" : current ? "bg-brand text-white" : "bg-divider text-muted2"
                )}
              >
                {done ? <Check className="h-[14px] w-[14px]" /> : index + 1}
              </button>
              <span
                className={cn(
                  "ml-2 truncate whitespace-nowrap text-[12px] font-black sm:ml-[10px] sm:text-[13px]",
                  current ? "text-brand" : done ? "text-ink" : "text-muted"
                )}
              >
                {step.label}
              </span>
              {index < steps.length - 1 ? (
                <div className={cn("mx-2 h-px flex-1 sm:mx-[14px] sm:w-[260px] sm:flex-none", done ? "bg-pos" : "bg-border")} />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FieldBox({
  label,
  value,
  caption,
  onChange
}: {
  label: string;
  value: string;
  caption?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-[12px] font-black text-ink3">{label}</span>
      <input
        value={value}
        readOnly={!onChange}
        onChange={(event) => onChange?.(event.target.value)}
        inputMode={onChange ? "decimal" : undefined}
        className="h-[43px] w-full rounded-[10px] border border-border bg-surface px-[14px] text-[15px] font-black text-ink outline-none"
      />
      {caption ? <span className="mt-2 block text-[11.5px] font-semibold text-muted2">{caption}</span> : null}
    </label>
  );
}
