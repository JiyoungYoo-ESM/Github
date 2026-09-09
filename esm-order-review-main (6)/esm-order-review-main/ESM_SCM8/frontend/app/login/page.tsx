"use client";

// 로그인 화면. 자격증명 검증과 세션 발급은 백엔드(/api/auth/login)가 처리한다.
// (lib/auth.ts 주석 참고 — IMPROVEMENT_PLAN.md 항목 4)

import { useEffect, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { AlertCircle, Eye, EyeOff, Loader2, Lock, User } from "lucide-react";
import {
  checkSession,
  clearClientAuthorizationState,
  getVerifiedUser,
  hasAuthorizationScopeChanged,
  markVerified,
  verifyCredentialsRemote
} from "@/lib/auth";
import { cn } from "@/lib/utils";

// 좌측 패널 레이어 (rgba만 사용 → 디자인 토큰 감사 통과, 색상은 브랜드/사이드바 값과 동일)
const overlayStyle = {
  background:
    "linear-gradient(90deg, rgba(14,14,17,0.74) 0%, rgba(14,14,17,0.48) 42%, rgba(14,14,17,0.18) 100%), linear-gradient(180deg, rgba(14,14,17,0.18) 0%, rgba(14,14,17,0.48) 100%)"
};
const gridStyle = {
  backgroundImage:
    "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
  backgroundSize: "48px 48px"
};
const glowStyle = {
  background: "radial-gradient(circle, rgba(230,0,45,0.18) 0%, transparent 70%)"
};

export default function LoginPage() {
  const router = useRouter();
  const passwordRef = useRef<HTMLInputElement>(null);
  // 특정 계정을 기본 입력하지 않아 모든 사용자가 자신의 계정으로 로그인한다.
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<"credentials" | "rate_limited" | "network" | null>(null);
  const [shake, setShake] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // 이미 로그인된 상태로 로그인 페이지에 들어오면 메인으로 보냄
  useEffect(() => {
    checkSession().then((currentUser) => {
      if (currentUser.status === "authenticated") {
        const adoptSession = async () => {
          if (hasAuthorizationScopeChanged(getVerifiedUser(), currentUser.user)) {
            await clearClientAuthorizationState();
          }
          markVerified(currentUser.user);
          router.replace("/");
        };
        void adoptSession();
      }
    });
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isLoading) return;
    setError(null);
    setIsLoading(true);

    const result = await verifyCredentialsRemote(id.trim(), password);
    if (result === "ok") {
      const currentUser = await checkSession();
      if (currentUser.status === "authenticated") {
        if (hasAuthorizationScopeChanged(getVerifiedUser(), currentUser.user)) {
          await clearClientAuthorizationState();
        }
        markVerified(currentUser.user, true);
        router.replace("/"); // 메인 랜딩 페이지로 이동
        return;
      }
    }
    setIsLoading(false);
    setShake(true);
    setError(
      result === "invalid"
        ? "credentials"
        : result === "rate_limited"
          ? "rate_limited"
          : "network"
    );
    passwordRef.current?.focus();
  }

  // 입력 필드 포커스 시 오류 메시지 초기화
  function clearError() {
    if (error) setError(null);
  }

  const inputClass =
    "h-[46px] w-full rounded-[11px] border-[1.5px] border-[var(--border)] text-[14px] font-semibold text-[var(--text)] outline-none transition-colors placeholder:font-normal placeholder:text-muted2 focus:border-brand";

  return (
    <main className="flex h-screen w-screen overflow-hidden">
      {/* ── 좌측 브랜드 패널 (모바일 < 768px 에서는 숨김) ── */}
      <section className="relative hidden overflow-hidden text-white md:flex md:w-[52%]">
        <Image
          src="/assets/silicon2-building.jpg"
          alt=""
          aria-hidden="true"
          fill
          priority
          sizes="52vw"
          className="object-cover object-center brightness-[1.08] contrast-[1.02]"
        />
        <div className="absolute inset-0" style={overlayStyle} />
        <div className="absolute inset-0" style={gridStyle} />
        <div
          className="pointer-events-none absolute -right-20 -top-[120px] h-[480px] w-[480px]"
          style={glowStyle}
        />

        <div className="relative z-[1] flex w-full flex-col justify-between px-[52px] py-12">
          {/* 상단 로고 */}
          <div>
            <Image
              src="/assets/silicon2-logo-white.png"
              alt="Silicon2"
              width={200}
              height={44}
              className="h-[26px] w-auto object-contain"
            />
            <p className="mt-2 text-[12px] tracking-[0.02em] text-white/40">SCM Analytics · ESM</p>
          </div>

          {/* 중앙 헤드카피 + 통계 */}
          <div>
            <h1 className="mb-4 text-[38px] font-extrabold leading-[1.18] tracking-[-0.02em]">
              데이터 기반
              <br />
              글로벌 뷰티
              <br />
              <span className="text-brand">인사이트</span>
            </h1>
            <p className="max-w-[340px] text-[15px] leading-[1.7] text-muted2">
              국가 · 브랜드 · SKU를 하나의 분석 뷰에서.
              <br />
              발주 결정부터 브랜드 미팅 보고서까지.
            </p>
          </div>

          {/* 하단 저작권 */}
          <p className="text-[11.5px] text-white/25">© 2026 Silicon2 Co., Ltd. · 내부 임직원 전용 시스템</p>
        </div>
      </section>

      {/* ── 우측 폼 패널 ── */}
      <section className="flex flex-1 items-center justify-center bg-page px-4 py-6 sm:px-12 sm:py-10">
        {/* fade-up(마운트)와 shake(오류)를 서로 다른 요소에 두어 animation 충돌 방지 */}
        <div className="w-full max-w-[400px] animate-fade-up">
          <div
            className={cn(
              "rounded-[16px] border border-[var(--border)] bg-white px-6 py-7 shadow-[0_2px_12px_rgba(15,23,42,0.07)] sm:rounded-[20px] sm:px-[38px] sm:py-10",
              shake && "animate-shake"
            )}
            onAnimationEnd={() => setShake(false)}
          >
          <Image src="/assets/silicon2-logo-white.png" alt="Silicon2" width={130} height={28} className="mb-8 h-7 w-auto [filter:invert(1)] md:hidden" />
          <h2 className="text-[24px] font-extrabold tracking-[-0.02em] text-[var(--text)]">로그인</h2>
          <p className="mb-7 mt-[7px] text-[13.5px] leading-[1.5] text-muted">
            SILICON2 SCM Analytics에 오신 것을 환영합니다
          </p>

          <form onSubmit={handleSubmit} noValidate>
            {/* 아이디 */}
            <label htmlFor="login-id" className="mb-[7px] block text-[12.5px] font-bold text-[var(--text-2)]">
              아이디
            </label>
            <div className="relative mb-[14px]">
              <User className="pointer-events-none absolute left-[13px] top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-muted2" />
              <input
                id="login-id"
                name="id"
                type="text"
                autoComplete="username"
                value={id}
                onChange={(event) => setId(event.target.value)}
                onFocus={clearError}
                placeholder="아이디를 입력하세요"
                className={cn(inputClass, "pl-[38px] pr-[14px]")}
              />
            </div>

            {/* 비밀번호 */}
            <label htmlFor="login-password" className="mb-[7px] block text-[12.5px] font-bold text-[var(--text-2)]">
              비밀번호
            </label>
            <div className="relative mb-2">
              <Lock className="pointer-events-none absolute left-[13px] top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-muted2" />
              <input
                id="login-password"
                name="password"
                ref={passwordRef}
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onFocus={clearError}
                placeholder="비밀번호를 입력하세요"
                className={cn(inputClass, "pl-[38px] pr-[42px]")}
              />
              <button
                type="button"
                onClick={() => setShowPassword((visible) => !visible)}
                aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 표시"}
                className="absolute right-[13px] top-1/2 -translate-y-1/2 text-muted2 transition-colors hover:text-muted"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>

            {/* 오류 메시지 (로그인 실패 시만) — 자격증명 오류와 서버/네트워크 오류를 구분해서
                보여준다. 구분 안 하면 백엔드가 다운됐을 때도 "비밀번호가 틀렸다"고 표시된다. */}
            {error ? (
              <div
                role="alert"
                className="mt-2 flex items-center gap-1.5 rounded-[9px] border border-brand-100 bg-[var(--accent-tint)] px-[13px] py-2.5 text-[12.5px] font-semibold text-brand"
              >
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {error === "credentials"
                  ? "아이디 또는 비밀번호가 올바르지 않습니다"
                  : error === "rate_limited"
                    ? "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요"
                  : "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요"}
              </div>
            ) : null}

            {/* 로그인 버튼 */}
            <button
              type="submit"
              disabled={isLoading}
              className={cn(
                "mt-[14px] flex h-12 w-full items-center justify-center gap-[9px] rounded-[12px] text-[15px] font-bold text-white transition-colors",
                isLoading ? "bg-[var(--text-2)]" : "bg-sidebar hover:bg-brand"
              )}
            >
              {isLoading ? <Loader2 className="h-[18px] w-[18px] animate-spin" /> : "로그인"}
            </button>
          </form>

          </div>
        </div>
      </section>
    </main>
  );
}
