"use client";

import { Square } from "lucide-react";

import { useTasks } from "@/components/providers/tasks";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The running background task, with «Стоп». Slides in from the bottom while something runs. */
export function ActivityBar() {
  const { status, stop } = useTasks();
  const running = !!status?.running;
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "fixed bottom-[22px] left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-full bg-foreground py-2.5 pr-2.5 pl-[18px] font-medium text-background transition-transform duration-300",
        running ? "translate-y-0" : "pointer-events-none translate-y-[120px]",
      )}
    >
      <span className="size-4 animate-spin rounded-full border-2 border-background/40 border-t-brand" aria-hidden />
      <span>{status?.job ? `${status.job}…` : ""}</span>
      <Button size="sm" variant="secondary" className="rounded-full bg-background/20 text-background hover:bg-background/30" onClick={stop}>
        <Square />
        Стоп
      </Button>
    </div>
  );
}
