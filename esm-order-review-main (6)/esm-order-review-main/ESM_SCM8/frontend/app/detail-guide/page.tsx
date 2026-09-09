import type { Metadata } from "next";
import Script from "next/script";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { applyIngredientAvailabilityToGuide } from "@/lib/ingredient-availability";
import { LandingNav } from "@/components/landing/LandingNav";

const guideHref = "/docs/esm-scm-detail-guide-v10.html?v=14";
const guideFileName = "ESM_SCM_상세가이드_다운로드용_v14.html";

export const metadata: Metadata = {
  title: "상세가이드 | Silicon2 ESM SCM",
  description: "ESM SCM 데이터 출처와 계산 로직 상세 가이드",
};

const guideStyles = `
.manual-doc {
  --manual-black: var(--text-strong);
  --manual-ink: var(--text-700);
  --manual-muted: var(--text-3);
  --manual-faint: var(--muted-2);
  --manual-line: var(--border);
  --manual-bg: var(--surface);
  --manual-surface: var(--surface-soft);
  --manual-accent: #c0392b;
  --manual-accent-strong: #8b2520;
  --manual-teal: #0f6e56;
  --manual-blue: #185fa5;
  --manual-amber: #854f0b;
  --accent: var(--manual-accent);
  --accent-strong: var(--manual-accent-strong);
  --teal: var(--manual-teal);
  --blue: var(--manual-blue);
  --amber: var(--manual-amber);
  background: var(--manual-bg);
  color: var(--manual-ink);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
  text-rendering: geometricPrecision;
  word-break: keep-all;
}

.manual-doc,
.manual-doc * {
  box-sizing: border-box;
  letter-spacing: 0;
}

.manual-doc .layout {
  max-width: 1100px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 3rem;
  padding: 6rem 2rem 4rem;
}

.manual-doc .toc {
  position: sticky;
  top: 178px;
  align-self: start;
  max-height: calc(100vh - 196px);
  overflow-y: auto;
  font-size: 13px;
}

.manual-doc .toc-title {
  margin-bottom: 1rem;
  color: var(--manual-faint);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.manual-doc .toc ul,
.manual-doc ul.bullets,
.manual-doc ol.steps {
  margin: 0;
  padding: 0;
  list-style: none;
}

.manual-doc .toc > ul > li > a {
  display: block;
  padding: 0.35rem 0;
  color: var(--manual-ink);
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s ease;
}

.manual-doc .toc ul ul {
  margin: 0.2rem 0 0.6rem 0.75rem;
  border-left: 1px solid var(--manual-line);
}

.manual-doc .toc ul ul a {
  display: block;
  padding: 0.2rem 0 0.2rem 0.75rem;
  color: var(--manual-muted);
  text-decoration: none;
  font-size: 12px;
  transition: color 0.2s ease;
}

.manual-doc .toc a:hover,
.manual-doc .content a:hover {
  color: var(--manual-accent);
}

.manual-doc .content {
  min-width: 0;
}

.manual-doc [id] {
  scroll-margin-top: 178px;
}

.manual-doc .doc-header {
  margin-bottom: 4rem;
}

.manual-doc .eyebrow {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
  color: var(--manual-accent);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.manual-doc .eyebrow::after {
  content: "";
  flex: 1;
  max-width: 40px;
  height: 1px;
  background: var(--manual-accent);
}

.manual-doc .doc-title {
  color: var(--manual-black);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: clamp(2.25rem, 4.4vw, 3.5rem);
  font-weight: 300;
  letter-spacing: 0;
  line-height: 1.15;
}

.manual-doc .doc-title strong {
  font-weight: 600;
}

.manual-doc .doc-sub {
  margin-top: 1rem;
  color: var(--manual-muted);
  font-size: 16px;
  line-height: 1.75;
}

.manual-doc .guide-actions {
  margin-top: 1.35rem;
}

.manual-doc .download-link {
  display: inline-flex;
  min-height: 40px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--manual-accent-strong);
  border-radius: 999px;
  padding: 0 1.1rem;
  background: var(--manual-accent-strong);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  text-decoration: none;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.manual-doc .download-link:hover {
  border-color: var(--manual-accent);
  background: var(--manual-accent);
  color: #fff;
}

.manual-doc h2.module {
  margin: 3.5rem 0 0.5rem;
  padding-top: 1.5rem;
  border-top: 2px solid var(--manual-black);
  color: var(--manual-black);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 1.5rem;
  font-weight: 500;
  letter-spacing: 0;
  line-height: 1.3;
}

.manual-doc h2.module:first-of-type {
  margin-top: 0;
}

.manual-doc .module-tag {
  margin-bottom: 1.5rem;
  color: var(--manual-accent);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.manual-doc h3.screen {
  margin: 2.5rem 0 0.75rem;
  color: var(--manual-black);
  font-size: 1.15rem;
  font-weight: 500;
}

.manual-doc h4.sub {
  margin: 1.5rem 0 0.5rem;
  color: var(--manual-accent-strong);
  font-size: 0.95rem;
  font-weight: 500;
}

.manual-doc p {
  margin: 0 0 0.75rem;
  color: var(--manual-ink);
  font-size: 15px;
}

.manual-doc .lead {
  margin: 0.75rem 0 1.25rem;
  border-left: 3px solid var(--manual-line);
  padding-left: 1rem;
  color: var(--manual-muted);
  font-size: 15px;
  font-style: italic;
}

.manual-doc .note {
  margin: 0.5rem 0;
  color: var(--manual-faint);
  font-size: 13px;
}

.manual-doc table.t {
  width: 100%;
  margin: 1rem 0 1.5rem;
  overflow: hidden;
  border: 1px solid var(--manual-line);
  border-collapse: separate;
  border-spacing: 0;
  border-radius: 10px;
  background: white;
  font-size: 14px;
}

.manual-doc table.t th {
  padding: 0.7rem 1rem;
  background: var(--manual-surface);
  color: var(--manual-muted);
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-align: left;
  text-transform: uppercase;
}

.manual-doc table.t td {
  border-top: 1px solid var(--manual-line);
  padding: 0.6rem 1rem;
  color: var(--manual-ink);
  vertical-align: top;
}

.manual-doc table.t td:first-child {
  color: var(--manual-ink);
  font-weight: 500;
  white-space: nowrap;
}

.manual-doc table.t td.desc {
  color: var(--manual-muted);
  font-weight: 400;
  white-space: normal;
}

.manual-doc .doc-sub a,
.manual-doc table.t a,
.manual-doc .tip a,
.manual-doc .lead a,
.manual-doc .note a {
  color: var(--manual-accent-strong);
  text-decoration: none;
}

.manual-doc .doc-sub a {
  font-weight: 600;
}

.manual-doc ul.bullets {
  margin: 0.75rem 0 1.5rem;
}

.manual-doc ul.bullets li {
  position: relative;
  padding: 0.35rem 0 0.35rem 1.25rem;
  color: var(--manual-ink);
  font-size: 14px;
  line-height: 1.6;
}

.manual-doc ul.bullets li::before {
  content: "-";
  position: absolute;
  left: 0;
  color: var(--manual-accent);
}

.manual-doc ol.steps {
  counter-reset: manual-step;
  margin: 0.75rem 0 1.5rem;
}

.manual-doc ol.steps li {
  position: relative;
  counter-increment: manual-step;
  padding: 0.45rem 0 0.45rem 2.4rem;
  color: var(--manual-ink);
  font-size: 14.5px;
  line-height: 1.65;
}

.manual-doc ol.steps li::before {
  content: counter(manual-step);
  position: absolute;
  left: 0;
  top: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.6rem;
  height: 1.6rem;
  border-radius: 999px;
  background: var(--manual-accent);
  color: white;
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 12px;
  font-weight: 600;
}

.manual-doc ol.steps li b,
.manual-doc .tip b {
  color: var(--manual-accent-strong);
}

.manual-doc .tip {
  margin: 1rem 0 1.5rem;
  border: 1px solid #f0d5cf;
  border-radius: 10px;
  background: #fdf3f1;
  padding: 0.9rem 1.15rem;
  color: var(--manual-ink);
  font-size: 14px;
}

.manual-doc .word,
.manual-doc .srcbox {
  margin: 1rem 0 1.5rem;
  border: 1px solid var(--manual-line);
  border-radius: 10px;
  background: var(--manual-surface);
  padding: 0.9rem 1.15rem;
  color: var(--manual-muted);
  font-size: 13.5px;
}

.manual-doc .word b {
  color: var(--manual-ink);
}

.manual-doc .srcbox {
  border-color: #cbdcee;
  background: #eff4fa;
}

.manual-doc .srcbox b {
  color: var(--manual-blue);
}

.manual-doc code {
  border: 1px solid var(--manual-line);
  border-radius: 5px;
  background: var(--manual-surface);
  padding: 1px 6px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12.5px;
}

.manual-doc .calc {
  margin: 1rem 0 1.5rem;
  border: 1px solid var(--manual-line);
  border-radius: 12px;
  background: #fff;
  padding: 1.25rem 1.4rem;
}

.manual-doc .calc-title {
  margin-bottom: 0.3rem;
  color: var(--manual-black);
  font-size: 15px;
  font-weight: 700;
}

.manual-doc .calc-why {
  margin-bottom: 0.75rem;
  color: var(--manual-muted);
  font-size: 13.5px;
}

.manual-doc .calc-f {
  margin-bottom: 0.75rem;
  border: 1px solid var(--manual-line);
  border-radius: 8px;
  background: var(--manual-surface);
  padding: 0.7rem 1rem;
  color: var(--manual-black);
  font-size: 15px;
  font-weight: 500;
  text-align: center;
}

.manual-doc .calc-f b {
  color: var(--manual-accent);
}

.manual-doc .calc-ex {
  border: 1px solid #ede4c8;
  border-radius: 8px;
  background: #fbf8ef;
  padding: 0.6rem 1rem;
  color: var(--manual-ink);
  font-size: 13.5px;
}

.manual-doc .calc-ex b {
  color: var(--manual-amber);
}

.manual-doc .src {
  display: inline-block;
  margin: 1px 2px 1px 0;
  border-radius: 10px;
  padding: 1px 8px;
  font-family: "Pretendard", "Pretendard Variable", "Inter", sans-serif;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.manual-doc .s-mi { background: #e8f1fa; color: #185fa5; }
.manual-doc .s-eu { background: #e6f3ee; color: #0f6e56; }
.manual-doc .s-un { background: #f1eaf9; color: #6d3fb0; }
.manual-doc .s-sko { background: #fbeee4; color: #a34e12; }
.manual-doc .s-sale { background: #fbf3d9; color: #854f0b; }
.manual-doc .s-item { background: #e5f4f4; color: #0c7d80; }
.manual-doc .s-calc { background: #fbeae7; color: #c0392b; }
.manual-doc .s-ui { background: #edece8; color: #5f5e5a; }
.manual-doc .s-fx { background: #e9edf9; color: #3d51b5; }

@media (max-width: 840px) {
  .manual-doc .layout {
    grid-template-columns: 1fr;
    gap: 0;
    padding: 4rem 1.25rem 3rem;
  }

  .manual-doc .toc {
    display: none;
  }

  .manual-doc table.t {
    display: block;
    overflow-x: auto;
  }
}
`;

function getGuideMarkup() {
  const html = readFileSync(join(process.cwd(), "public", "docs", "esm-scm-detail-guide-v10.html"), "utf8");
  const body = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i)?.[1] ?? html;
  const downloadAction = `<div class="guide-actions"><a class="download-link" href="${guideHref}" download="${guideFileName}">HTML 다운로드</a></div>`;

  return applyIngredientAvailabilityToGuide(body
    .replace(/<nav[\s\S]*?<\/nav>/i, "")
    .replace(/<footer[\s\S]*?<\/footer>/i, "")
    .replace(/<main([^>]*)class="content"([^>]*)>/i, "<div$1class=\"content\"$2>")
    .replace(/<\/main>/i, "</div>")
    .replace(/(<p class="doc-sub">[\s\S]*?<\/p>)/i, `$1\n${downloadAction}`));
}

export default function DetailGuidePage() {
  const guideMarkup = getGuideMarkup();

  return (
    <main className="min-h-screen bg-about-bg text-about-ink">
      <LandingNav />
      <style>{guideStyles}</style>
      <section className="manual-doc" dangerouslySetInnerHTML={{ __html: guideMarkup }} />
      <Script id="detail-guide-hash-scroll" strategy="afterInteractive">
        {`
          (() => {
            const scrollToHash = () => {
              const hash = decodeURIComponent(window.location.hash.slice(1));
              if (!hash) return;
              const target = document.getElementById(hash);
              if (target) target.scrollIntoView({ block: "start" });
            };

            window.requestAnimationFrame(scrollToHash);
            window.addEventListener("hashchange", scrollToHash);
          })();
        `}
      </Script>
    </main>
  );
}
