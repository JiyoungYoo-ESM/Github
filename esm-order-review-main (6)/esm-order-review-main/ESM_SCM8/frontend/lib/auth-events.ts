export const AUTH_SESSION_CHANGED_EVENT = "esm_scm_auth_session_changed";
export const AUTH_SESSION_SIGNAL_STORAGE_KEY = "esm_scm_auth_session_signal";

export type AuthSessionChangeReason = "login" | "logout" | "unauthorized";

export type AuthSessionSignal = {
  id: string;
  reason: AuthSessionChangeReason;
  issuedAt: number;
};

function isAuthSessionChangeReason(value: unknown): value is AuthSessionChangeReason {
  return value === "login" || value === "logout" || value === "unauthorized";
}

export function parseAuthSessionSignal(value: string | null): AuthSessionSignal | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<AuthSessionSignal>;
    if (
      typeof parsed.id !== "string" ||
      parsed.id.length === 0 ||
      !isAuthSessionChangeReason(parsed.reason) ||
      typeof parsed.issuedAt !== "number" ||
      !Number.isFinite(parsed.issuedAt)
    ) {
      return null;
    }
    return {
      id: parsed.id,
      reason: parsed.reason,
      issuedAt: parsed.issuedAt
    };
  } catch {
    return null;
  }
}

let sequence = 0;

function createSignal(reason: AuthSessionChangeReason): AuthSessionSignal {
  sequence += 1;
  const randomPart =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return {
    id: `${Date.now()}:${sequence}:${randomPart}`,
    reason,
    issuedAt: Date.now()
  };
}

/**
 * 현재 탭에는 CustomEvent로, 다른 탭에는 localStorage의 storage 이벤트로
 * 인증 상태 변경을 알린다. 신호에는 계정명이나 토큰 같은 민감 정보가 없다.
 */
export function publishAuthSessionChange(reason: AuthSessionChangeReason): void {
  if (typeof window === "undefined") return;
  const signal = createSignal(reason);
  window.dispatchEvent(new CustomEvent<AuthSessionSignal>(AUTH_SESSION_CHANGED_EVENT, { detail: signal }));
  try {
    window.localStorage.setItem(AUTH_SESSION_SIGNAL_STORAGE_KEY, JSON.stringify(signal));
  } catch {
    // 저장소가 차단돼도 현재 탭의 CustomEvent 처리는 유지한다.
  }
}

export function subscribeAuthSessionChanges(
  handler: (signal: AuthSessionSignal) => void
): () => void {
  if (typeof window === "undefined") return () => undefined;

  let lastSignalId: string | null = null;
  const deliver = (signal: AuthSessionSignal | null) => {
    if (!signal || signal.id === lastSignalId) return;
    lastSignalId = signal.id;
    handler(signal);
  };
  const onCurrentTabChange = (event: Event) => {
    deliver((event as CustomEvent<AuthSessionSignal>).detail ?? null);
  };
  const onOtherTabChange = (event: StorageEvent) => {
    if (event.key !== AUTH_SESSION_SIGNAL_STORAGE_KEY) return;
    deliver(parseAuthSessionSignal(event.newValue));
  };

  window.addEventListener(AUTH_SESSION_CHANGED_EVENT, onCurrentTabChange);
  window.addEventListener("storage", onOtherTabChange);
  return () => {
    window.removeEventListener(AUTH_SESSION_CHANGED_EVENT, onCurrentTabChange);
    window.removeEventListener("storage", onOtherTabChange);
  };
}
