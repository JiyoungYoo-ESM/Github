"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, Check, ChevronLeft, ChevronRight } from "lucide-react";
import { DEMAND_DATA_MIN_DATE, todayKst } from "../../lib/workspace-format";

export function SourceDataRowV2({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[11px] border border-border bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[13px] font-black text-ink">{title}</p>
          <p className="mt-2 text-[12px] font-semibold leading-[1.45] text-muted2">{description}</p>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 text-[12px] font-black text-green-600">
          <Check className="h-3.5 w-3.5" />
          자동 조회
        </span>
      </div>
    </div>
  );
}

export function InputDateBoxV2({
  label,
  value,
  min = DEMAND_DATA_MIN_DATE,
  max = todayKst,
  onChange
}: {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (value: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const selectedDate = useMemo(() => parseDateValue(value), [value]);
  const minimumDate = useMemo(() => parseDateValue(min), [min]);
  const maximumDate = useMemo(() => parseDateValue(max), [max]);
  const fallbackDate = selectedDate ?? maximumDate ?? minimumDate ?? new Date();
  const [open, setOpen] = useState(false);
  const [viewDate, setViewDate] = useState(() => monthStart(fallbackDate));

  useEffect(() => {
    if (!open) return;

    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setViewDate(monthStart(parseDateValue(value) ?? parseDateValue(max) ?? parseDateValue(min) ?? new Date()));
  }, [max, min, open, value]);

  const calendarDays = useMemo(() => buildCalendarDays(viewDate), [viewDate]);
  const previousMonth = addMonths(viewDate, -1);
  const nextMonth = addMonths(viewDate, 1);
  const canGoPrevious = !minimumDate || monthKey(previousMonth) >= monthKey(minimumDate);
  const canGoNext = !maximumDate || monthKey(nextMonth) <= monthKey(maximumDate);

  const selectDate = (date: Date) => {
    if (isDateDisabled(date, minimumDate, maximumDate)) return;
    onChange(dateValue(date));
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <label className="block">
      <span className="mb-2 block text-[12px] font-semibold text-muted">{label}</span>
      <div ref={rootRef} className="relative">
        <button
          ref={triggerRef}
          type="button"
          data-testid={`date-picker-${label}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-label={`${label} 선택${value ? `, 현재 ${value}` : ""}`}
          onClick={() => {
            if (!open) {
              setViewDate(monthStart(parseDateValue(value) ?? maximumDate ?? minimumDate ?? new Date()));
            }
            setOpen((current) => !current);
          }}
          className="flex h-[39px] w-full items-center justify-between rounded-[9px] border border-border bg-surface px-3 text-left text-[13px] font-black text-ink outline-none transition hover:border-sidebar focus:border-sidebar focus:bg-white"
        >
          <span>{value || "YYYY-MM-DD"}</span>
          <CalendarDays className="h-[15px] w-[15px] shrink-0 text-ink" aria-hidden="true" />
        </button>

        {open ? (
          <div
            role="dialog"
            data-testid="date-picker-calendar"
            aria-label={`${label} 달력`}
            className="absolute left-0 top-[45px] z-50 w-[202px] overflow-hidden rounded-[4px] border border-[var(--datepicker-border)] bg-white shadow-[0_2px_7px_rgba(0,0,0,0.16)]"
          >
            <div className="flex h-[30px] items-center justify-between bg-[var(--datepicker-header)] px-[5px] text-[12px] font-black text-white">
              <button
                type="button"
                aria-label="이전 달"
                disabled={!canGoPrevious}
                onClick={() => setViewDate(previousMonth)}
                className="flex h-[20px] w-[20px] items-center justify-center rounded-full bg-white/95 text-[var(--datepicker-header)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-[13px] w-[13px]" strokeWidth={3} aria-hidden="true" />
              </button>
              <span>{monthLabel(viewDate)}</span>
              <button
                type="button"
                aria-label="다음 달"
                disabled={!canGoNext}
                onClick={() => setViewDate(nextMonth)}
                className="flex h-[20px] w-[20px] items-center justify-center rounded-full bg-white/95 text-[var(--datepicker-header)] transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronRight className="h-[13px] w-[13px]" strokeWidth={3} aria-hidden="true" />
              </button>
            </div>
            <div className="px-[4px] pb-[4px] pt-[5px]">
              <div className="grid grid-cols-7 pb-[3px] text-center text-[9px] font-black text-[var(--datepicker-cell-text)]">
                {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
              </div>
              <div className="grid grid-cols-7 border-l border-t border-white bg-white">
                {calendarDays.map((day, index) => {
                  const disabled = !day || isDateDisabled(day, minimumDate, maximumDate);
                  const selected = Boolean(day && value === dateValue(day));
                  return (
                    <div key={`${day ? dateValue(day) : "empty"}-${index}`} className="h-[25px] border-b border-r border-white bg-[var(--datepicker-cell)]">
                      {day ? (
                        <button
                          type="button"
                          disabled={disabled}
                          aria-label={`${dateValue(day)} 선택`}
                          aria-pressed={selected}
                          onClick={() => selectDate(day)}
                          className={`h-full w-full text-[10px] font-semibold text-[var(--datepicker-cell-text)] transition hover:bg-white disabled:cursor-not-allowed disabled:text-muted2 ${
                            selected ? "bg-[var(--datepicker-selected)] font-black text-ink hover:bg-[var(--datepicker-selected)]" : ""
                          }`}
                        >
                          {day.getDate()}
                        </button>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </label>
  );
}

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function dateValue(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parseDateValue(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day ? parsed : null;
}

function monthStart(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date: Date, months: number) {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

function monthKey(date: Date) {
  return date.getFullYear() * 12 + date.getMonth();
}

function monthLabel(date: Date) {
  return new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(date);
}

function buildCalendarDays(viewDate: Date) {
  const firstDay = monthStart(viewDate);
  const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
  const cellCount = Math.ceil((firstDay.getDay() + daysInMonth) / 7) * 7;
  return Array.from({ length: cellCount }, (_, index) => {
    const dayNumber = index - firstDay.getDay() + 1;
    return dayNumber > 0 && dayNumber <= daysInMonth
      ? new Date(viewDate.getFullYear(), viewDate.getMonth(), dayNumber)
      : null;
  });
}

function isDateDisabled(date: Date, minimumDate: Date | null, maximumDate: Date | null) {
  return Boolean((minimumDate && date < minimumDate) || (maximumDate && date > maximumDate));
}
