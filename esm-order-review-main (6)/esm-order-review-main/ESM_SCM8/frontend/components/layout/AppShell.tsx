import { AppSidebar } from "@/components/layout/AppSidebar";
import { AppBreadcrumbs } from "@/components/layout/AppBreadcrumbs";
import { GlobalSkuSearch } from "@/components/layout/GlobalSkuSearch";
import { AnalysisReadinessBanner } from "@/components/analysis/AnalysisReadinessBanner";
import { EntityIntegrationNotice } from "@/components/auth/EntityIntegrationNotice";
import { EntitySelector } from "@/components/auth/EntitySelector";

type AppShellProps = {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
};

export function AppShell({ title, description, actions, children }: AppShellProps) {
  return (
    <main className="flex min-h-screen bg-cloud">
      <AppSidebar />
      <div className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1680px] px-4 py-4 lg:px-6">
          <header className="mb-4 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <AppBreadcrumbs />
              <h1 className="mt-1 text-xl font-black tracking-normal text-black lg:text-2xl">{title}</h1>
              {description ? <p className="mt-2 text-sm font-semibold text-slate-500">{description}</p> : null}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <EntitySelector />
              <GlobalSkuSearch />
              {actions}
            </div>
          </header>
          <AnalysisReadinessBanner />
          <EntityIntegrationNotice />
          {children}
        </div>
      </div>
    </main>
  );
}
