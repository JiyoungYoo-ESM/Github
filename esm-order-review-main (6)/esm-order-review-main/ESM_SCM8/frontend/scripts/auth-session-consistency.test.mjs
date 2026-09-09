import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const eventTarget = new EventTarget();
const localValues = new Map();
globalThis.window = {
  addEventListener: eventTarget.addEventListener.bind(eventTarget),
  removeEventListener: eventTarget.removeEventListener.bind(eventTarget),
  dispatchEvent: eventTarget.dispatchEvent.bind(eventTarget),
  localStorage: {
    getItem: (key) => localValues.get(key) ?? null,
    setItem: (key, value) => localValues.set(key, value),
    removeItem: (key) => localValues.delete(key)
  }
};

const {
  AUTH_SESSION_CHANGED_EVENT,
  AUTH_SESSION_SIGNAL_STORAGE_KEY,
  parseAuthSessionSignal,
  publishAuthSessionChange,
  subscribeAuthSessionChanges
} = await import("../lib/auth-events.ts");

const received = [];
const unsubscribe = subscribeAuthSessionChanges((signal) => received.push(signal));

publishAuthSessionChange("login");
assert.equal(received.length, 1);
assert.equal(received[0].reason, "login");
const persistedSignal = localValues.get(AUTH_SESSION_SIGNAL_STORAGE_KEY);
assert.equal(parseAuthSessionSignal(persistedSignal)?.id, received[0].id);
assert.equal("username" in JSON.parse(persistedSignal), false, "탭 간 신호에 계정명을 저장하면 안 됨");

const duplicateStorageEvent = new Event("storage");
Object.assign(duplicateStorageEvent, {
  key: AUTH_SESSION_SIGNAL_STORAGE_KEY,
  newValue: persistedSignal
});
eventTarget.dispatchEvent(duplicateStorageEvent);
assert.equal(received.length, 1, "동일 신호를 CustomEvent와 storage 이벤트로 중복 처리하면 안 됨");

const remoteSignal = JSON.stringify({
  id: "remote-tab:2",
  reason: "unauthorized",
  issuedAt: Date.now()
});
const remoteStorageEvent = new Event("storage");
Object.assign(remoteStorageEvent, {
  key: AUTH_SESSION_SIGNAL_STORAGE_KEY,
  newValue: remoteSignal
});
eventTarget.dispatchEvent(remoteStorageEvent);
assert.equal(received.length, 2);
assert.equal(received[1].reason, "unauthorized");

const malformedStorageEvent = new Event("storage");
Object.assign(malformedStorageEvent, {
  key: AUTH_SESSION_SIGNAL_STORAGE_KEY,
  newValue: JSON.stringify({ id: "bad", reason: "unknown", issuedAt: Date.now() })
});
eventTarget.dispatchEvent(malformedStorageEvent);
assert.equal(received.length, 2, "알 수 없는 인증 신호는 무시해야 함");
assert.equal(parseAuthSessionSignal("not-json"), null);

unsubscribe();
eventTarget.dispatchEvent(new CustomEvent(AUTH_SESSION_CHANGED_EVENT, {
  detail: { id: "after-unsubscribe", reason: "logout", issuedAt: Date.now() }
}));
assert.equal(received.length, 2, "구독 해제 후에는 신호가 전달되면 안 됨");

const transportSource = readFileSync(new URL("../lib/api/transport.ts", import.meta.url), "utf8");
assert.match(transportSource, /response\.status === 401/);
assert.match(transportSource, /publishAuthSessionChange\("unauthorized"\)/);
assert.match(transportSource, /auth\\\/\(\?:login\|me\)/, "로그인 실패와 세션 확인 401은 재귀 신호에서 제외해야 함");
assert.match(transportSource, /abortActiveApiRequests/);
assert.match(transportSource, /activeRequestControllers/);

const guardSource = readFileSync(new URL("../components/auth/AuthGuard.tsx", import.meta.url), "utf8");
assert.match(guardSource, /subscribeAuthSessionChanges/);
assert.match(guardSource, /hasAuthorizationScopeChanged/);
assert.match(guardSource, /clearClientAuthorizationState/);
assert.match(guardSource, /window\.addEventListener\("focus"/);
assert.match(guardSource, /event\.persisted/);
assert.match(guardSource, /concealPreviousScope\(\);[\s\S]*?await clearClientAuthorizationState\(\)/);

const loginSource = readFileSync(new URL("../app/login/page.tsx", import.meta.url), "utf8");
assert.match(loginSource, /markVerified\(currentUser\.user, true\)/, "로그인 성공을 다른 탭에 알려야 함");
assert.match(loginSource, /hasAuthorizationScopeChanged\(getVerifiedUser\(\), currentUser\.user\)/);

const authSource = readFileSync(new URL("../lib/auth.ts", import.meta.url), "utf8");
assert.match(authSource, /status: "unavailable"/);
assert.match(authSource, /status: "unauthorized"/);

console.log("auth session consistency tests passed");
