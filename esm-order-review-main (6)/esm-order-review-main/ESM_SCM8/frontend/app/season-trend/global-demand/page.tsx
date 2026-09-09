import { AppShell } from "@/components/layout/AppShell";
import { SeasonTrendPageClient } from "@/components/season-trend/SeasonTrendPageClient";

export default function GlobalDemandPage() {
  return (
    <AppShell
      title="수요 분석"
      description="권역, 국가, 카테고리, SKU까지 한 화면에서 좁혀 봅니다."
    >
      <SeasonTrendPageClient section="global" />
    </AppShell>
  );
}
