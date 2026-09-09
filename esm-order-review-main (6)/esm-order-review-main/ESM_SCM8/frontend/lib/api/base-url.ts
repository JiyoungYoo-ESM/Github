export const SAME_ORIGIN_API_BASE = "/backend-api";
export const SAME_ORIGIN_DIRECT_API_BASE = "/api";
export const LOCAL_SERVER_API_BASE = "http://127.0.0.1:8002/api";

type BrowserLocation = Pick<Location, "hostname" | "protocol">;

function isLocalDevelopmentHost(hostname: string): boolean {
  if (hostname === "127.0.0.1" || hostname === "localhost") return true;
  // LAN development is served from the current machine. Large Excel exports
  // must go straight to FastAPI because the Next.js rewrite can reset a
  // multi-minute response before the workbook reaches the browser.
  return (
    /^10\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(hostname)
  );
}

export function normalizeApiBase(value: string | undefined): string {
  const base = value?.replace(/\/$/, "");
  if (!base) {
    return "";
  }
  return base.endsWith("/api") ? base : `${base}/api`;
}

export function resolveBrowserApiBase(configuredPublicBase?: string): string {
  return normalizeApiBase(configuredPublicBase) || SAME_ORIGIN_API_BASE;
}

/**
 * Resolve an API base for large binary transfers that should not be buffered
 * through the Next.js `/backend-api` rewrite in production.
 */
export function resolveBrowserDirectApiBase(
  configuredPublicBase?: string,
  location?: BrowserLocation,
  _environment = process.env.NODE_ENV
): string {
  const configured = normalizeApiBase(configuredPublicBase);
  if (configured) return configured;
  // `next start` sets NODE_ENV=production even when the app is being served
  // locally. In that setup a large V2 workbook can take longer than the Next
  // rewrite keeps its upstream socket open, so local HTTP traffic must still
  // bypass Next and stream directly from FastAPI.
  if (
    location?.protocol === "http:" &&
    isLocalDevelopmentHost(location.hostname)
  ) {
    return `http://${location.hostname}:8002/api`;
  }
  return SAME_ORIGIN_DIRECT_API_BASE;
}

export function resolveServerApiBase(configuredInternalBase?: string): string {
  return normalizeApiBase(configuredInternalBase) || LOCAL_SERVER_API_BASE;
}
