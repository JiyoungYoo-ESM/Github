"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  checkSession,
  clearClientAuthorizationState,
  getVerifiedUser,
  hasAuthorizationScopeChanged,
  markVerified,
  wasVerifiedThisLoad,
  type AuthUser
} from "@/lib/auth";
import { subscribeAuthSessionChanges } from "@/lib/auth-events";
import {
  initializeActiveEntity,
  setActiveEntityCode
} from "@/lib/entity-session";
import { abortActiveApiRequests } from "@/lib/api/client";
import type { EntityCode } from "@/lib/entities";
import {
  canAccessOrderAnalysis,
  isOrderAnalysisBlockedForEntity,
  isOrderAnalysisPath
} from "@/lib/order-access";
import {
  canAccessCorporateInventory,
  canAccessCorporateInventoryForEntity,
  isCorporateInventoryPath
} from "@/lib/corporate-inventory-access";
import { AuthSessionContext } from "@/components/auth/AuthSessionContext";
import { workspaceScreenFromPathname } from "@/components/redesign/lib/workspace-routes";

// 로그인 없이 접근 가능한 경로
const PUBLIC_PATHS = ["/login"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/**
 * 서버 세션 기반 인증 가드.
 *
 * 세션 쿠키는 HttpOnly라 여기서 직접 읽을 수 없으므로 /api/auth/me로 서버에 확인한다.
 * 일반 라우트 이동에는 탭의 검증 결과를 재사용한다. 대신 다른 탭의 로그인/로그아웃,
 * 데이터 API의 401, 창 포커스 복귀에는 서버 세션을 재검증한다. 계정 범위가 바뀌는
 * 동안에는 보호 콘텐츠를 먼저 숨기고 이전 계정의 법인 선택과 분석 캐시를 지운다.
 *
 * 로그인하지 않은 사용자가 보호된 페이지에 직접 접근하면 /login 으로 리다이렉트합니다.
 * 인증 확인이 끝나기 전에는 보호된 콘텐츠를 노출하지 않습니다(스플래시 표시).
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const publicPath = isPublicPath(pathname);
  const cachedUser = getVerifiedUser();
  const [user, setUser] = useState<AuthUser | null>(cachedUser);
  const [selectedEntity, setSelectedEntity] = useState<EntityCode | null>(() =>
    cachedUser ? initializeActiveEntity(cachedUser) : null
  );
  const [allowed, setAllowed] = useState(Boolean(cachedUser && wasVerifiedThisLoad()));
  const [sessionUnavailable, setSessionUnavailable] = useState(false);
  const orderPathBlocked = Boolean(
    user && !canAccessOrderAnalysis(user) && isOrderAnalysisPath(pathname)
  );
  const corporateInventoryPathBlocked = Boolean(
    user &&
      isCorporateInventoryPath(pathname) &&
      (!canAccessCorporateInventory(user) || !canAccessCorporateInventoryForEntity(selectedEntity))
  );
  const adminV3SettingsPathBlocked = Boolean(
    user && pathname.startsWith("/admin/v3-settings") && !user.is_admin
  );
  const entityWorkspaceScreen = workspaceScreenFromPathname(pathname);
  const entityOrderPathBlocked = Boolean(
    user &&
      selectedEntity &&
      entityWorkspaceScreen &&
      isOrderAnalysisBlockedForEntity(selectedEntity, entityWorkspaceScreen)
  );

  useEffect(() => {
    let active = true;
    let validationSequence = 0;

    const concealPreviousScope = () => {
      setUser(null);
      setSelectedEntity(null);
      setAllowed(publicPath);
    };

    const invalidateSession = async () => {
      const requestSequence = ++validationSequence;
      concealPreviousScope();
      await clearClientAuthorizationState();
      if (!active || requestSequence !== validationSequence) return;
      if (!publicPath) {
        router.replace("/login");
      }
    };

    const revalidateSession = async ({
      conceal = false,
      redirectFromPublic = false
    }: {
      conceal?: boolean;
      redirectFromPublic?: boolean;
    } = {}) => {
      const requestSequence = ++validationSequence;
      if (conceal) concealPreviousScope();
      const currentUser = await checkSession();
      if (!active || requestSequence !== validationSequence) return;

      if (currentUser.status === "unavailable") {
        setSessionUnavailable(true);
        return;
      }

      if (currentUser.status === "unauthorized") {
        concealPreviousScope();
        await clearClientAuthorizationState();
        if (!active || requestSequence !== validationSequence) return;
        if (!publicPath) router.replace("/login");
        return;
      }

      setSessionUnavailable(false);
      const authenticatedUser = currentUser.user;
      const previousUser = getVerifiedUser();
      if (hasAuthorizationScopeChanged(previousUser, authenticatedUser)) {
        concealPreviousScope();
        await clearClientAuthorizationState();
        if (!active || requestSequence !== validationSequence) return;
      }

      markVerified(authenticatedUser);
      setUser(authenticatedUser);
      setSelectedEntity(initializeActiveEntity(authenticatedUser));
      setAllowed(true);
      if (publicPath && redirectFromPublic) {
        router.replace("/");
      }
    };

    const unsubscribe = subscribeAuthSessionChanges((signal) => {
      if (signal.reason === "logout") {
        void invalidateSession();
        return;
      }
      void revalidateSession({ conceal: true, redirectFromPublic: signal.reason === "login" });
    });

    const handleFocus = () => void revalidateSession({ redirectFromPublic: true });
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") handleFocus();
    };
    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) void revalidateSession({ conceal: true, redirectFromPublic: true });
    };
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pageshow", handlePageShow);

    if (publicPath) {
      setAllowed(true);
    } else {
      const verifiedUser = getVerifiedUser();
      if (wasVerifiedThisLoad() && verifiedUser) {
        setUser(verifiedUser);
        setSelectedEntity(initializeActiveEntity(verifiedUser));
        setAllowed(true);
      } else {
        void revalidateSession({ conceal: true });
      }
    }

    return () => {
      active = false;
      validationSequence += 1;
      unsubscribe();
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, [publicPath, router]);

  useEffect(() => {
    if (allowed && (orderPathBlocked || entityOrderPathBlocked || corporateInventoryPathBlocked || adminV3SettingsPathBlocked)) {
      router.replace(entityOrderPathBlocked ? "/order-analysis/new-order-logic" : "/insight/input");
    }
  }, [adminV3SettingsPathBlocked, allowed, corporateInventoryPathBlocked, entityOrderPathBlocked, orderPathBlocked, router]);

  const selectEntity = useCallback(async (entityCode: EntityCode) => {
    if (!user || !user.allowed_entities.includes(entityCode)) return;
    if (entityCode === selectedEntity) return;
    // A response started under the previous entity must never repopulate the
    // newly selected entity's in-memory or persisted analysis state.
    abortActiveApiRequests();
    const { clearSensitiveAnalysisState } = await import("@/lib/api/storage");
    await clearSensitiveAnalysisState();
    setActiveEntityCode(user, entityCode);
    setSelectedEntity(entityCode);
  }, [selectedEntity, user]);

  const sessionValue = useMemo(
    () => ({ user, selectedEntity, selectEntity }),
    [selectEntity, selectedEntity, user]
  );

  // 로그인 페이지 등 공개 경로는 그대로 렌더
  if (publicPath) {
    return <AuthSessionContext.Provider value={sessionValue}>{children}</AuthSessionContext.Provider>;
  }

  // 인증 확인 전 또는 미인증 상태에서는 보호된 콘텐츠를 감춤
  if (!allowed || !user || !selectedEntity || orderPathBlocked || entityOrderPathBlocked || corporateInventoryPathBlocked || adminV3SettingsPathBlocked) {
    if (sessionUnavailable) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white px-6 text-center">
          <p className="text-sm font-semibold text-ink">세션을 확인하지 못했습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요.</p>
          <button type="button" className="rounded-md bg-brand px-4 py-2 text-sm font-bold text-white" onClick={() => window.location.reload()}>
            다시 시도
          </button>
        </div>
      );
    }
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-line border-t-brand" aria-label="로딩 중" />
      </div>
    );
  }

  return <AuthSessionContext.Provider value={sessionValue}>{children}</AuthSessionContext.Provider>;
}
