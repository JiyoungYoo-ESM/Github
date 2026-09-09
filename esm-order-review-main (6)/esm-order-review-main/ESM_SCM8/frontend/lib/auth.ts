/**
 * 로그인 유틸리티 — 자격증명 검증과 세션은 백엔드가 관리한다.
 * (이전에는 프론트엔드 localStorage + NEXT_PUBLIC 비밀번호로 처리했음 — 브라우저 번들에
 * 비밀번호가 그대로 노출되는 문제가 있었다. IMPROVEMENT_PLAN.md 항목 4 참고.)
 *
 * 세션은 백엔드가 발급하는 HttpOnly 쿠키(s2_session)로 유지된다. 이 모듈은 그 쿠키를
 * 직접 읽지 않는다(HttpOnly라 JS로 읽을 수 없음) — 대신 /api/auth/* 엔드포인트를 호출해
 * 서버에 물어본다.
 */

import type { AuthActionResponse, LoginRequest } from "@/types/api";
import { abortActiveApiRequests, apiFetch, FASTAPI_BASE_URL } from "./api/client";
import { clearActiveEntity } from "@/lib/entity-session";
import type { EntityCode } from "@/lib/entities";
import { LEAD_TIME_STORAGE_PREFIX } from "@/lib/lead-times";
import { publishAuthSessionChange } from "./auth-events";
import type { UserPermissions } from "./amount-permissions";
import {
  readRawItem,
  removeItem,
  removeItemsWithPrefix,
  writeRawItem
} from "@/lib/storage/adapter";

export type AuthUser = {
  authenticated: true;
  username: string;
  display_name: string;
  role: string;
  account_type: string;
  allowed_entities: EntityCode[];
  entities: Array<{
    code: EntityCode;
    display_name: string;
    legal_name: string;
    integrated: boolean;
    order_integrated?: boolean;
    insight_integrated?: boolean;
  }>;
  is_admin: boolean;
  permissions: UserPermissions;
};

export type LoginResult = "ok" | "invalid" | "rate_limited" | "network_error";
export type SessionCheckResult =
  | { status: "authenticated"; user: AuthUser }
  | { status: "unauthorized" }
  | { status: "unavailable" };
export type LogoutResult = "ok" | "network_error";

/** 이 탭이 로드된 뒤 서버에 인증 확인을 이미 받았는지 여부. 라우트 이동마다 매번
 * /api/auth/me를 부르면 네비게이션마다 네트워크 왕복이 붙으므로, 탭당 1회로 제한한다.
 * 전체 새로고침(모듈 상태 초기화)이나 로그아웃 시에는 다시 확인한다. */
let verifiedThisLoad = false;
let verifiedUser: AuthUser | null = null;
const AUTHORIZATION_SCOPE_STORAGE_KEY = "esm_scm_authorization_scope";

function authorizationScopeFingerprint(user: AuthUser): string {
  return JSON.stringify({
    username: user.username,
    role: user.role,
    accountType: user.account_type,
    isAdmin: user.is_admin,
    permissions: user.permissions,
    allowedEntities: user.allowed_entities,
    entities: user.entities.map((entity) => [entity.code, entity.integrated])
  });
}

export function wasVerifiedThisLoad(): boolean {
  return verifiedThisLoad;
}

export function getVerifiedUser(): AuthUser | null {
  return verifiedUser;
}

export function markVerified(user: AuthUser, notifyOtherTabs = false): void {
  verifiedThisLoad = true;
  verifiedUser = user;
  writeRawItem("session", AUTHORIZATION_SCOPE_STORAGE_KEY, authorizationScopeFingerprint(user));
  if (notifyOtherTabs) {
    publishAuthSessionChange("login");
  }
}

export function clearVerified(): void {
  verifiedThisLoad = false;
  verifiedUser = null;
}

export function hasAuthorizationScopeChanged(
  previousUser: AuthUser | null,
  currentUser: AuthUser
): boolean {
  const currentScope = authorizationScopeFingerprint(currentUser);
  if (!previousUser) {
    return readRawItem("session", AUTHORIZATION_SCOPE_STORAGE_KEY) !== currentScope;
  }
  if (
    previousUser.username !== currentUser.username ||
    previousUser.role !== currentUser.role ||
    previousUser.account_type !== currentUser.account_type ||
    previousUser.is_admin !== currentUser.is_admin ||
    JSON.stringify(previousUser.permissions) !== JSON.stringify(currentUser.permissions)
  ) {
    return true;
  }
  return (
    previousUser.allowed_entities.join("\u0000") !== currentUser.allowed_entities.join("\u0000") ||
    previousUser.entities
      .map((entity) => `${entity.code}\u0000${entity.integrated}`)
      .join("\u0001") !==
      currentUser.entities
        .map((entity) => `${entity.code}\u0000${entity.integrated}`)
        .join("\u0001")
  );
}

let clientStateClearPromise: Promise<void> | null = null;

/** 사용자/법인 범위가 끝나는 즉시 메모리, 세션 저장소와 IndexedDB 결과를 비운다. */
export function clearClientAuthorizationState(): Promise<void> {
  abortActiveApiRequests();
  clearVerified();
  clearActiveEntity();
  removeItem("session", AUTHORIZATION_SCOPE_STORAGE_KEY);
  removeItemsWithPrefix("local", `${LEAD_TIME_STORAGE_PREFIX}:`);
  if (!clientStateClearPromise) {
    clientStateClearPromise = import("./api/storage")
      .then(({ clearSensitiveAnalysisState }) => clearSensitiveAnalysisState())
      .finally(() => {
        clientStateClearPromise = null;
      });
  }
  return clientStateClearPromise;
}

/** 아이디/비밀번호를 백엔드에 제출해 세션 쿠키를 발급받는다. */
export async function verifyCredentialsRemote(id: string, password: string): Promise<LoginResult> {
  try {
    const request: LoginRequest = { id, password };
    const response = await apiFetch(`${FASTAPI_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    });
    if (response.ok) {
      const result = (await response.json()) as AuthActionResponse;
      return result.ok ? "ok" : "network_error";
    }
    if (response.status === 401) return "invalid";
    if (response.status === 429) return "rate_limited";
    return "network_error";
  } catch {
    return "network_error";
  }
}

/** 현재 세션 쿠키가 서버에서 유효한지 확인한다. */
export async function checkSession(): Promise<SessionCheckResult> {
  try {
    const response = await apiFetch(`${FASTAPI_BASE_URL}/auth/me`);
    if (response.status === 401 || response.status === 403) return { status: "unauthorized" };
    if (!response.ok) return { status: "unavailable" };
    const result = (await response.json()) as AuthUser;
    return result.authenticated
      ? { status: "authenticated", user: result }
      : { status: "unauthorized" };
  } catch {
    return { status: "unavailable" };
  }
}

/** 서버 세션을 무효화한다(쿠키 삭제). 실패해도 클라이언트는 로그인 화면으로 보낸다. */
export async function logoutRemote(): Promise<LogoutResult> {
  try {
    const response = await apiFetch(`${FASTAPI_BASE_URL}/auth/logout`, { method: "POST" });
    if (!response.ok) return "network_error";
  } catch {
    // 세션 쿠키는 만료되면 자연히 정리되므로 여기서 실패해도 무방하다.
    return "network_error";
  }
    await clearClientAuthorizationState();
    publishAuthSessionChange("logout");
  return "ok";
}
