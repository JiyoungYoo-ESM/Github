"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { logoutRemote } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { useAuthSession } from "@/components/auth/AuthSessionContext";

type LogoutButtonProps = {
  /** true면 아이콘만 표시(사이드바 등 좁은 영역용) */
  compact?: boolean;
  className?: string;
};

/**
 * 로그아웃 버튼.
 * 클릭 시 서버 세션을 무효화한 뒤 /login 으로 이동합니다. (lib/auth.ts 주석 참고)
 */
export function LogoutButton({ compact = false, className }: LogoutButtonProps) {
  const router = useRouter();
  const { user } = useAuthSession();
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    const result = await logoutRemote();
    setIsLoggingOut(false);
    if (result === "ok") {
      router.replace("/login");
      return;
    }
    window.alert("로그아웃에 실패했습니다. 연결을 확인한 뒤 다시 시도해 주세요.");
  }

  if (compact) {
    return (
      <button
        type="button"
        onClick={handleLogout}
        disabled={isLoggingOut}
        title={`${user?.display_name ?? user?.username ?? "현재 계정"} 로그아웃`}
        aria-label="로그아웃"
        className={cn(
          "grid h-9 w-9 place-items-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-brand",
          className
        )}
      >
        <LogOut className="h-4 w-4" />
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      disabled={isLoggingOut}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-line bg-white px-3.5 py-1.5 text-sm font-bold text-black transition-colors hover:border-brand hover:text-brand",
        className
      )}
    >
      <LogOut className="h-4 w-4" />
      로그아웃
    </button>
  );
}
