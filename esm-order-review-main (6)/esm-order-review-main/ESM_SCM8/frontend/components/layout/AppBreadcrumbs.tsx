"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { routes } from "@/lib/routes";

const labels: Array<{ match: (pathname: string) => boolean; items: Array<{ label: string; href?: string }> }> = [
  {
    match: (pathname) => pathname.startsWith("/season-trend"),
    items: [{ label: "리포트", href: routes.globalDemand }]
  },
  {
    match: (pathname) => pathname === routes.upload,
    items: [{ label: "데이터 준비" }]
  },
  {
    match: (pathname) => pathname === routes.integratedOrderReview,
    items: [{ label: "통합 발주" }]
  },
  {
    match: (pathname) => pathname === routes.dashboard,
    items: [{ label: "대시보드" }]
  }
];

function orderAnalysisItems(pathname: string) {
  const active =
    pathname.includes("stock-gap")
      ? "재고공백"
      : pathname.includes("sku-concentration")
        ? "SKU 집중도"
        : "발주검토";
  return [
    { label: "발주 분석", href: routes.orderAnalysis },
    { label: active }
  ];
}

export function AppBreadcrumbs() {
  const pathname = usePathname();
  const matched = labels.find((item) => item.match(pathname));
  const seasonItems = [
    { label: "리포트", href: routes.globalDemand },
    { label: pathname.includes("mapping-check") ? "매핑 확인" : "수요 분석" }
  ];
  const items = pathname.startsWith("/order-analysis")
    ? orderAnalysisItems(pathname)
    : pathname.startsWith("/season-trend")
      ? seasonItems
      : matched?.items ?? [{ label: "홈" }];

  return (
    <nav aria-label="현재 위치" className="mb-2 flex flex-wrap items-center gap-1 text-sm font-bold text-slate-400">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className="inline-flex items-center gap-1">
            {item.href && !isLast ? (
              <Link href={item.href} className="transition hover:text-brand-700">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "text-slate-500" : undefined}>{item.label}</span>
            )}
            {!isLast ? <ChevronRight className="h-4 w-4" /> : null}
          </span>
        );
      })}
    </nav>
  );
}
