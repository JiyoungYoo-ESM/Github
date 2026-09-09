import { ArrowUpRight, Package, Plane, ShieldAlert, Warehouse } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatNumber } from "@/lib/utils";
import type { DashboardKpi } from "@/types/api";

const icons = [Warehouse, Plane, Package, ArrowUpRight, ShieldAlert];

function displayKpiValue(kpi: DashboardKpi) {
  if (kpi.unit === "SKU" || kpi.unit === "개") {
    return formatNumber(kpi.value);
  }
  if (kpi.unit === "KRW") {
    return `약 ${formatNumber(kpi.value / 100_000_000, 1)}억`;
  }
  return formatNumber(kpi.value, 0);
}

export function MetricCards({ kpis }: { kpis: DashboardKpi[] }) {
  return (
    <div className="grid gap-4 xl:grid-cols-5">
      {kpis.map((kpi, index) => {
        const Icon = icons[index] ?? Warehouse;
        return (
          <Card key={kpi.label} className="border-slate-200">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-500">{kpi.label}</p>
                  <p className="mt-3 whitespace-nowrap text-2xl font-bold tracking-tight text-ink">
                    {displayKpiValue(kpi)}
                  </p>
                  <p className="mt-1 text-xs font-semibold text-slate-500">{kpi.unit === "KRW" ? "KRW" : kpi.unit}</p>
                </div>
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-brand-50 text-brand-700">
                  <Icon className="h-5 w-5" />
                </span>
              </div>
              {kpi.trend ? <p className="mt-4 text-xs font-semibold text-brand-600">{kpi.trend}</p> : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
