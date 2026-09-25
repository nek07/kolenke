"use client";

import { CalendarDays, RefreshCw } from "lucide-react";
import { useState, type DragEvent } from "react";

import { $api, type Schemas, type Stage } from "@/api/client";
import { PageHeader } from "@/components/blocks";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import { Button } from "@/components/ui/button";
import { useSetStage } from "@/components/vacancy-panel";
import { daysAgo, plural, whenText } from "@/lib/format";
import { cn } from "@/lib/utils";

type Card = Schemas["PipelineCard"];

const DOT: Record<Stage, string> = {
  applied: "bg-muted-foreground",
  viewed: "bg-info",
  invited: "bg-success",
  interview: "bg-success",
  offer: "bg-brand",
  declined: "bg-border",
};

const EMPTY_TEXT: Partial<Record<Stage, string>> = {
  offer: "Скоро здесь будет ваш оффер ✨",
  declined: "Пусто — и это хорошо",
};

function PipelineCardView({ card, onOpen }: { card: Card; onOpen: () => void }) {
  const late = card.next_at && new Date(card.next_at) < new Date();
  return (
    <button
      type="button"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", String(card.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={onOpen}
      className="mb-2 block w-full cursor-grab rounded-xl border bg-card px-3 py-2.5 text-left text-sm hover:border-ink-2/40 active:cursor-grabbing"
    >
      <b className="line-clamp-2 leading-tight font-semibold">{card.title}</b>
      <div className="mt-0.5 text-[13px] text-muted-foreground">{card.company}</div>
      {card.next_at ? (
        <div
          className={cn(
            "mt-2 inline-flex items-center gap-1.5 rounded-lg px-2 py-0.5 text-[12.5px] font-semibold",
            late ? "bg-muted text-muted-foreground" : "bg-brand-soft",
          )}
        >
          <CalendarDays className="size-3" />
          {whenText(card.next_at)}
          {card.next_step && ` · ${card.next_step}`}
        </div>
      ) : (
        <div className="mt-1.5 text-[13px] text-muted-foreground">
          {card.applied_at || card.created_at ? `отклик ${daysAgo(card.applied_at || card.created_at)}` : ""}
          {card.notes && " · 📝"}
        </div>
      )}
    </button>
  );
}

export function PipelinePage() {
  const { data } = $api.useQuery("get", "/api/pipeline");
  const { run } = useTasks();
  const { openVacancy } = useUI();
  const setStage = useSetStage();
  const [over, setOver] = useState<Stage | null>(null);

  const cards = data?.cards ?? [];
  const active = cards.filter((c) => c.stage !== "declined").length;
  const good = cards.filter((c) => c.stage && ["invited", "interview", "offer"].includes(c.stage)).length;

  function drop(e: DragEvent, stage: Stage) {
    e.preventDefault();
    setOver(null);
    const id = Number(e.dataTransfer.getData("text/plain"));
    const card = cards.find((c) => c.id === id);
    if (card && (card.stage ?? "applied") !== stage) void setStage(id, stage);
  }

  return (
    <>
      <PageHeader
        title="Воронка"
        description="Что происходит после отклика. Перетаскивайте карточки, когда что-то меняется. Ответы с hh двигают их сами"
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => run("hh_sync")}>
          <RefreshCw />
          Обновить ответы с hh
        </Button>
        <span className="flex-1" />
        <span className="text-[13px] text-muted-foreground">
          {active} в процессе · {good} {plural(good, "приглашение", "приглашения", "приглашений")} и дальше
        </span>
      </div>
      <div className="flex items-start gap-3 overflow-x-auto pb-3">
        {data?.stages.map((st) => {
          const inStage = cards.filter((c) => (c.stage ?? "applied") === st.id);
          return (
            <section
              key={st.id}
              aria-label={st.label}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(st.id);
              }}
              onDragLeave={() => setOver((o) => (o === st.id ? null : o))}
              onDrop={(e) => drop(e, st.id)}
              className={cn(
                "min-h-[120px] w-[250px] flex-none rounded-2xl bg-muted p-2.5 outline-2 outline-transparent outline-dashed transition-colors",
                over === st.id && "bg-brand-soft outline-foreground",
                st.id === "declined" && "opacity-75",
              )}
            >
              <h3 className="mx-1.5 mt-1 mb-2.5 flex items-center gap-2 text-sm font-bold">
                <span className={cn("size-[9px] rounded-full", DOT[st.id])} />
                {st.label}
                <span className="ml-auto font-semibold text-muted-foreground">{inStage.length}</span>
              </h3>
              {inStage.length ? (
                inStage.map((c) => <PipelineCardView key={c.id} card={c} onOpen={() => openVacancy(c.id)} />)
              ) : (
                <div className="px-1.5 py-3.5 text-center text-[13px] text-muted-foreground">
                  {EMPTY_TEXT[st.id] ?? "Перетащите сюда карточку"}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
