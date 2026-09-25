"use client";

import { Check, ExternalLink, Send, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { $api, type Vacancy } from "@/api/client";
import { EmptyState, ProgressBar } from "@/components/blocks";
import { Pill } from "@/components/badges";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";
import { pluralN } from "@/lib/format";
import { cn } from "@/lib/utils";

type Pick = "queued" | "skipped";

function Deck({ items, onClose }: { items: Vacancy[]; onClose: () => void }) {
  const { run } = useTasks();
  const setStatus = $api.useMutation("patch", "/api/vacancies/status");
  const [i, setI] = useState(0);
  const [history, setHistory] = useState<Pick[]>([]);
  const [leaving, setLeaving] = useState<Pick | null>(null);
  const v = items[i];
  const yes = history.filter((h) => h === "queued").length;

  const pick = useCallback(
    async (status: Pick) => {
      if (!v || leaving) return;
      setLeaving(status);
      try {
        await setStatus.mutateAsync({ body: { ids: [v.id], status, review: true } });
        setHistory((h) => [...h, status]);
        setI((n) => n + 1);
      } finally {
        setLeaving(null);
      }
    },
    [v, leaving, setStatus],
  );

  async function undo() {
    if (!history.length) return;
    const prev = items[i - 1];
    await setStatus.mutateAsync({ body: { ids: [prev.id], status: "new" } });
    setHistory((h) => h.slice(0, -1));
    setI((n) => n - 1);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement).closest("input,textarea")) return;
      if (e.key === "ArrowRight") void pick("queued");
      if (e.key === "ArrowLeft") void pick("skipped");
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [pick]);

  return (
    <div className="mx-auto max-w-[560px] px-4 pt-7 pb-10">
      <div className="mb-4 flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X />
          Закрыть
        </Button>
        <span className="flex-1" />
        {!!history.length && (
          <Button variant="ghost" size="sm" onClick={undo}>
            <Undo2 />
            Вернуть
          </Button>
        )}
        <Pill>
          {Math.min(i + 1, items.length)} из {items.length}
        </Pill>
      </div>
      <ProgressBar value={items.length ? (i * 100) / items.length : 0} className="mb-5" />

      {!v ? (
        <div className="rounded-[20px] border-[1.5px] border-foreground bg-card p-6 shadow-hard-lg">
          <EmptyState emoji={yes ? "🎯" : "✨"} title={items.length ? "Все карточки просмотрены" : "Новых вакансий нет"}>
            {items.length
              ? `Откликнуться: ${yes}, пропустить: ${history.length - yes}`
              : "Когда автопилот найдёт свежие, придёт уведомление"}
          </EmptyState>
          {yes > 0 && (
            <>
              <Button
                variant="brand"
                className="h-12 w-full text-[15.5px]"
                onClick={() => {
                  onClose();
                  void run("hh_apply");
                }}
              >
                <Send />
                Отправить {pluralN(yes, "отклик", "отклика", "откликов")} сейчас
              </Button>
              <p className="mt-3 text-center text-[13px] text-muted-foreground">
                Или закройте: если автопилот включён, он отправит их в следующем цикле
              </p>
            </>
          )}
        </div>
      ) : (
        <article
          key={v.id}
          className={cn(
            "animate-[fade-in_.2s] rounded-[20px] border-[1.5px] border-foreground bg-card p-6 shadow-hard-lg transition-all duration-200",
            leaving === "queued" && "translate-x-10 rotate-3 opacity-0",
            leaving === "skipped" && "-translate-x-10 -rotate-3 opacity-0",
          )}
        >
          <div className="mb-1.5 text-[14.5px] text-muted-foreground">{v.company}</div>
          <h2 className="text-2xl leading-tight font-extrabold tracking-[-0.02em]">{v.title}</h2>
          <div className="my-[18px] flex flex-wrap gap-2.5">
            {[
              ["Совпадение навыков", v.skill_match != null ? `${v.skill_match}%` : "—"],
              ["Зарплата", v.salary_text || "не указана"],
              ...(v.experience ? [["Опыт", v.experience]] : []),
            ].map(([label, value]) => (
              <div key={label} className="min-w-[120px] flex-1 rounded-xl border border-muted bg-surface-2 px-3 py-2.5">
                <small className="text-[12.5px] text-muted-foreground">{label}</small>
                <b className="block text-[17px] font-extrabold tracking-[-0.01em]">{value}</b>
              </div>
            ))}
          </div>
          <ReviewReasons id={v.id} />
          <Button size="sm" variant="outline" className="mt-4" asChild>
            <a href={v.url} target="_blank" rel="noreferrer">
              <ExternalLink />
              Открыть вакансию на hh
            </a>
          </Button>
          <div className="mt-[18px] grid grid-cols-2 gap-3">
            <Button variant="outline" className="h-12 text-[15.5px]" onClick={() => pick("skipped")}>
              Пропустить <kbd className="rounded border px-1 font-mono text-[11px] opacity-70">←</kbd>
            </Button>
            <Button variant="brand" className="h-12 text-[15.5px]" onClick={() => pick("queued")}>
              Откликнуться <kbd className="rounded border border-foreground/40 px-1 font-mono text-[11px] opacity-70">→</kbd>
            </Button>
          </div>
        </article>
      )}
    </div>
  );
}

/** Why the vacancy passed the filters: loaded per card, the list endpoint leaves the reasons out. */
function ReviewReasons({ id }: { id: number }) {
  const { data } = $api.useQuery("get", "/api/vacancies/{vid}", { params: { path: { vid: id } } });
  if (!data?.match_info.length) return null;
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {data.match_info.map((r, k) => (
        <li key={k} className="flex items-start gap-2">
          {r.ok ? <Check className="mt-0.5 size-4 text-success" /> : <X className="mt-0.5 size-4 text-destructive" />}
          <span>{r.text}</span>
        </li>
      ))}
    </ul>
  );
}

/** Fresh vacancies one by one: «Откликнуться» → or «Пропустить» ←. Best skill match first. */
export function ReviewDeck() {
  const { reviewOpen, setReviewOpen } = useUI();
  const refresh = useRefresh();
  // the queue is taken once when the deck opens, so answered cards don't jump out from under you
  const { data: items } = $api.useQuery("get", "/api/vacancies/review", {}, { enabled: reviewOpen, staleTime: Infinity, gcTime: 0 });
  const close = () => {
    setReviewOpen(false);
    void refresh(...VACANCY_VIEWS);
  };
  return (
    <Dialog open={reviewOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent
        showCloseButton={false}
        className="h-dvh max-w-none overflow-auto rounded-none border-0 bg-background p-0 sm:max-w-none"
      >
        <DialogTitle className="sr-only">Проверка вакансий</DialogTitle>
        <DialogDescription className="sr-only">Откликнуться или пропустить каждую новую вакансию</DialogDescription>
        {items && <Deck items={items} onClose={close} />}
      </DialogContent>
    </Dialog>
  );
}
