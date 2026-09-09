import { escapeReportHtml, injectReportWatermark } from "../../lib/report-html";

export type ReportBasisRow = readonly [string, string];
export type ReportMetricRow = readonly [string, string, string, string];
export type ReportSummaryRow = readonly [string, string, string[]];

// design-token-audit: report-template-start
const PRINT_LAYOUT_CSS = `
  @page{size:A4;margin:10mm}
  @media print{
    body{background:#fff}
    .page{max-width:none;padding:0}
    .card{overflow:visible;border:0;border-radius:0}
    .hero,.basis-grid,.metrics,.row,.footer{break-inside:avoid;page-break-inside:avoid}
    .rows{padding:6px 0 0}
    .row{padding:12px 8px}
    .footer{margin-top:6px;padding:12px 8px}
  }
`;

export function buildBrandReportPdfHtml({
  brandDisplayName,
  generatedAt,
  fileDate,
  reportBasisRows,
  metricRows,
  summaryRows
}: {
  brandDisplayName: string;
  generatedAt: string;
  fileDate: string;
  reportBasisRows: readonly ReportBasisRow[];
  metricRows: readonly ReportMetricRow[];
  summaryRows: readonly ReportSummaryRow[];
}): string {
  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8" /><title>브랜드 자동 리포트 ${escapeReportHtml(fileDate)}</title><style>@page{size:A4;margin:12mm}*{box-sizing:border-box}body{margin:0;background:#f3f4f6;color:#05060a;font-family:Arial,"Malgun Gothic",sans-serif}.page{max-width:980px;margin:0 auto;padding:24px}.card{overflow:hidden;border:1px solid #e2e4e8;border-radius:16px;background:#fff}.hero{background:#0f1115;color:#fff;padding:28px 32px}.hero-row{display:flex;justify-content:space-between;gap:20px}.eyebrow{font-size:12px;font-weight:900;letter-spacing:.12em;color:#eef0f5}h1{margin:13px 0 0;font-size:30px;line-height:1;font-weight:950}.logo{margin-top:18px;font-size:25px;font-weight:950}.basis-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:14px 16px;border-bottom:1px solid #e8ebef;background:#fafbfc}.basis-card{border:1px solid #e8ebef;border-radius:10px;background:#fff;padding:10px 12px}.basis-label{font-size:10px;font-weight:900;color:#8a92a3}.basis-value{margin-top:5px;font-size:11px;font-weight:900;line-height:1.35}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid #e8ebef}.metric{min-height:96px;border-right:1px solid #e8ebef;padding:18px 22px}.metric:last-child{border-right:0}.label{font-size:12px;font-weight:800;color:#8a92a3}.value{margin-top:7px;font-size:25px;line-height:1;font-weight:950}.caption{margin-top:7px;font-size:10px;font-weight:800;color:#8a92a3}.brand{color:#e90035}.neg{color:#e90035}.rows{padding:10px 16px 14px}.row{display:grid;grid-template-columns:46px 1fr;border-bottom:1px solid #e8ebef;padding:16px}.row:last-child{border-bottom:0}.num{font-size:13px;font-weight:950;color:#e90035}h2{margin:0;font-size:14px;line-height:1;font-weight:950}.body{margin-top:8px;font-size:12px;font-weight:700;color:#69707f}.body span{display:block;line-height:1.55}.body span+span{margin-top:4px}.body .recommendation{margin-top:10px;color:#05060a}.footer{display:flex;justify-content:space-between;gap:20px;border-top:1px solid #e8ebef;padding:17px 24px;font-size:12px;font-weight:800;color:#8a92a3}@media print{body{background:#f3f4f6}.page{padding:0}}</style></head><body><main class="page"><section class="card"><div class="hero"><div class="hero-row"><div><div class="eyebrow">BRAND PERFORMANCE REPORT · CMS DATA</div><h1>${escapeReportHtml(brandDisplayName)}</h1></div><div class="logo">Silicon2</div></div></div><div class="basis-grid">${reportBasisRows.map(([label, value]) => `<div class="basis-card"><div class="basis-label">${escapeReportHtml(label)}</div><div class="basis-value">${escapeReportHtml(value)}</div></div>`).join("")}</div><div class="metrics" style="grid-template-columns:repeat(${Math.max(metricRows.length, 1)},1fr)">${metricRows.map(([label, value, tone, caption]) => `<div class="metric"><div class="label">${escapeReportHtml(label)}</div><div class="value ${tone === "brand" ? "brand" : tone === "neg" ? "neg" : ""}">${escapeReportHtml(value)}</div><div class="caption">${escapeReportHtml(caption)}</div></div>`).join("")}</div><div class="rows">${summaryRows.map(([number, title, bodyLines]) => `<div class="row"><div class="num">${escapeReportHtml(number)}</div><div><h2>${escapeReportHtml(title)}</h2><div class="body">${bodyLines.map((part, lineIndex) => {
    const isRecommendation = part.startsWith("권장 조치:");
    return `<span${isRecommendation ? ` class="recommendation"` : ""}>${lineIndex === 0 || isRecommendation ? "" : `<b style="color:#e6002d;margin-right:6px;">•</b>`}${escapeReportHtml(part)}</span>`;
  }).join("")}</div></div></div>`).join("")}</div><div class="footer"><span>자동 생성 · 실리콘투 SCM Analytics · ${escapeReportHtml(generatedAt)}</span><span>브랜드 미팅 · 내부 보고 즉시 활용</span></div></section></main><script>window.addEventListener("load",()=>{document.title="brand-auto-report-${escapeReportHtml(fileDate)}";setTimeout(()=>{window.focus();window.print();},250);});</script></body></html>`;
  return injectReportWatermark(html)
    .replace("@page{size:A4;margin:12mm}", "@page{size:A4;margin:0}")
    .replace("</style>", `${PRINT_LAYOUT_CSS}</style>`)
    .replace(
      "*{box-sizing:border-box}",
      "*{box-sizing:border-box;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}"
    )
    .replace("@media print{body{background:#f3f4f6}.page{padding:0}}", "@media print{body{background:#f3f4f6}.page{padding:12mm}}");
}
// design-token-audit: report-template-end
