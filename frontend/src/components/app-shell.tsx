"use client";

import { Suspense, type ReactNode } from "react";

import { ActivityBar } from "@/components/activity-bar";
import { AppSidebar, Logo } from "@/components/app-sidebar";
import { ReviewDeck } from "@/components/review-deck";
import { SearchDialog } from "@/components/search-dialog";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { VacancyPanel } from "@/components/vacancy-panel";
import { useHydrated } from "@/hooks/use-hydrated";

/** Shown until the page can use the browser: every screen is built from the local API, not on the server. */
function PageSkeleton() {
  return (
    <div aria-busy className="space-y-4">
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-5 w-96 max-w-full" />
      <Skeleton className="h-40 rounded-2xl" />
      <Skeleton className="h-64 rounded-2xl" />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const hydrated = useHydrated();
  return (
    <SidebarProvider style={{ "--sidebar-width": "240px" } as React.CSSProperties}>
      <AppSidebar />
      <SidebarInset className="bg-background">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b bg-card px-4 py-2.5 md:hidden">
          <SidebarTrigger />
          <Logo />
          <b className="font-extrabold">kolenke</b>
        </header>
        <main className="w-full max-w-[1100px] min-w-0 px-4 pt-6 pb-32 md:px-10 md:pt-9">
          {hydrated ? <Suspense fallback={<PageSkeleton />}>{children}</Suspense> : <PageSkeleton />}
        </main>
      </SidebarInset>
      <VacancyPanel />
      <ReviewDeck />
      <SearchDialog />
      <ActivityBar />
    </SidebarProvider>
  );
}
