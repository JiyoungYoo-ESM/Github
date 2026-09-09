const sampleRate = Number(process.env.NEXT_PUBLIC_PERFORMANCE_SAMPLE_RATE ?? "0.1");

function reportClientPerformance(name: string, durationMs: number) {
  if (typeof navigator === "undefined" || !Number.isFinite(durationMs)) return;
  // Always retain conspicuously slow work; sample routine work to control cost.
  if (durationMs < 100 && Math.random() > sampleRate) return;
  const screen = window.location.pathname.slice(0, 40);
  const body = JSON.stringify({ name, duration_ms: Number(durationMs.toFixed(2)), screen });
  navigator.sendBeacon("/backend-api/health/client-performance", new Blob([body], { type: "application/json" }));
}

/** Lightweight client-side timing for expensive derived UI work. */
export function measureClientWork<T>(name: string, work: () => T, warnAfterMs = 16): T {
  if (typeof performance === "undefined") return work();
  const startedAt = performance.now();
  const value = work();
  const duration = performance.now() - startedAt;
  performance.measure(name, { start: startedAt, duration });
  reportClientPerformance(name, duration);
  if (duration >= warnAfterMs && process.env.NODE_ENV !== "production") {
    console.warn(`[performance] ${name}: ${duration.toFixed(1)}ms`);
  }
  return value;
}
