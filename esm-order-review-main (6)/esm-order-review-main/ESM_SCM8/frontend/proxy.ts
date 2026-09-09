import { NextResponse, type NextRequest } from "next/server";

const backendOrigin = (process.env.FASTAPI_INTERNAL_BASE_URL || "http://127.0.0.1:8002").replace(/\/$/, "");

function loginResponse(request: NextRequest) {
  const returnTo = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const loginUrl = new URL(`/login?next=${encodeURIComponent(returnTo)}`, request.url);
  return NextResponse.redirect(loginUrl);
}

/**
 * Files in public/ bypass client-side AuthGuard. Protect internal guides and
 * reports at the edge before Next serves the static asset.
 */
export async function proxy(request: NextRequest) {
  const cookie = request.headers.get("cookie");
  if (!cookie) return loginResponse(request);

  try {
    const response = await fetch(`${backendOrigin}/api/auth/me`, {
      headers: { cookie },
      cache: "no-store"
    });
    if (response.status === 401 || response.status === 403) return loginResponse(request);
    if (!response.ok) {
      return new NextResponse("Authentication service unavailable", { status: 503 });
    }
    const session = (await response.json()) as { authenticated?: boolean };
    return session.authenticated
      ? NextResponse.next()
      : loginResponse(request);
  } catch {
    return new NextResponse("Authentication service unavailable", { status: 503 });
  }
}

export const config = {
  matcher: ["/docs/:path*", "/reports/:path*"]
};
