import { getActiveEntityCode } from "@/lib/entity-session";
import { readRawItem, writeRawItem } from "@/lib/storage/adapter";

export const CLIENT_ID_STORAGE_KEY = "esm_scm_client_id";

export function randomClientId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `client_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export function getClientId(): string {
  if (typeof window === "undefined") return "server";
  const stored = readRawItem("local", CLIENT_ID_STORAGE_KEY);
  if (stored) return stored;
  const next = randomClientId();
  writeRawItem("local", CLIENT_ID_STORAGE_KEY, next);
  return next;
}

export function requestContextHeaders(): Record<string, string> {
  const entityCode = getActiveEntityCode();
  return {
    "X-Client-Id": getClientId(),
    ...(entityCode ? { "X-Entity-Code": entityCode } : {})
  };
}

export function clientHeaders(): HeadersInit {
  return { "X-Client-Id": getClientId() };
}
