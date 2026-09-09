import { ABOUT_DIAGRAM_COLORS as diagram } from "@/lib/design-tokens";
import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";

const comparisonRows = [
  {
    before: "CMS 데이터를 내려받아 수작업 대조",
    after: "분석 시작 한 번으로 CMS API 데이터 통합",
  },
  {
    before: "SKU별 발주 필요 여부를 눈으로 판단",
    after: "발주 필요 / 긴급 SKU 자동 산출",
  },
  {
    before: "운송 중 물량·ETA를 개별 시트에서 확인",
    after: "미입고·운송중을 한 테이블에서 확인",
  },
  {
    before: INGREDIENT_ANALYSIS_ENABLED ? "브랜드·국가·성분 분석을 별도 시트로" : "브랜드·국가 분석을 별도 시트로",
    after: INGREDIENT_ANALYSIS_ENABLED ? "국가·브랜드·SKU·시즌·성분 탭에서 즉시 전환" : "국가·브랜드·SKU·시즌 탭에서 즉시 전환",
  },
  {
    before: "보고서 작성에 3~4시간",
    after: "브랜드 자동 리포트 → 클릭 한 번으로 PDF 발행",
  },
];

const valueCards = [
  {
    title: "파일 입력 표준화",
    desc: "CMS 데이터를 한번에 모아 재고·발주·SKU 분석에 활용합니다.",
  },
  {
    title: "리스크 중심 의사결정",
    desc: "입고 지연·ETA 누락·재고공백 등 운영 리스크를 전체 SKU 기준으로 확인합니다.",
  },
  {
    title: "기존 양식 유지",
    desc: "기존 산출 구조를 유지하면서 분석 결과만 빠르게 확장합니다.",
  },
];

function SectionLabel({ number }: { number: string }) {
  return (
    <p className="mb-3 flex items-center gap-4 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-about-faint">
      {number}
      <span className="h-px flex-1 bg-about-line" />
    </p>
  );
}

function AboutStructureDiagram() {
  return (
    <svg
      viewBox="0 0 1435 1308"
      role="img"
      aria-labelledby="about-structure-title about-structure-desc"
      className="h-auto w-full rounded-md"
      style={{ fontFamily: "Pretendard, 'Malgun Gothic', sans-serif" }}
    >
      <title id="about-structure-title">ESM SCM 구조도</title>
      <desc id="about-structure-desc">
        CMS API 데이터가 발주 판단과 분석을 거쳐 결과 양식과 보고서로 이어지는 흐름
      </desc>
      <defs>
        <marker id="about-structure-arrow" markerHeight="12" markerWidth="12" orient="auto" refX="10" refY="6">
          <path d="M1 1 L10 6 L1 11" fill="none" stroke={diagram.arrow} strokeLinecap="round" strokeWidth="2.6" />
        </marker>
      </defs>

      <g fill="none" letterSpacing="0" strokeLinecap="round" strokeLinejoin="round">
        <text fill={diagram.heading} fontSize="22" fontWeight="700" textAnchor="middle" x="222" y="72">
          1. 데이터
        </text>
        <text fill={diagram.heading} fontSize="22" fontWeight="700" textAnchor="middle" x="718" y="72">
          2. 작동
        </text>
        <text fill={diagram.heading} fontSize="22" fontWeight="700" textAnchor="middle" x="1269" y="72">
          3. 결과
        </text>
        <path d="M70 96 H1365" stroke={diagram.line} strokeWidth="2" />

        <path
          d="M360 590 L492 318"
          markerEnd="url(#about-structure-arrow)"
          stroke={diagram.arrow}
          strokeWidth="3.2"
        />
        <path
          d="M360 652 L492 900"
          markerEnd="url(#about-structure-arrow)"
          stroke={diagram.arrow}
          strokeWidth="3.2"
        />
        <path
          d="M980 316 H1138"
          markerEnd="url(#about-structure-arrow)"
          stroke={diagram.arrow}
          strokeWidth="3.2"
        />
        <path
          d="M980 928 H1138"
          markerEnd="url(#about-structure-arrow)"
          stroke={diagram.arrow}
          strokeWidth="3.2"
        />

        <rect fill={diagram.neutralSurface} height="192" rx="18" stroke={diagram.neutralBorder} strokeWidth="1.4" width="276" x="84" y="527" />
        <text fill={diagram.heading} fontSize="30" fontWeight="800" textAnchor="middle" x="222" y="600">
          CMS API
        </text>
        <text fill={diagram.heading} fontSize="22" textAnchor="middle" x="222" y="642">
          판매·재고
        </text>
        <text fill={diagram.heading} fontSize="22" textAnchor="middle" x="222" y="677">
          운송·미입고
        </text>
        <text fill={diagram.neutralText} fontSize="22" fontWeight="700" textAnchor="middle" x="222" y="760">
          업로드 없이 자동 연동
        </text>

        <rect fill={diagram.orderSurface} height="318" rx="24" stroke={diagram.orderBorder} strokeWidth="1.7" width="488" x="494" y="155" />
        <text fill={diagram.primaryText} fontSize="30" fontWeight="800" textAnchor="middle" x="738" y="214">
          발주 — 무엇을 발주할까
        </text>
        <path d="M528 233 H946" stroke={diagram.orderDivider} strokeWidth="2" />
        <text fill={diagram.bodyText} fontSize="22" textAnchor="middle" x="738" y="283">
          <tspan x="738">기준값·리드타임·환율 입력</tspan>
          <tspan dy="40" x="738">발주 필요량·긴급 SKU 자동 산출</tspan>
          <tspan dy="40" x="738">미입고 해소 전/후 비교</tspan>
          <tspan dy="40" x="738">재고 공백 포착</tspan>
          <tspan dy="38" x="738">전체 SKU를 한 화면에서</tspan>
        </text>

        <rect fill={diagram.qualitySurface} height="184" rx="17" stroke={diagram.qualityBorder} strokeWidth="1.7" width="488" x="494" y="516" />
        <text fill={diagram.qualityHeading} fontSize="30" fontWeight="800" textAnchor="middle" x="738" y="574">
          데이터 점검
        </text>
        <text fill={diagram.qualityText} fontSize="22" textAnchor="middle" x="738" y="621">
          {INGREDIENT_ANALYSIS_ENABLED ? "미분류 SKU·성분·권역 정리" : "미분류 SKU·권역 정리"}
        </text>
        <text fill={diagram.qualityText} fontSize="22" textAnchor="middle" x="738" y="674">
          발주·분석 정확도를 함께 끌어올림
        </text>

        <rect fill={diagram.insightSurface} height="363" rx="20" stroke={diagram.insightBorder} strokeWidth="1.7" width="488" x="494" y="752" />
        <text fill={diagram.primaryText} fontSize="30" fontWeight="800" textAnchor="middle" x="738" y="812">
          분석 — 어디서·무엇이 뜰까
        </text>
        <path d="M528 833 H946" stroke={diagram.insightDivider} strokeWidth="2" />
        <text fill={diagram.bodyText} fontSize="22" textAnchor="middle" x="738" y="883">
          <tspan x="738">국가별 잘 팔리는 시장</tspan>
          <tspan dy="39" x="738">브랜드별 매출 집중·국가 분포</tspan>
          <tspan dy="39" x="738">SKU 계절성·발주 시점</tspan>
          <tspan dy="39" x="738">시즌 수요 신호 확인</tspan>
          <tspan dy="39" x="738">{INGREDIENT_ANALYSIS_ENABLED ? "성분 트렌드·교차분석" : "국가·브랜드·SKU 교차분석"}</tspan>
          <tspan dy="37" x="738">같은 데이터를 각도만 바꿔서</tspan>
        </text>

        <rect fill={diagram.neutralSurface} height="142" rx="18" stroke={diagram.neutralBorder} strokeWidth="1.4" width="250" x="1144" y="246" />
        <text fill={diagram.heading} fontSize="30" fontWeight="800" textAnchor="middle" x="1269" y="306">
          결과
        </text>
        <text fill={diagram.heading} fontSize="22" textAnchor="middle" x="1269" y="356">
          기존 양식 그대로
        </text>

        <rect fill={diagram.reportSurface} height="202" rx="18" stroke={diagram.reportBorder} strokeWidth="1.7" width="250" x="1144" y="827" />
        <text fill={diagram.reportText} fontSize="30" fontWeight="800" textAnchor="middle" x="1269" y="889">
          보고서
        </text>
        <text fill={diagram.reportText} fontSize="22" textAnchor="middle" x="1269" y="944">
          PDF·PPT
        </text>
        <text fill={diagram.reportText} fontSize="22" textAnchor="middle" x="1269" y="996">
          클릭 한 번 발행
        </text>

        <path d="M70 1180 H1365" stroke={diagram.line} strokeWidth="2" />
        <text fill={diagram.heading} fontSize="22" fontWeight="600" textAnchor="middle" x="718" y="1230">
          하나의 데이터 연동에서 발주 실행과 시장 통찰이 동시에 — 판단부터 공유까지 한 흐름
        </text>
      </g>
    </svg>
  );
}

export function AboutContent() {
  return (
    <div className="min-h-screen bg-about-bg text-about-ink">
      <section id="intro" className="mx-auto max-w-[960px] px-6 pb-16 pt-24 max-sm:px-6 max-sm:pt-16">
        <p className="mb-6 flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.18em] text-about-accent">
          웹 소개
          <span className="h-px w-10 bg-about-accent" />
        </p>

        <h1 className="text-[36px] font-light leading-[1.15] tracking-normal text-about-black sm:text-[56px]">
          발주 검토와 시장 분석을
          <br />
          <strong className="font-semibold">한 화면</strong>에서
        </h1>
        <p className="mt-5 text-[18px] font-medium tracking-normal text-about-accent">
          One View. Clear Decisions.
        </p>
        <p className="mt-6 max-w-[560px] text-[17px] leading-[1.75] text-about-muted">
          흩어진 데이터와 씨름하던 발주 판단을, 모든 신호가 모인 하나의 화면으로. ESM SCM은 기존 업무
          흐름은 그대로 두되 판단 속도만 끌어올립니다.
        </p>
      </section>

      <section id="why" className="mx-auto max-w-[960px] px-6 py-16 max-sm:px-6">
        <SectionLabel number="01" />
        <h2 className="text-[24px] font-medium leading-[1.3] text-about-black sm:text-[32px]">왜 만들었는가</h2>

        <div className="mt-6 space-y-4 text-[16px] leading-[1.7] text-about-ink">
          <p className="font-medium text-about-black">발주 판단은 늘 흩어진 데이터와의 싸움이었습니다.</p>
          <p className="text-about-muted">
            CMS에서 판매·재고 데이터를 다운로드 후 수작업으로 대조하고, SKU별 발주 필요 여부를
            눈으로 판단하고, 운송 중 물량과 ETA는 시트를 따로 열어 확인해야 했습니다. 같은 정보를 보는데도
            사람마다, 시트마다 기준이 달랐고, 판단까지 걸리는 시간이 의사결정의 속도를 발목 잡았습니다.
          </p>
          <blockquote className="my-8 border-l-[3px] border-about-accent py-2 pl-6 text-[18px] font-normal leading-[1.5] text-about-black sm:text-[22px]">
            &quot;기존 업무 흐름은 그대로 두되, 판단 속도만 끌어올리자.&quot;
          </blockquote>
          <p className="text-about-muted">
            기존 양식을 버리라는 게 아니라, 판단에 필요한 모든 신호 — 재고, 운송, 미입고, ETA, 리스크 — 를
            한 화면(One View)에 모으고, 발주 필요/불필요와 우선순위를 자동으로 산출해주는 것이 목표입니다.
          </p>
        </div>
      </section>

      <section id="change" className="mx-auto max-w-[960px] px-6 py-16 max-sm:px-6">
        <SectionLabel number="02" />
        <h2 className="text-[24px] font-medium leading-[1.3] text-about-black sm:text-[32px]">무엇이 달라지는가</h2>

        <div className="mt-6 overflow-hidden rounded-lg border border-about-line bg-white">
          <div className="grid grid-cols-2 bg-about-surface text-left text-[12px] font-semibold uppercase tracking-[0.04em] max-sm:grid-cols-1">
            <div className="px-5 py-4 text-about-muted">기존 방식</div>
            <div className="px-5 py-4 text-about-accentDark max-sm:border-t max-sm:border-about-line">ESM SCM</div>
          </div>
          {comparisonRows.map((row) => (
            <div
              key={row.before}
              className="grid grid-cols-2 border-t border-about-line text-[14px] leading-[1.6] max-sm:grid-cols-1"
            >
              <div className="px-5 py-4 text-about-muted">{row.before}</div>
              <div className="px-5 py-4 font-medium text-about-ink max-sm:border-t max-sm:border-about-line">
                {row.after}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 grid overflow-hidden rounded-lg border border-about-line bg-about-line md:grid-cols-3">
          {valueCards.map((card) => (
            <div key={card.title} className="bg-white px-5 py-6">
              <h3 className="text-[15px] font-medium text-about-black">{card.title}</h3>
              <p className="mt-2 text-[13px] leading-[1.6] text-about-muted">{card.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="structure" className="mx-auto max-w-[960px] px-6 py-16 max-sm:px-6">
        <SectionLabel number="03" />
        <h2 className="text-[24px] font-medium leading-[1.3] text-about-black sm:text-[32px]">
          전체 구조 한눈에 보기
        </h2>
        <p className="mt-6 text-[16px] leading-[1.7] text-about-muted">
          하나의 데이터 연동에서 발주 실행과 시장 통찰이 동시에 — 판단부터 공유까지 끊김 없는 한 흐름입니다.
        </p>
        <figure className="mt-8 rounded-lg border border-about-line bg-about-surface p-8 text-center max-sm:p-5">
          <AboutStructureDiagram />
          <figcaption className="mt-4 text-[12px] tracking-[0.04em] text-about-faint">
            데이터 연동에서 발주·분석으로, 다시 결과·보고서 발행까지
          </figcaption>
        </figure>
      </section>

      <section id="future" className="mx-auto max-w-[960px] px-6 py-16 max-sm:px-6">
        <SectionLabel number="04" />
        <h2 className="text-[24px] font-medium leading-[1.3] text-about-black sm:text-[32px]">
          최종적으로 그리는 미래
        </h2>
        <div className="mt-6 space-y-4 text-[16px] leading-[1.7] text-about-ink">
          <p>이 도구가 지향하는 끝은 단순한 발주 보조 도구가 아닙니다.</p>
          <p className="text-about-muted">
            지금은 CMS에서 데이터를 가져와 분석합니다. 하지만 팀이 그리는 최종 그림은 다릅니다. 발주 판단,
            시장 분석, 국가별 수요, 보고서 발행 — 지금 여러 시스템을 오가며 하던 모든 판단을
            ESM SCM 하나에서 끝내는 것입니다.
          </p>
        </div>
        <div className="my-8 rounded-lg bg-about-black px-10 py-12 max-sm:px-6 max-sm:py-8">
          <p className="text-[19px] font-normal leading-[1.5] text-white sm:text-[24px]">
            <em className="not-italic text-about-warm">
              &quot;{INGREDIENT_ANALYSIS_ENABLED ? "국가 × 브랜드 × SKU × 성분 × 시즌" : "국가 × 브랜드 × SKU × 시즌"}을 가로지르는 하나의 뷰&quot;
            </em>
          </p>
          <p className="mt-4 text-[14px] leading-[1.8] text-white">
            어떤 시스템도 이 조합을 한 화면에서 보여주지 않습니다. ESM만이 가능합니다. 데이터가 쌓일수록,
            데이터 기준이 정교해질수록, 사용자가 여기서 먼저 답을 찾는 습관이 생길수록 — 이 도구는 점점 더
            유일한 판단 기준이 됩니다.
          </p>
        </div>
      </section>

    </div>
  );
}
