export const chartColors = {
  brand: "#e6002d",
  brandDark: "#b80024",
  blue: "#2563eb",
  blueDark: "#1d4ed8",
  green: "#059669",
  amber: "#d97706",
  orange: "#f97316",
  purple: "#7c3aed",
  pink: "#db2777",
  cyan: "#0891b2",
  lime: "#65a30d",
  slate: "#475569",
  slateLight: "#94a3b8",
  slateMuted: "#64748b",
  slatePale: "#cbd5e1",
  line: "#e2e8f0",
  black: "#000000",
  white: "#ffffff"
} as const;

export const dashboardBarColors = [
  chartColors.blueDark,
  chartColors.blue,
  chartColors.slateMuted,
  chartColors.slateLight,
  chartColors.slatePale
];

export const trendLineColors = [
  chartColors.brand,
  chartColors.blue,
  chartColors.green,
  chartColors.amber,
  chartColors.purple,
  chartColors.pink,
  chartColors.cyan,
  chartColors.lime,
  chartColors.slate,
  "#b45309"
];

export const mapShareColors = {
  selected: "#ef4444",
  selectedStroke: "#dc2626",
  selectedOutline: "#b91c1c",
  hovered: "#f87171",
  muted: "#e5e7eb",
  high: "#f87171",
  medium: "#fca5a5",
  low: "#fecaca",
  none: "#f1f5f9"
} as const;

export function rgba(rgb: string, alpha: number) {
  return `rgba(${rgb}, ${alpha})`;
}

export const chartRgb = {
  brand: "230, 0, 45",
  blue: "37, 99, 235",
  blueDark: "29, 78, 216",
  slate: "100, 116, 139",
  teal: "20, 184, 166",
  tealDark: "15, 118, 110"
} as const;
