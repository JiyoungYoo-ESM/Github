import Link from "next/link";
import { ArrowRight, ChevronDown } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const demoRows = [
  {
    sku: "JSMSM03-SREU",
    priority: "Priority 1",
    status: "입고 지연 위험",
    badgeClass: "bg-brand/10 text-brand",
  },
  {
    sku: "BODP04-MRCEU",
    priority: "Priority 2",
    status: "신규 발주 검토",
    badgeClass: "bg-black/5 text-black/70",
  },
  {
    sku: "DRAS01-CRRREU",
    priority: "Priority 3",
    status: "운송 ETA 확인",
    badgeClass: "bg-black/5 text-black/70",
  },
];

export function LandingHero() {
  return (
    <section className="relative overflow-hidden bg-black text-white">
      <video
        className="absolute inset-0 h-full w-full object-cover"
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        poster="/assets/hero-poster.jpg"
        aria-hidden="true"
      >
        <source src="/assets/silicon2_main_video.mp4" type="video/mp4" />
      </video>
      <div className="absolute inset-0 bg-black/40" />
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(0,0,0,0.66)_0%,rgba(0,0,0,0.45)_46%,rgba(0,0,0,0.18)_100%)]" />

      <div className="relative mx-auto grid min-h-[600px] max-w-7xl grid-cols-1 content-center gap-12 px-4 py-16 sm:min-h-[720px] sm:px-6 sm:py-20 xl:grid-cols-[1.08fr_0.92fr] xl:pl-24">
        <div className="max-w-[calc(100vw-32px)] sm:max-w-[760px]">
          <h1 className="text-[2.7rem] font-black leading-[0.95] tracking-normal sm:text-6xl lg:text-7xl xl:text-8xl">
            One View.
            <span className="block whitespace-nowrap text-brand">Clear Decisions.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-[17px] font-bold leading-snug text-white sm:mt-7 sm:text-xl [word-break:keep-all]">
            복잡한 발주 검토와 시장 분석을 한 화면으로 간편하게
          </p>
          <p className="mt-3 max-w-2xl text-[15px] leading-6 text-white/75 sm:mt-4 sm:text-lg sm:leading-8">
            발주 필요 여부와 재고 리스크부터 국가·브랜드·SKU별 시장 흐름까지 빠르게 확인합니다.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/upload"
              className={cn(
                buttonVariants({ size: "lg" }),
                "group rounded-full bg-brand px-6 text-white hover:bg-brand-dark",
              )}
            >
              데이터 입력부터 시작 <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>

        <div className="hidden justify-self-end lg:block">
          <div className="relative w-[440px] animate-hero-float rounded-[20px] border border-white/20 bg-white/10 p-4 shadow-soft backdrop-blur-md">
            <div className="absolute -right-4 -top-4 h-16 w-16 border-r-2 border-t-2 border-brand" />
            <div className="rounded-[16px] bg-white/95 p-5 text-black shadow-2xl shadow-black/20">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.16em] text-black/40">Order Analysis</p>
                  <h2 className="mt-1 text-xl font-black">발주 분석</h2>
                  <p className="mt-1 text-xs font-medium text-black/45">재고 · MOI · 미입고 · 운송중 반영</p>
                </div>
                <span className="rounded-full bg-black/5 px-3 py-1.5 text-[11px] font-black text-black/55">CMS 연동</span>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-2">
                <div className="rounded-[12px] border border-black/5 bg-black/[0.025] p-3">
                  <p className="text-[10px] font-bold text-black/45">발주필요 SKU</p>
                  <p className="mt-2 text-xl font-black leading-none">126</p>
                </div>
                <div className="rounded-[12px] border border-brand/10 bg-brand/5 p-3">
                  <p className="text-[10px] font-bold text-brand/70">긴급 SKU</p>
                  <p className="mt-2 text-xl font-black leading-none text-brand">18</p>
                </div>
                <div className="rounded-[12px] border border-black/5 bg-black/[0.025] p-3">
                  <p className="text-[10px] font-bold text-black/45">발주필요금액</p>
                  <p className="mt-2 text-xl font-black leading-none">₩8.4억</p>
                </div>
              </div>

              <div className="mt-5 flex items-center justify-between border-b border-black/10 pb-2.5">
                <p className="text-sm font-black">우선 확인 SKU</p>
                <span className="text-[11px] font-bold text-black/40">위험도순</span>
              </div>
              <div className="divide-y divide-black/[0.06]">
                {demoRows.map((row) => (
                  <div key={row.sku} className="flex items-center justify-between gap-3 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] bg-black/5 text-[11px] font-black text-black/45">
                        {row.priority.replace("Priority ", "")}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-mono text-[12px] font-bold text-black">{row.sku}</p>
                        <p className="mt-0.5 text-[10px] font-medium text-black/40">발주 검토 대상</p>
                      </div>
                    </div>
                    <span className={cn("whitespace-nowrap rounded-[7px] px-2.5 py-1 text-[11px] font-black", row.badgeClass)}>
                      {row.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <a
        href="#operational-value"
        className="absolute bottom-7 left-1/2 z-10 flex -translate-x-1/2 items-center justify-center rounded-full p-2 text-white/70 transition hover:text-white focus:outline-none focus:ring-2 focus:ring-white/70"
        aria-label="아래 섹션으로 이동"
      >
        <ChevronDown className="h-9 w-9 animate-scroll-cue stroke-[1.5]" />
      </a>
    </section>
  );
}
