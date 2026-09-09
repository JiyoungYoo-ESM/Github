/**
 * 브라우저 저장소 어댑터 — localStorage/sessionStorage/IndexedDB 접근을 한 곳에 모은다.
 *
 * 상위 계층(레포지토리·hook·컴포넌트)은 이 모듈만 거쳐 브라우저 저장소에 접근한다.
 * SSR 가드, 접근 실패(비활성화·프라이빗 모드·쿼터 초과) 시의 조용한 폴백, JSON
 * 직렬화를 여기서 전부 처리하므로 개별 레포지토리는 도메인 로직에만 집중할 수 있다.
 * 나중에 DB(Supabase 등)로 옮길 때도 이 모듈의 구현만 교체하면 된다.
 */

export type StorageArea = "local" | "session";

function resolveArea(area: StorageArea): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return area === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readRawItem(area: StorageArea, key: string): string | null {
  const storage = resolveArea(area);
  if (!storage) {
    return null;
  }
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

/** 저장 성공 여부를 반환한다(쿼터 초과 등으로 실패 시 false) — 호출자가 실패 시
 * 별도 정리(예: 이전 값 삭제)를 해야 하는 경우를 위해 존재한다. 신경 쓰지 않는
 * 호출자는 반환값을 무시해도 된다(실패해도 예외를 던지지 않는다). */
export function writeRawItem(area: StorageArea, key: string, value: string): boolean {
  const storage = resolveArea(area);
  if (!storage) {
    return false;
  }
  try {
    storage.setItem(key, value);
    return true;
  } catch {
    // 쿼터 초과·프라이빗 모드 등: 예외는 삼키고 실패만 알린다.
    return false;
  }
}

export function removeItem(area: StorageArea, key: string): void {
  const storage = resolveArea(area);
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(key);
  } catch {
    // ignore
  }
}

export function removeItemsWithPrefix(area: StorageArea, prefix: string): void {
  const storage = resolveArea(area);
  if (!storage) {
    return;
  }
  try {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(prefix)) keys.push(key);
    }
    keys.forEach((key) => storage.removeItem(key));
  } catch {
    // ignore
  }
}

export function readJsonItem<T>(area: StorageArea, key: string, fallback: T): T {
  const raw = readRawItem(area, key);
  if (!raw) {
    return fallback;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJsonItem(area: StorageArea, key: string, value: unknown): void {
  writeRawItem(area, key, JSON.stringify(value));
}

export function dispatchStorageEvent(eventName: string): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(eventName));
  }
}

export function onStorageAreaKeyChanged(key: string, handler: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const listener = (event: StorageEvent) => {
    if (event.key === key) {
      handler();
    }
  };
  window.addEventListener("storage", listener);
  return () => window.removeEventListener("storage", listener);
}

// ---------------------------------------------------------------------------
// IndexedDB: 단일 스토어 key-value 접근. 대용량 분석 결과 캐시(analysis/season-trend)에
// 사용한다. DB 열기는 3초 타임아웃으로 보호한다(브라우저별 IndexedDB 훅 오류 대비).
// ---------------------------------------------------------------------------

const IDB_OPEN_TIMEOUT_MS = 3000;

function openIndexedDbStore(dbName: string, storeName: string): Promise<IDBDatabase | null> {
  if (typeof window === "undefined" || !("indexedDB" in window)) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (db: IDBDatabase | null) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      resolve(db);
    };
    const timer = window.setTimeout(() => finish(null), IDB_OPEN_TIMEOUT_MS);
    const request = window.indexedDB.open(dbName, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(storeName)) {
        db.createObjectStore(storeName);
      }
    };
    request.onsuccess = () => finish(request.result);
    request.onerror = () => finish(null);
    request.onblocked = () => finish(null);
  });
}

export async function idbGetItem<T>(dbName: string, storeName: string, key: string): Promise<T | null> {
  const db = await openIndexedDbStore(dbName, storeName);
  if (!db) {
    return null;
  }
  return new Promise((resolve) => {
    const transaction = db.transaction(storeName, "readonly");
    const request = transaction.objectStore(storeName).get(key);
    request.onsuccess = () => resolve((request.result as T | undefined) ?? null);
    request.onerror = () => resolve(null);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => db.close();
  });
}

export async function idbSetItem(dbName: string, storeName: string, key: string, value: unknown): Promise<void> {
  const db = await openIndexedDbStore(dbName, storeName);
  if (!db) {
    return;
  }
  await new Promise<void>((resolve) => {
    const transaction = db.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).put(value, key);
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      resolve();
    };
  });
}

export async function idbDeleteItem(dbName: string, storeName: string, key: string): Promise<void> {
  const db = await openIndexedDbStore(dbName, storeName);
  if (!db) {
    return;
  }
  await new Promise<void>((resolve) => {
    const transaction = db.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).delete(key);
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      resolve();
    };
  });
}
