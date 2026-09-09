import { publishAuthSessionChange } from "@/lib/auth-events";
import { requestContextHeaders } from "./request-context";

const activeRequestControllers = new Set<AbortController>();

function isDirectAuthCheck(input: string): boolean {
  return /\/auth\/(?:login|me)(?:[/?#]|$)/.test(input);
}

/** The sole browser transport boundary: cookies, CSRF and entity context. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const requestController = new AbortController();
  const abortFromCaller = () => requestController.abort();
  if (init.signal?.aborted) requestController.abort();
  else init.signal?.addEventListener("abort", abortFromCaller, { once: true });
  activeRequestControllers.add(requestController);
  try {
    const response = await fetch(input, {
      ...init,
      signal: requestController.signal,
      credentials: "include",
      headers: {
        ...(init.headers as Record<string, string> | undefined),
        ...requestContextHeaders(),
        "X-Requested-With": "fetch"
      }
    });
    if (response.status === 401 && !isDirectAuthCheck(input)) {
      publishAuthSessionChange("unauthorized");
    }
    return response;
  } finally {
    activeRequestControllers.delete(requestController);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }
}

export function abortActiveApiRequests(): void {
  for (const controller of activeRequestControllers) controller.abort();
  activeRequestControllers.clear();
}

/**
 * 법인 전환·로그아웃에서 우리가 끊은 요청인지 판별한다. 사용자가 겪은 실패가 아니므로
 * 콘솔에 찍거나 화면에 "조회 실패"로 표시하면 안 된다.
 */
export function isAbortError(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { name?: unknown }).name === "AbortError";
}

export class ApiRequestError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export async function parseApiError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown; error?: { message?: unknown } };
    if (typeof body.error?.message === "string") return body.error.message;
    if (typeof body.detail === "string") return body.detail;
    if (body.detail) return JSON.stringify(body.detail);
  } catch {
    // Use the status fallback below when the response has no JSON body.
  }
  if (response.status === 504) return "서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.";
  return response.statusText || `HTTP ${response.status}`;
}

export function wait(ms = 350): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
