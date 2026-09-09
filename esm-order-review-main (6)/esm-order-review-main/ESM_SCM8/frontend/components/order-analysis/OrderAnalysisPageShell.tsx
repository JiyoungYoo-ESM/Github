import type { LucideIcon } from "lucide-react";
import { PlayCircle } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { OrderAnalysisClient, type OrderAnalysisTab } from "@/components/order-analysis/OrderAnalysisClient";
import { routes } from "@/lib/routes";

const description = "발주검토 · 재고공백 · SKU 집중도를 하나의 흐름에서 확인합니다.";

function HeaderAction({
  href,
  icon: Icon,
  children
}: {
  href: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-flex h-10 items-center gap-2 rounded-xl border border-line bg-white px-4 text-sm font-bold text-ink shadow-sm transition hover:border-slate-300 hover:bg-slate-25"
    >
      <Icon className="h-5 w-5" />
      {children}
    </Link>
  );
}

export function OrderAnalysisPageShell({ tab }: { tab: OrderAnalysisTab }) {
  return (
    <AppShell
      title="발주 분석"
      description={description}
      actions={
        <HeaderAction href={routes.upload} icon={PlayCircle}>
          발주 분석 시작하기
        </HeaderAction>
      }
    >
      <OrderAnalysisClient tab={tab} />
    </AppShell>
  );
}
