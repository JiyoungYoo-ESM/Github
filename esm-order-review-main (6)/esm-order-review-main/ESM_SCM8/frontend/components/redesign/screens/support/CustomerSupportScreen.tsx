"use client";

import { ChevronDown, ExternalLink, MessageCircleMore, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { descriptions, faqCategories, supportFormUrl, type SupportView } from "./supportData";
import { useSupportScreenModel } from "./useSupportScreenModel";

export function CustomerSupportScreen() {
  const { view, setView, category, setCategory, openFaq, setOpenFaq, searchQuery, setSearchQuery, visibleFaqs } = useSupportScreenModel();

  return (
    <div className="relative min-h-screen overflow-hidden bg-page">
      <header className="border-b border-border bg-surface px-[25px] py-[18px]">
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center gap-4">
          <div className="mr-auto min-w-[150px]">
            <p className="text-[11px] font-black leading-none text-brand">지원 · SUPPORT</p>
            <h1 className="mt-[7px] text-[21px] font-black leading-none text-ink">고객센터</h1>
          </div>
          <div className="flex rounded-[10px] border border-border bg-surface p-1">
            {(["faq", "submit"] as SupportView[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setView(item)}
                className={cn(
                  "h-[34px] rounded-[8px] px-4 text-[13px] font-black transition",
                  view === item ? "bg-ink text-white" : "text-muted2 hover:bg-row hover:text-ink"
                )}
              >
                {item === "faq" ? "FAQ" : "문의하기"}
              </button>
            ))}
          </div>
          <label className="relative w-full sm:ml-2 sm:w-[230px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted2" aria-hidden="true" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                setView("faq");
              }}
              placeholder="질문 검색"
              aria-label="FAQ 질문 검색"
              className="h-[38px] w-full rounded-[9px] border border-border bg-page py-2 pl-9 pr-3 text-[13px] font-semibold text-ink outline-none transition placeholder:text-muted2 focus:border-brand focus:bg-surface focus:ring-2 focus:ring-brand/15"
            />
          </label>
        </div>
      </header>

      <div className="mx-auto max-w-[1320px] px-[25px] py-6">
        <p className="mb-5 text-[13px] font-semibold leading-6 text-muted">{descriptions[view]}</p>

        {view === "faq" ? (
          <section>
            <div className="mb-[18px] flex flex-wrap gap-2" aria-label="FAQ 카테고리">
              {faqCategories.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setCategory(item.id)}
                  className={cn(
                    "rounded-full border px-[14px] py-[7px] text-[12px] font-black transition",
                    category === item.id ? "border-ink bg-ink text-white" : "border-border bg-surface text-muted hover:border-muted2 hover:text-ink"
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="space-y-2">
              {visibleFaqs.map((faq) => {
                const open = openFaq === faq.id;
                return (
                  <article key={faq.id} className="overflow-hidden rounded-[12px] border border-border bg-surface">
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => setOpenFaq(open ? null : faq.id)}
                      className="flex w-full items-center justify-between gap-4 px-[18px] py-[15px] text-left"
                    >
                      <span className="text-[14px] font-black text-ink">
                        <span className="mr-[10px] inline-flex rounded-[5px] bg-brand-50 px-2 py-[3px] text-[10px] font-black text-brand">
                          {faq.categoryLabel}
                        </span>
                        {faq.question}
                      </span>
                      <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted2 transition", open && "rotate-180")} />
                    </button>
                    {open ? <p className="mx-[18px] border-t border-border px-0 py-[14px] text-[13px] font-semibold leading-6 text-muted">{faq.answer}</p> : null}
                  </article>
                );
              })}
              {visibleFaqs.length === 0 ? (
                <div className="rounded-[12px] border border-dashed border-border bg-surface px-6 py-14 text-center">
                  <Search className="mx-auto h-6 w-6 text-muted2" />
                  <p className="mt-3 text-[13px] font-black text-muted">검색 결과가 없습니다.</p>
                  <p className="mt-1 text-[12px] font-semibold text-muted2">다른 검색어나 카테고리를 선택해 보세요.</p>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        {view === "submit" ? (
          <section className="overflow-hidden rounded-[14px] border border-border bg-surface">
            <div className="flex min-h-[360px] flex-col items-center justify-center bg-page px-6 py-12 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand">
                <MessageCircleMore className="h-5 w-5" />
              </span>
              <h2 className="mt-4 text-[17px] font-black text-ink">Microsoft Forms에서 문의를 접수합니다</h2>
              <p className="mt-2 max-w-[440px] text-[12px] font-semibold leading-5 text-muted">
                문의하기를 누르면 Microsoft Forms가 새 창에서 열립니다.
                문의 내용을 작성한 뒤 제출해 주세요.
              </p>
              <a
                href={supportFormUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-6 inline-flex h-11 items-center gap-2 rounded-[9px] bg-brand px-5 text-[13px] font-black text-white transition hover:bg-brand-700"
              >
                문의하기 <ExternalLink className="h-4 w-4" />
              </a>
              <p className="mt-3 text-[11px] font-semibold text-muted2">Forms가 새 창에서 열리지 않으면 브라우저의 팝업 차단을 해제해 주세요.</p>
            </div>
          </section>
        ) : null}

      </div>
    </div>
  );
}
