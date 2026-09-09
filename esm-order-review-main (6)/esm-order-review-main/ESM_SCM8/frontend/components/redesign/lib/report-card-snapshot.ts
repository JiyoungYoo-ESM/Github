import type { ReportBlock } from "./types";

export const REPORT_CARD_SNAPSHOT_ATTR = "data-report-card-snapshot";
let lastReportCardClickTarget: HTMLElement | null = null;

export function rememberReportCardClickTarget(event: MouseEvent | PointerEvent) {
  const target = event.target;
  lastReportCardClickTarget = target instanceof HTMLElement ? target : null;
}

function removeInteractiveReportControls(root: HTMLElement) {
  root.querySelectorAll("button, select, input, textarea, [role='button']").forEach((element) => element.remove());
}

function cssName(property: string) {
  return property.replace(/[A-Z]/g, (match) => `-${match.toLowerCase()}`);
}

function copyComputedStyles(source: Element, target: Element) {
  if (!(source instanceof HTMLElement) || !(target instanceof HTMLElement)) return;
  const computed = window.getComputedStyle(source);
  const importantProperties = [
    "display",
    "position",
    "boxSizing",
    "width",
    "minWidth",
    "maxWidth",
    "height",
    "minHeight",
    "maxHeight",
    "margin",
    "padding",
    "border",
    "borderRadius",
    "background",
    "backgroundColor",
    "boxShadow",
    "color",
    "font",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "lineHeight",
    "letterSpacing",
    "textAlign",
    "textDecoration",
    "textTransform",
    "whiteSpace",
    "overflow",
    "textOverflow",
    "gridTemplateColumns",
    "gridTemplateRows",
    "gridColumn",
    "gridRow",
    "gap",
    "alignItems",
    "alignContent",
    "justifyContent",
    "justifyItems",
    "flexDirection",
    "flexWrap",
    "alignSelf",
    "justifySelf",
    "objectFit",
    "opacity"
  ];
  target.setAttribute("style", importantProperties.map((property) => `${cssName(property)}:${computed.getPropertyValue(property)};`).join(""));
  Array.from(source.children).forEach((child, index) => {
    const targetChild = target.children.item(index);
    if (targetChild) copyComputedStyles(child, targetChild);
  });
}

function likelyReportCardContainers() {
  return Array.from(document.querySelectorAll("div, section, article")).filter((element): element is HTMLElement => {
    if (!(element instanceof HTMLElement)) return false;
    const className = element.getAttribute("class") ?? "";
    return (
      className.includes("rounded-[16px]") &&
      (className.includes("bg-surface") || className.includes("shadow-soft") || className.includes("border-border"))
    );
  });
}

function nearestReportCardElement(block?: ReportBlock): HTMLElement | null {
  if (lastReportCardClickTarget) {
    const marked = lastReportCardClickTarget.closest(`[${REPORT_CARD_SNAPSHOT_ATTR}]`);
    if (marked instanceof HTMLElement) return marked;

    let current: HTMLElement | null = lastReportCardClickTarget;
    for (let depth = 0; current && depth < 8; depth += 1) {
      const className = current.getAttribute("class") ?? "";
      if (
        current !== lastReportCardClickTarget &&
        className.includes("rounded-[16px]") &&
        (className.includes("bg-surface") || className.includes("shadow-soft") || className.includes("border-border"))
      ) {
        return current;
      }
      current = current.parentElement;
    }
  }

  const active = document.activeElement;
  if (active instanceof HTMLElement) {
    const marked = active.closest(`[${REPORT_CARD_SNAPSHOT_ATTR}]`);
    if (marked instanceof HTMLElement) return marked;

    let current: HTMLElement | null = active;
    for (let depth = 0; current && depth < 8; depth += 1) {
      const className = current.getAttribute("class") ?? "";
      if (
        current !== active &&
        className.includes("rounded-[16px]") &&
        (className.includes("bg-surface") || className.includes("shadow-soft") || className.includes("border-border"))
      ) {
        return current;
      }
      current = current.parentElement;
    }
  }

  const title = block?.title?.trim();
  const subtitle = block?.subtitle?.trim();
  if (title) {
    const titleMatches = likelyReportCardContainers().filter((element) => element.innerText.includes(title));
    if (titleMatches.length > 0) {
      return titleMatches.find((element) => (subtitle ? element.innerText.includes(subtitle) : true)) ?? titleMatches[0];
    }
  }
  return null;
}

export function captureReportCardHtmlSnapshot(block?: ReportBlock): string | null {
  if (typeof window === "undefined") return null;
  const source = nearestReportCardElement(block);
  if (!source) return null;
  const clone = source.cloneNode(true);
  if (!(clone instanceof HTMLElement)) return null;
  removeInteractiveReportControls(clone);
  copyComputedStyles(source, clone);
  clone.querySelectorAll("[class]").forEach((element) => element.removeAttribute("class"));
  clone.removeAttribute("class");
  clone.setAttribute("data-exported-web-card", "true");
  return clone.outerHTML;
}
