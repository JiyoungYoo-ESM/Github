import { AppShell } from "@/components/layout/AppShell";
import { IntegratedOrderReviewControls } from "./IntegratedOrderReviewControls";
import { IntegratedOrderTable } from "./IntegratedOrderTable";

export default function IntegratedOrderReviewPage() {
  return (
    <AppShell
      title="통합 발주"
      description="발주 검토와 시즌 수요를 종합해 언제, 무엇을, 몇 개 발주할지 결정합니다."
    >
      <div className="space-y-6">
        <IntegratedOrderReviewControls />
        <IntegratedOrderTable />
      </div>
    </AppShell>
  );
}
