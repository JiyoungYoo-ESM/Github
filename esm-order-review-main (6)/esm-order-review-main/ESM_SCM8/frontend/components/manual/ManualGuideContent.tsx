"use client";

import { useEffect, useState } from "react";
import { applyIngredientAvailabilityToGuide } from "@/lib/ingredient-availability";

export function ManualGuideContent() {
  const [markup, setMarkup] = useState("");

  useEffect(() => {
    let mounted = true;

    fetch("/docs/esm-scm-web-guide-v7-content.html?v=11", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Unable to load manual content");
        return response.text();
      })
      .then((content) => {
        if (!mounted) return;
        setMarkup(applyIngredientAvailabilityToGuide(content));
        requestAnimationFrame(() => {
          const hash = decodeURIComponent(window.location.hash.slice(1));
          document.getElementById(hash)?.scrollIntoView({ block: "start" });
        });
      })
      .catch(() => {
        if (mounted) setMarkup('<div class="layout"><div class="content"><p>사용설명서를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</p></div></div>');
      });

    const handleHashChange = () => {
      const hash = decodeURIComponent(window.location.hash.slice(1));
      document.getElementById(hash)?.scrollIntoView({ block: "start" });
    };
    window.addEventListener("hashchange", handleHashChange);

    return () => {
      mounted = false;
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  return markup ? <div dangerouslySetInnerHTML={{ __html: markup }} /> : null;
}
