"use client";

import { X } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";

import { Card, CardContent } from "@/components/ui/card";
import { chartColors } from "@/lib/chart-tokens";
import { monthLabel } from "@/lib/global-demand-view-model";
import { cn, formatNumber } from "@/lib/utils";
import { LENS_LABEL, compactNumber, type Lens } from "./GlobalDemandViewModel";

function ScopeChip({
  label,
  value,
  options,
  onSelect,
  onClear
}: {
  label: string;
  value: string;
  options: string[];
  onSelect: (value: string) => void;
  onClear?: () => void;
}) {
  return (
    <span className="inline-flex min-h-10 items-center gap-1 rounded-full border border-line bg-white px-3 text-sm font-bold text-ink shadow-sm">
      <span className="text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onSelect(event.target.value)}
        className="max-w-[190px] bg-transparent font-black outline-none"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {onClear ? (
        <button type="button" onClick={onClear} className="rounded-full p-0.5 text-slate-400 hover:bg-slate-100 hover:text-ink">
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </span>
  );
}

function LensSegment({ lens, onChange }: { lens: Lens; onChange: (lens: Lens) => void }) {
  const order: Lens[] = ["monthly", "ingredient", "brand", "sku"];
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardContent className="flex flex-wrap gap-2 p-3">
        {order.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            className={cn(
              "min-h-10 rounded-lg px-4 text-base font-black transition",
              lens === item ? "bg-ink text-white shadow-sm" : "text-slate-500 hover:bg-slate-50 hover:text-ink"
            )}
          >
            {LENS_LABEL[item]}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

function lastNonZeroIndex(values: number[]) {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    if ((values[index] ?? 0) > 0) return index;
  }
  return 0;
}

function MiniSparkline({
  values,
  color = chartColors.brand,
  observedOnly = false,
  peakMonth
}: {
  values: number[];
  color?: string;
  observedOnly?: boolean;
  peakMonth?: number;
}) {
  const visibleValues = observedOnly ? values.slice(0, lastNonZeroIndex(values) + 1) : values;
  const max = Math.max(...visibleValues, 1);
  const data = visibleValues.map((value, index) => {
    const normalized = (value / max) * 100;
    return {
      name: monthLabel(index + 1),
      value: normalized,
      peak: peakMonth === index + 1 ? normalized : null,
      raw: value
    };
  });
  return (
    <div className="h-11 w-28">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 2, bottom: 2, left: 2 }}>
          <Tooltip
            cursor={false}
            formatter={(value, _name, props) => [formatNumber(Number(props.payload.raw)), "판매수량"]}
            labelFormatter={(label) => label}
          />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line
            type="monotone"
            dataKey="peak"
            stroke={color}
            strokeWidth={0}
            dot={(props) => {
              const point = props as { cx?: number; cy?: number; value?: number | null };
              if (point.value == null || typeof point.cx !== "number" || typeof point.cy !== "number") return null;
              return <circle cx={point.cx} cy={point.cy} r={3.5} fill={color} stroke={chartColors.white} strokeWidth={2} />;
            }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function KpiCard({
  label,
  value,
  detail,
  accent = chartColors.brand,
  onClick
}: {
  label: string;
  value: string;
  detail?: string;
  accent?: string;
  onClick?: () => void;
}) {
  const card = (
    <Card className="overflow-hidden rounded-lg border-line bg-white shadow-sm">
      <div className="flex">
        <div className="w-1.5 shrink-0" style={{ backgroundColor: accent }} />
        <CardContent className="flex min-h-[116px] flex-1 items-center p-5">
          <div className="min-w-0">
            <p className="text-sm font-black text-slate-500">{label}</p>
            <p className="mt-2 truncate text-2xl font-black text-ink tabular-nums" title={value}>
              {value}
            </p>
            {detail ? <p className="mt-1 truncate text-xs font-bold text-slate-500">{detail}</p> : null}
          </div>
        </CardContent>
      </div>
    </Card>
  );
  if (!onClick) return card;
  return (
    <button type="button" onClick={onClick} className="block w-full text-left transition hover:-translate-y-0.5">
      {card}
    </button>
  );
}

export { KpiCard, LensSegment, MiniSparkline, ScopeChip };


