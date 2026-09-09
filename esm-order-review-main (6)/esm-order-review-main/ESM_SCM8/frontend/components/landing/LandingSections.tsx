"use client";

import { useEffect, type CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  Download,
  FileSpreadsheet,
  Layers,
  Plane,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";

const values = [
  {
    title: "파일 입력 표준화",
    desc: "CMS 데이터를 한 번에 모아 재고·발주 판단과 시장 분석에 함께 활용합니다.",
    icon: FileSpreadsheet,
  },
  {
    title: "리스크 중심 의사결정",
    desc: "입고 지연, ETA 누락, 재고공백 등 운영 리스크를 전체 SKU 기준으로 확인합니다.",
    icon: Plane,
  },
  {
    title: "분석 결과 간편 공유",
    desc: "발주와 시장 분석 결과를 보고서로 정리해 팀과 빠르게 공유합니다.",
    icon: Database,
  },
];

const proofStats = [
  { value: "One View", label: "발주와 시장 판단을 한 화면에서" },
  { value: "CMS API", label: "데이터 직접 연동" },
  { value: "3단계", label: "리스크 자동 분류" },
  { value: "Export", label: "기존 양식 그대로 내보내기" },
];

const features = [
  {
    label: "국가 분석",
    desc: "권역별 판매 비중과 국가별 성장률을 비교해 우선 공략할 시장을 확인합니다.",
    icon: CheckCircle2,
  },
  {
    label: "브랜드 분석",
    desc: "브랜드별 매출, 성장률, 재고 수준을 함께 비교해 경쟁 위치와 성장 흐름을 파악합니다.",
    icon: ShieldCheck,
  },
  {
    label: "SKU · 시즌 캘린더",
    desc: "핵심 SKU의 판매 추이와 월별 피크를 연결해 시즌 수요와 준비 시점을 확인합니다.",
    icon: Clock,
  },
  ...(INGREDIENT_ANALYSIS_ENABLED
    ? [{
        label: "성분 분석",
        desc: "성분 키워드별 성장률과 브랜드 분포를 추적해 시장 트렌드를 발견합니다.",
        icon: Layers,
      }]
    : []),
  {
    label: "교차분석",
    desc: INGREDIENT_ANALYSIS_ENABLED
      ? "국가·브랜드·SKU·성분을 교차 비교해 단일 지표에서는 보이지 않던 기회를 찾습니다."
      : "국가·브랜드·SKU를 교차 비교해 단일 지표에서는 보이지 않던 기회를 찾습니다.",
    icon: RefreshCw,
  },
  {
    label: "브랜드 리포트",
    desc: "필요한 분석 블록을 선택해 브랜드별 인사이트를 공유 가능한 보고서로 구성합니다.",
    icon: Download,
  },
];

const steps = ["CMS API 호출", "데이터 기준 정리", "발주·시장 분석", "결과 다운로드"];

const beforeItems = [
  "CMS 데이터를 엑셀로 내려받아 수작업으로 대조",
  "SKU별 발주 필요 여부를 눈으로 판단",
  "국가·브랜드·SKU 분석을 개별 시트에서 확인",
];

const afterItems = [
  "분석 시작 한 번으로 CMS API 데이터 통합",
  "발주 필요/불필요와 우선순위 자동 산출",
  INGREDIENT_ANALYSIS_ENABLED
    ? "국가·브랜드·SKU·성분 인사이트를 한 화면에서 확인"
    : "국가·브랜드·SKU 인사이트를 한 화면에서 확인",
];

const revealDelay = (ms: number) => ({ "--reveal-delay": `${ms}ms` }) as CSSProperties;

export function LandingSections() {
  useEffect(() => {
    document.documentElement.classList.add("supports-scroll-reveal");
    const revealItems = Array.from(document.querySelectorAll<HTMLElement>("[data-scroll-rise]"));
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.16 },
    );

    revealItems.forEach((item) => observer.observe(item));

    return () => {
      observer.disconnect();
      document.documentElement.classList.remove("supports-scroll-reveal");
    };
  }, []);

  return (
    <>
      <section id="operational-value" className="mx-auto max-w-7xl scroll-mt-10 px-6 py-20">
        <div data-scroll-rise className="scroll-rise mb-10 max-w-2xl">
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-brand">Operational Value</p>
          <h2 className="mt-3 text-3xl font-black tracking-tight text-black">발주 판단부터 시장 인사이트까지 한 흐름으로 연결합니다</h2>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {values.map((item, index) => {
            const Icon = item.icon;
            return (
              <Card
                key={item.title}
                data-scroll-rise
                className="scroll-rise rounded-none border-black/10 shadow-none transition-colors hover:border-brand"
                style={revealDelay(100 + index * 90)}
              >
                <CardHeader>
                  <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-full bg-black/5 text-brand">
                    <Icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="font-bold">{item.title}</CardTitle>
                  <CardDescription>{item.desc}</CardDescription>
                </CardHeader>
              </Card>
            );
          })}
        </div>
      </section>

      <section className="bg-black py-16 text-white">
        <div className="mx-auto max-w-7xl px-6">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {proofStats.map((stat, index) => (
              <div
                key={stat.label}
                data-scroll-rise
                className="scroll-rise border-l-2 border-brand pl-6"
                style={revealDelay(80 + index * 90)}
              >
                <p className="text-3xl font-black tracking-tight lg:text-4xl">{stat.value}</p>
                <p className="mt-2 text-sm text-white/60">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-cloud py-20">
        <div className="mx-auto max-w-7xl px-6">
          <div data-scroll-rise className="scroll-rise max-w-2xl">
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-brand">Analysis Modules</p>
            <h2 className="mt-3 text-3xl font-black tracking-tight text-black">시장을 다각도로 읽는 인사이트 분석</h2>
          </div>
          <div className="mt-10 grid border-t border-black/10 md:grid-cols-2">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.label}
                  data-scroll-rise
                  className="scroll-rise flex items-start gap-4 border-b border-black/10 py-6 pr-6 transition-colors hover:bg-white md:px-4"
                  style={revealDelay(60 + index * 60)}
                >
                  <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black/5 text-brand">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="font-bold text-black">{feature.label}</p>
                    <p className="mt-1 text-sm leading-6 text-black/60">{feature.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section id="workflow" className="mx-auto max-w-7xl scroll-mt-10 px-6 py-20">
        <div className="grid gap-10 lg:grid-cols-[0.75fr_1.25fr] lg:items-center">
          <div data-scroll-rise className="scroll-rise">
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-brand">Workflow</p>
            <h2 className="mt-3 text-3xl font-black tracking-tight text-black">
              <span className="block">발주와 시장 판단까지 이어지는</span>
              <span className="block">분석 흐름</span>
            </h2>
            <p className="mt-4 leading-7 text-black/70">
              CMS API 데이터를 불러오면 재고·운송 리스크와 국가·브랜드·SKU별 시장 흐름을 함께 분석하고 결과로 연결합니다.
            </p>
          </div>
          <div className="space-y-8">
            <div data-scroll-rise className="scroll-rise" style={revealDelay(80)}>
              <div className="overflow-hidden border border-black/10 bg-white shadow-[0_24px_70px_rgba(0,0,0,0.14)]">
                <Image
                  src="/assets/cms-laptop-workflow-rotato.png"
                  alt="CMS 데이터 화면을 노트북에 배치한 목업"
                  width={1500}
                  height={914}
                  className="h-auto w-full"
                  priority={false}
                />
              </div>
            </div>
            <ol data-scroll-rise className="scroll-rise flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-0" style={revealDelay(160)}>
              {steps.map((step, index) => (
                <li key={step} className="relative flex items-center gap-4 sm:flex-1 sm:flex-col sm:gap-3 sm:text-center">
                  {index < steps.length - 1 && (
                    <span aria-hidden className="absolute left-[18px] top-9 hidden h-px sm:left-[calc(50%+26px)] sm:top-[18px] sm:block sm:w-[calc(100%-52px)] sm:bg-black/15" />
                  )}
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-black text-sm font-bold text-white">
                    {index + 1}
                  </span>
                  <span className="text-sm font-bold text-black">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="mt-16 grid gap-px overflow-hidden border border-black/10 bg-black/10 md:grid-cols-2">
          <div data-scroll-rise className="scroll-rise bg-white p-8" style={revealDelay(80)}>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-black/40">Before</p>
            <h3 className="mt-2 text-xl font-black text-black/60">기존 방식</h3>
            <ul className="mt-5 space-y-3">
              {beforeItems.map((item) => (
                <li key={item} className="flex items-start gap-3 text-black/55">
                  <X className="mt-1 h-4 w-4 shrink-0 text-black/30" />
                  <span className="leading-6">{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div data-scroll-rise className="scroll-rise bg-white p-8" style={revealDelay(160)}>
            <p className="text-sm font-bold uppercase tracking-[0.2em] text-brand">After</p>
            <h3 className="mt-2 text-xl font-black text-black">ESM SCM</h3>
            <ul className="mt-5 space-y-3">
              {afterItems.map((item) => (
                <li key={item} className="flex items-start gap-3 text-black">
                  <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-brand" />
                  <span className="leading-6">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="bg-black py-20 text-white">
        <div className="mx-auto max-w-7xl px-6">
          <div
            data-scroll-rise
            className="scroll-rise flex flex-col items-start gap-8 border-l-4 border-brand pl-8 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <p className="text-sm font-bold uppercase tracking-[0.2em] text-brand">Get Started</p>
              <h2 className="mt-3 text-3xl font-black tracking-tight">지금 바로 발주와 시장 분석을 시작하세요</h2>
              <p className="mt-3 max-w-xl leading-7 text-white/75">
                분석 시작만 누르면 발주 필요 여부와 리스크는 물론 국가·브랜드·SKU별 인사이트까지 확인할 수 있습니다.
              </p>
            </div>
            <Link
              href="/upload"
              className={cn(
                buttonVariants({ size: "lg" }),
                "group shrink-0 rounded-full bg-brand px-7 text-white hover:bg-brand-dark",
              )}
            >
              데이터 입력 시작 <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
