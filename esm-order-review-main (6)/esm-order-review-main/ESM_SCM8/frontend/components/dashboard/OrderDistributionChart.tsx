import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { dashboardBarColors } from "@/lib/chart-tokens";
import { formatNumber } from "@/lib/utils";
import type { OrderDistributionPoint } from "@/types/api";

function formatKrwAmount(value: number) {
  if (value >= 100_000_000) {
    return `약 ${formatNumber(value / 100_000_000, 1)}억`;
  }
  if (value >= 10_000) {
    return `약 ${formatNumber(value / 10_000, 1)}만`;
  }
  return `${formatNumber(value)}원`;
}

export function OrderDistributionChart({ data }: { data: OrderDistributionPoint[] }) {
  const maxValue = Math.max(...data.map((item) => item.value), 0);

  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>브랜드별 발주 금액 TOP 5</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex h-72 items-center justify-center rounded-lg bg-slate-25 text-sm text-slate-500">
            발주 금액이 있는 브랜드가 없습니다.
          </div>
        ) : (
          <div className="space-y-4">
            {data.map((item, index) => {
              const width = maxValue > 0 ? Math.max((item.value / maxValue) * 100, 4) : 0;
              return (
                <div key={item.name} className="space-y-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate font-semibold text-slate-700">{item.name}</span>
                    <span className="shrink-0 font-bold text-ink">{formatKrwAmount(item.value)}</span>
                  </div>
                  <div className="h-3 rounded-full bg-slate-100">
                    <div
                      className="h-3 rounded-full"
                      style={{
                        width: `${width}%`,
                        backgroundColor: dashboardBarColors[index % dashboardBarColors.length]
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
