import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { GoogleAnalytics } from "@/components/analytics/GoogleAnalytics";
import { AppRouteLoader } from "@/components/layout/AppRouteLoader";
import "./globals.css";

export const metadata: Metadata = {
  title: "ESM SCM Dashboard",
  description: "Local Next.js client for the ESM SCM FastAPI backend"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <AuthGuard>{children}</AuthGuard>
        <Suspense fallback={null}>
          <AppRouteLoader />
        </Suspense>
        <GoogleAnalytics />
      </body>
    </html>
  );
}
