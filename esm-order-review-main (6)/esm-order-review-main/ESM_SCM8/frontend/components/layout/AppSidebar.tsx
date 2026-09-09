"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Check,
  Database,
  ClipboardList,
  Home,
  LayoutDashboard,
  LucideIcon,
  Table2
} from "lucide-react";
import { LogoutButton } from "@/components/auth/LogoutButton";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { canAccessOrderAnalysis, isOrderAnalysisPath } from "@/lib/order-access";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const navItems: NavItem[] = [
  { href: routes.home, label: "홈", icon: Home },
  { href: routes.upload, label: "데이터 준비", icon: Database },
  { href: routes.dashboard, label: "대시보드", icon: LayoutDashboard },
  { href: routes.orderAnalysis, label: "발주분석", icon: Table2 },
  { href: routes.globalDemand, label: "수요분석", icon: BarChart3 },
  { href: routes.integratedOrderReview, label: "최종발주", icon: ClipboardList },
  { href: routes.mappingCheck, label: "데이터점검", icon: Check }
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }

  if (href === routes.orderAnalysis) {
    return pathname.startsWith("/order-analysis");
  }

  if (href === routes.globalDemand) {
    return pathname.startsWith("/season-trend");
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useAuthSession();
  const visibleNavItems = canAccessOrderAnalysis(user)
    ? navItems
    : navItems.filter((item) => !isOrderAnalysisPath(item.href));

  return (
    <aside className="sticky top-0 flex h-screen w-[78px] shrink-0 flex-col items-center border-r border-line bg-white">
      <nav className="mt-10 flex w-full flex-1 flex-col items-center gap-2 px-2">
        {visibleNavItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(pathname, item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-14 w-16 flex-col items-center justify-center gap-1 rounded-lg text-xs font-bold transition",
                active
                  ? "bg-slate-100 text-ink"
                  : "text-slate-500 hover:bg-slate-25 hover:text-black"
              )}
            >
              <Icon className={cn("h-4 w-4", active ? "stroke-[2.5]" : "stroke-[1.9]")} />
              <span className="whitespace-nowrap">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mb-5 flex flex-col items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-black text-sm font-black text-white">
          {(user?.display_name || user?.username || "S").slice(0, 1)}
        </div>
        {user ? <span className="max-w-[68px] truncate text-[10px] font-bold text-slate-500">{user.username}</span> : null}
        <LogoutButton compact />
      </div>
    </aside>
  );
}
