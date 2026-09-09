import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatNumber } from "@/lib/utils";
import type { EtaEvent } from "@/types/api";

export function EtaTimeline({ events }: { events: EtaEvent[] }) {
  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>ETA 타임라인 미리보기</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {events.map((event) => (
          <div key={`${event.date}-${event.mode}`} className="flex gap-4">
            <div className="flex w-28 shrink-0 flex-col items-end">
              <span className="text-sm font-bold text-slate-900">{event.date}</span>
              <span className="text-xs text-slate-500">{event.mode}</span>
            </div>
            <div className="relative flex-1 border-l border-line pl-5">
              <span className="absolute -left-2 top-1 h-4 w-4 rounded-full border-4 border-white bg-brand-600" />
              <div className="rounded-2xl border border-line bg-slate-25 p-4">
                <div className="flex items-center justify-between">
                  <p className="font-semibold text-slate-900">{formatNumber(event.quantity)} pcs</p>
                  <Badge variant={event.status === "긴급" ? "danger" : event.status === "확인지연" ? "slate" : "success"}>
                    {event.status}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-slate-500">{event.skuCount} SKU 도착 예정</p>
              </div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
