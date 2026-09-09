import { DashboardClient } from "@/app/dashboard/DashboardClient";
import { AppShell } from "@/components/layout/AppShell";

export default function DashboardPage() {
  return (
    <AppShell title="대시보드" description="분석 결과에서 오늘 먼저 확인할 SKU와 발주 흐름을 요약합니다.">
      <DashboardClient />
    </AppShell>
  );
}
