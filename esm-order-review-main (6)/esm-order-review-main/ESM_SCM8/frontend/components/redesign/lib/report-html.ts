export function escapeReportHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// design-token-audit: report-template-start
const REPORT_WATERMARK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="320"><g transform="rotate(-30 160 160)" font-family="Arial, sans-serif" fill="#05060a"><text x="10" y="150" font-size="26" font-weight="900" letter-spacing="1">SILICON2</text><text x="10" y="176" font-size="12" font-weight="700" letter-spacing="1">CONFIDENTIAL · 내부용</text></g></svg>';
// design-token-audit: report-template-end

const REPORT_WATERMARK_BACKGROUND_URL = `data:image/svg+xml,${encodeURIComponent(REPORT_WATERMARK_SVG)}`;

export const REPORT_WATERMARK_STYLE = `.report-watermark{position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;pointer-events:none;opacity:.05;background-image:url('${REPORT_WATERMARK_BACKGROUND_URL}');background-repeat:repeat;background-position:center}@media print{.report-watermark{opacity:.06;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}}`;

export const REPORT_WATERMARK_MARKUP = '<div class="report-watermark" aria-hidden="true"></div>';

export function injectReportWatermark(html: string): string {
  return html
    .replace("</style>", `${REPORT_WATERMARK_STYLE}</style>`)
    .replace("<body>", `<body>${REPORT_WATERMARK_MARKUP}`);
}
