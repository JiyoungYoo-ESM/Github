"use client";

import { useMemo, useState } from "react";

import { INGREDIENT_ANALYSIS_ENABLED } from "@/lib/feature-flags";
import { faqs, type FaqCategory, type SupportView } from "./supportData";

// 플래그로 끼워 넣는 FAQ의 id는 supportData에서 파생시킨다. 예전에는 94를 하드코딩해 뒀는데
// 제품군 FAQ(94)가 추가되자 React key가 중복됐고, 아코디언 열림 상태가 id 기준이라 둘 중
// 하나를 누르면 두 항목이 함께 펼쳐졌다.
const SYNTHETIC_FAQ_ID = Math.max(...faqs.map((faq) => faq.id)) + 1;

export function useSupportScreenModel() {
  const [view, setView] = useState<SupportView>("faq");
  const [category, setCategory] = useState<FaqCategory>("all");
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const visibleFaqs = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLocaleLowerCase("ko-KR");
    const hiddenFaqIds = new Set([68, 69, 70, 71]);
    const ingredientAvailabilityFaq = {
      id: SYNTHETIC_FAQ_ID,
      category: "etc" as const,
      categoryLabel: "기타",
      question: "성분 탭이 비활성화되어 있어요.",
      answer: "성분 탭은 현재 데이터 정합성 보강을 위해 준비 중 상태로 비활성화되어 있습니다. 메뉴에서 '준비 중'으로 표시되며 지금은 선택하거나 성분 분석 기능을 사용할 수 없습니다. 기능이 준비되면 다시 활성화될 예정입니다."
    };

    return [
      ...faqs,
      ...(!INGREDIENT_ANALYSIS_ENABLED ? [ingredientAvailabilityFaq] : [])
    ].map((faq) => {
      if (faq.id === 89) {
        return {
          ...faq,
          answer: "'차원별'은 국가·브랜드·제품군·SKU 순서로 하나의 기준을 보는 화면입니다. '심화'는 시즌 캘린더·교차분석·브랜드 리포트 순서로 시즌 계획과 복합 분석·보고서 기능을 제공합니다. 성분 탭은 준비 중으로 별도 비활성화되어 있습니다."
        };
      }
      if (faq.id === 91) {
        return {
          ...faq,
          answer: "네, 모바일 화면에 맞춰 UI/UX가 대응되어 있어 주요 분석 화면과 엑셀 내보내기를 PC와 동일하게 이용할 수 있습니다. 다만 휴대폰도 회사 와이파이에 연결돼 있어야 접속됩니다(보안상 회사 IP에서만 접속 가능한 정책은 휴대폰도 동일하게 적용됩니다)."
        };
      }
      return faq;
    }).filter((faq) => {
      if (hiddenFaqIds.has(faq.id)) return false;
      if (!INGREDIENT_ANALYSIS_ENABLED && [63, 86].includes(faq.id)) return false;
      const matchesCategory = category === "all" || faq.category === category;
      const matchesSearch =
        !normalizedQuery ||
        [faq.question, faq.answer, faq.categoryLabel]
          .join(" ")
          .toLocaleLowerCase("ko-KR")
          .includes(normalizedQuery);

      return matchesCategory && matchesSearch;
    });
  }, [category, searchQuery]);

  return {
    view,
    setView,
    category,
    setCategory,
    openFaq,
    setOpenFaq,
    searchQuery,
    setSearchQuery,
    visibleFaqs
  };
}
