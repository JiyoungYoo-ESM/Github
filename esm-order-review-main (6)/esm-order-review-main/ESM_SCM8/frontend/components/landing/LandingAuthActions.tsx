"use client";

import { LogoutButton } from "@/components/auth/LogoutButton";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { UserRound } from "lucide-react";

export function LandingAuthActions() {
  const { user } = useAuthSession();
  const accountName = user?.display_name || user?.username || "로그인 계정";
  const showUsername = Boolean(user?.username && user.username !== accountName);

  return (
    <div className="flex h-11 min-w-0 items-center rounded-[8px] border border-black/10 bg-white pl-2.5 shadow-sm">
      <div className="flex min-w-0 items-center gap-2 pr-2.5">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
          <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span className="min-w-0 text-left leading-tight">
          <span className="block max-w-24 truncate text-[12px] font-black text-black sm:max-w-36">
            {accountName}
          </span>
          {showUsername ? (
            <span className="hidden max-w-36 truncate text-[10px] font-semibold text-slate-500 sm:block">
              {user?.username}
            </span>
          ) : null}
        </span>
      </div>
      <LogoutButton className="h-full shrink-0 rounded-none rounded-r-[8px] border-0 border-l border-black/10 bg-transparent px-3 text-[12px] font-black text-black shadow-none hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand sm:px-3.5 sm:text-[13px]" />
    </div>
  );
}
