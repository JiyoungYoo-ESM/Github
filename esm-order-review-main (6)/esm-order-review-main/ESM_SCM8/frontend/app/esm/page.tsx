import type { Metadata } from "next";
import { LandingNav } from "@/components/landing/LandingNav";

export const metadata: Metadata = {
  title: "ESM | Silicon2 ESM SCM",
  description: "ESM 팀의 일하는 방식과 팀 스피릿 소개",
};

const values = [
  {
    label: "Be rare",
    title: "귀한 팀",
    desc: "대체 불가능한 전문성과 인격. 직무를 수행하는 것을 넘어 귀한 팀이 되는 것.",
  },
  {
    label: "Earn trust",
    title: "신뢰를 얻는 팀",
    desc: '본사, 유럽법인, 브랜드사가 "ESM에 맡기면 안심이다"라고 믿게 하는 것.',
  },
  {
    label: "Make profit",
    title: "이윤을 창출하는 팀",
    desc: "SCM 최적화로 비용을 절감하고 매출을 극대화해 팀의 존재 가치를 성과로 증명.",
  },
  {
    label: "Seek higher purpose",
    title: "높은 목적을 가진 팀",
    desc: "K-뷰티의 확산과 사회적 가치 기여라는 큰 꿈을 팀 전체가 공유하는 것.",
  },
  {
    label: "Go the extra mile",
    title: "엑스트라 마일",
    desc: "기대받은 수준을 넘어, 상대방이 감동할 디테일을 추가로 내놓는 팀.",
  },
  {
    label: "Be honest",
    title: "투명한 팀",
    desc: "모든 수치와 정보를 정직하고 투명하게. 게으름 없이, 숨김 없이.",
  },
];

const principles = [
  {
    number: "01",
    title: "데이터는 거짓말하지 않는다",
    desc: "모르는 수치나 예측 실패를 숨기지 않습니다. 즉시 공유해 재고 리스크를 방지하는 것이 SCM에서 가장 용기 있는 행동입니다. '괜찮겠지'라는 막연한 추측이 가장 위험한 적입니다.",
  },
  {
    number: "02",
    title: "기존 관행을 의심하라",
    desc: '"예전부터 이렇게 했어요"는 ESM팀에 독입니다. 유럽 현지 수요와 물류 리드타임의 본질에서 다시 계산합니다. 현지 창고 회전율과 운송 비용의 물리적 한계를 밑바닥부터 재검토합니다.',
  },
  {
    number: "03",
    title: "본사와 지사의 시차를 없애라",
    desc: "정보가 특정인에게 고이면 의사결정이 느려집니다. 팀원 전체가 같은 수치를 같은 시간에 보는 것이 목표입니다. 사고가 터졌을 때 누구나 즉각적인 대응이 가능한 구조를 만듭니다.",
  },
  {
    number: "04",
    title: "품질보다 빠른 수정",
    desc: "완벽한 분석을 기다리다 품절이 나면 고객은 떠납니다. 80% 확신으로 먼저 움직이고, 시장 반응에 따라 매주 조정합니다. 성장하는 시장은 변동성이 크다는 것을 항상 전제합니다.",
  },
  {
    number: "05",
    title: "기존 주력에 안주하지 말 것",
    desc: "특정 브랜드 하나에 의존하는 SCM 구조는 리스크입니다. 스스로를 파괴하고 새로운 포트폴리오를 뿌리내릴 때 팀의 가치가 증명됩니다. 편한 운영 방식을 끊임없이 개선합니다.",
  },
];

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="mb-7 flex items-center gap-4">
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-about-faint">{label}</p>
      <span className="h-px flex-1 bg-about-line" />
    </div>
  );
}

export default function EsmPage() {
  return (
    <main className="min-h-screen bg-about-bg text-about-ink">
      <LandingNav />

      <section>
        <div className="mx-auto max-w-[960px] px-6 pb-16 pt-24 max-sm:pt-16">
          <div className="flex items-center gap-3">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-about-accent">Team Spirit</p>
            <span className="h-px w-10 bg-about-accent" />
          </div>

          <h1 className="mt-6 text-[36px] font-light leading-[1.15] tracking-normal text-about-black sm:text-[56px]">
            우리는 왜,
            <span className="block">
              <strong className="font-semibold">어떻게</strong> 일하는가
            </span>
          </h1>

          <p className="mt-6 max-w-[560px] text-[17px] leading-[1.75] text-about-muted">
            ESM팀은 단순히 발주를 처리하는 조직이 아닙니다. K-뷰티가 유럽에 뿌리내리는 과정에서,
            데이터로 판단하고 사람으로 신뢰를 쌓는 팀입니다.
          </p>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[960px] px-6 py-16">
          <div className="rounded-lg bg-about-black px-8 py-10 text-white sm:px-10 sm:py-12">
            <div>
              <p className="text-[19px] font-light leading-[1.55] tracking-normal text-white sm:text-[24px]">
              &quot;추측으로 일하지 않고
              <span className="block font-semibold text-about-warm">데이터로 대화하며,</span>
              완벽한 계획보다
              <span className="block">멈추지 않는 흐름을 만든다.&quot;</span>
              </p>
              <p className="mt-8 text-[11px] font-medium uppercase tracking-[0.18em] text-white/60">
                ESM Team Manifesto
              </p>
            </div>

            <div className="mt-8 border-t border-white/15 pt-7 text-[15px] leading-[1.8] text-white/72">
              <p>
                SCM에서 가장 위험한 건 &apos;괜찮겠지&apos;라는 막연한 추측입니다. 수치가 불편하더라도 즉시 공유하고,
                완벽한 분석을 기다리기보다 80% 확신으로 먼저 움직이고 실시간으로 조정합니다.
              </p>
              <p className="mt-5">멈추지 않는 흐름 — 그것이 ESM의 생명입니다.</p>
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[960px] px-6 py-16">
          <SectionHeader label="핵심 가치" />
          <div className="grid overflow-hidden rounded-lg border border-about-line bg-white md:grid-cols-3">
            {values.map((value, index) => (
              <article
                key={value.label}
                className={[
                  "px-6 py-7",
                  index > 0 ? "border-t border-about-line md:border-t-0" : "",
                  index % 3 !== 0 ? "md:border-l md:border-about-line" : "",
                  index >= 3 ? "md:border-t md:border-about-line" : "",
                ].join(" ")}
              >
                <p className="text-[12px] font-medium uppercase tracking-[0.08em] text-about-accent">{value.label}</p>
                <h2 className="mt-4 text-[17px] font-semibold text-about-black">{value.title}</h2>
                <p className="mt-4 text-[14px] leading-[1.7] text-about-muted">{value.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[960px] px-6 pb-20">
          <SectionHeader label="운영 원칙" />
          <div>
            {principles.map((principle) => (
              <article key={principle.number} className="grid gap-5 border-b border-about-line py-9 md:grid-cols-[56px_1fr]">
                <p className="font-mono text-[13px] font-semibold tracking-[0.14em] text-about-faint">{principle.number}</p>
                <div>
                  <h2 className="text-[19px] font-semibold text-about-black">{principle.title}</h2>
                  <p className="mt-4 text-[15px] leading-[1.8] text-about-muted">{principle.desc}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[960px] px-6 pb-24">
          <div className="rounded-lg border border-about-line bg-white px-8 py-12 text-center shadow-soft sm:px-14">
            <p className="text-[21px] font-semibold leading-[1.7] text-about-black sm:text-[24px]">
              ESM팀은 추측으로 일하지 않고 데이터로 대화하며,
              <span className="block">완벽한 계획보다 멈추지 않는 흐름을 만듭니다.</span>
            </p>
            <p className="mt-8 text-[21px] font-semibold leading-[1.7] text-about-black sm:text-[24px]">
              우리가 잘하면, 협력하는 모든 이가 함께 성공합니다.
            </p>
            <p className="mt-8 text-[11px] font-medium uppercase tracking-[0.18em] text-about-accent">
              ESM Team · K-Beauty Europe SCM
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
