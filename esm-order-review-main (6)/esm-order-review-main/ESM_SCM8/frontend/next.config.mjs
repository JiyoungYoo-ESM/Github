import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function normalizeBackendInternalBaseUrl(value) {
  const raw = value?.trim().replace(/\/$/, "");
  if (!raw) return "";
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(raw)) {
    throw new Error("FASTAPI_INTERNAL_BASE_URL must be an absolute http(s) URL.");
  }
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("FASTAPI_INTERNAL_BASE_URL must be an absolute http(s) URL.");
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error("FASTAPI_INTERNAL_BASE_URL must use http or https.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("FASTAPI_INTERNAL_BASE_URL must not contain credentials, a query, or a fragment.");
  }
  if (parsed.pathname !== "/" && parsed.pathname !== "") {
    throw new Error("FASTAPI_INTERNAL_BASE_URL must be the backend origin without an /api path.");
  }
  return parsed.origin;
}

const backendInternalBaseUrl = normalizeBackendInternalBaseUrl(
  process.env.FASTAPI_INTERNAL_BASE_URL
);
const backendApiBaseUrl = backendInternalBaseUrl || "http://127.0.0.1:8002";

if (process.env.NODE_ENV === "production" && !backendInternalBaseUrl) {
  throw new Error(
    "FASTAPI_INTERNAL_BASE_URL must be set in production so /backend-api can reach the backend."
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  serverExternalPackages: ["exceljs"],
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.0.5", "192.168.0.245"],
  experimental: {
    proxyClientMaxBodySize: "300mb"
  },
  turbopack: {
    root: __dirname
  },
  async rewrites() {
    return [
      {
        source: "/backend-api/:path*",
        destination: `${backendApiBaseUrl}/api/:path*`
      },
      {
        source: "/api/:path*",
        destination: `${backendApiBaseUrl}/api/:path*`
      }
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" }
        ]
      }
    ];
  }
};

export default nextConfig;
export { normalizeBackendInternalBaseUrl };
