"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

const MIN_VISIBLE_MS = 420;
const MAX_VISIBLE_MS = 6000;

function isPlainLeftClick(event: MouseEvent) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

function isSameRouteUrl(url: URL) {
  return url.pathname === window.location.pathname && url.search === window.location.search;
}

export function LoadingOverlay() {
  return (
    <div className="fixed inset-0 z-[9999] grid place-items-center bg-white" role="status" aria-label="페이지를 불러오는 중">
      <div className="h-14 w-14 animate-route-loader rounded-full border-4 border-line border-t-brand" />
    </div>
  );
}

export function AppRouteLoader() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [visible, setVisible] = useState(false);
  const startedAtRef = useRef(0);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const routeRef = useRef({ pathname: "", search: "" });

  const clearTimers = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }

    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
  }, []);

  const showLoader = useCallback(() => {
    clearTimers();
    startedAtRef.current = Date.now();
    setVisible(true);
    maxTimerRef.current = setTimeout(() => setVisible(false), MAX_VISIBLE_MS);
  }, [clearTimers]);

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!isPlainLeftClick(event)) {
        return;
      }

      const target = event.target instanceof Element ? event.target.closest("a") : null;
      if (!target) {
        return;
      }

      const href = target.getAttribute("href");
      const targetWindow = target.getAttribute("target");
      const download = target.hasAttribute("download");
      if (!href || href.startsWith("#") || targetWindow || download) {
        return;
      }

      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin || isSameRouteUrl(url)) {
        return;
      }

      showLoader();
    };

    const onPopState = () => {
      if (window.location.pathname === routeRef.current.pathname && window.location.search === routeRef.current.search) {
        return;
      }

      showLoader();
    };

    document.addEventListener("click", onDocumentClick, true);
    window.addEventListener("popstate", onPopState);

    return () => {
      document.removeEventListener("click", onDocumentClick, true);
      window.removeEventListener("popstate", onPopState);
      clearTimers();
    };
  }, [clearTimers, showLoader]);

  useEffect(() => {
    routeRef.current = {
      pathname,
      search: searchParams.toString() ? `?${searchParams.toString()}` : "",
    };

    if (!visible) {
      return;
    }

    const elapsed = Date.now() - startedAtRef.current;
    const remaining = Math.max(MIN_VISIBLE_MS - elapsed, 0);
    hideTimerRef.current = setTimeout(() => {
      setVisible(false);
      clearTimers();
    }, remaining);
  }, [clearTimers, pathname, searchParams, visible]);

  return visible ? <LoadingOverlay /> : null;
}
