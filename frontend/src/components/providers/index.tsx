"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import { TasksProvider } from "./tasks";
import { UIStateProvider } from "./ui-state";

function makeQueryClient() {
  return new QueryClient({
    // one place that tells you what went wrong; status polling stays quiet when the backend is down
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.quiet || query.queryKey[1] === "/api/status") return;
        toast.error(errorMessage(error));
      },
    }),
    mutationCache: new MutationCache({ onError: (error) => toast.error(errorMessage(error)) }),
    defaultOptions: {
      queries: { staleTime: 5_000, refetchOnWindowFocus: true, retry: 1 },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <UIStateProvider>
          <TasksProvider>{children}</TasksProvider>
        </UIStateProvider>
      </TooltipProvider>
      <Toaster position="top-right" richColors closeButton />
    </QueryClientProvider>
  );
}
