import type { Metadata } from "next";
import { LandingNav } from "@/components/landing/LandingNav";
import { AboutContent } from "./AboutContent";

export const metadata: Metadata = {
  title: "소개 | Silicon2 ESM SCM",
  description: "발주 검토와 시장 분석을 한 화면에서 확인하는 Silicon2 ESM SCM 소개",
};

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-about-bg text-about-ink">
      <LandingNav />
      <AboutContent />
    </main>
  );
}
