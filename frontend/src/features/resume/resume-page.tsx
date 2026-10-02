"use client";

import { History, Loader2 } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";

import { $api, type ReviewSummary } from "@/api/client";
import { Pill } from "@/components/badges";
import { EmptyState, PageHeader, Section } from "@/components/blocks";
import { useQueryParam } from "@/hooks/use-query-param";
import { useRefresh } from "@/hooks/use-refresh";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ResumeForm } from "./resume-form";
import { ResumeReportView, scoreTone } from "./resume-report";

const GRADE: Record<string, string> = { intern: "Стажёр", junior: "Junior", middle: "Middle", senior: "Senior", lead: "Lead" };
const running = (r?: Pick<ReviewSummary, "status"> | null) => r?.status === "pending" || r?.status === "running";

function Progress({ review }: { review: ReviewSummary }) {
  return (
    <Section>
      <div className="flex items-center gap-3">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
        <div>
          <b>
            Проверяю: {review.role} · {GRADE[review.grade]}
          </b>
          <p className="text-sm text-muted-foreground">{review.progress || "Начинаю"}</p>
        </div>
      </div>
    </Section>
  );
}

function HistoryList({ items, selected, onSelect }: { items: ReviewSummary[]; selected: number; onSelect: (id: number) => void }) {
  return (
    <Section
      title={
        <>
          <History className="size-[18px]" />
          История
        </>
      }
      description="Проверяйте после каждой правки: отчёт покажет, что стало лучше"
    >
      {items.length ? (
        <ul className="-mx-2 flex flex-col">
          {items.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onSelect(r.id)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-sm hover:bg-surface-2",
                  r.id === selected && "bg-brand-soft hover:bg-brand-soft",
                )}
              >
                <span className="min-w-0 flex-1">
                  <b className="block truncate font-semibold">
                    {r.role} · {GRADE[r.grade]}
                  </b>
                  <span className="block truncate text-[13px] text-muted-foreground">
                    {ago(r.created_at)} · {r.source_name}
                    {r.use_ai ? " · ИИ" : ""}
                  </span>
                </span>
                {r.status === "done" && r.score != null ? (
                  <Pill tone={scoreTone(r.score)} className="tabular-nums">
                    {r.score}
                  </Pill>
                ) : r.status === "error" ? (
                  <Pill tone="danger">ошибка</Pill>
                ) : (
                  <Loader2 className="size-4 animate-spin text-muted-foreground" />
                )}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState emoji="📄" title="Проверок пока не было">
          Загрузите резюме, и здесь появится история с баллами
        </EmptyState>
      )}
    </Section>
  );
}

export function ResumePage() {
  const [idParam, setIdParam] = useQueryParam<string>("id", "");
  const selected = Number(idParam) || 0;
  const refresh = useRefresh();

  const history = $api.useQuery(
    "get",
    "/api/resume-reviews",
    {},
    {
      refetchInterval: (q) => (q.state.data?.some(running) ? 2000 : false),
    },
  );
  const detail = $api.useQuery(
    "get",
    "/api/resume-reviews/{rid}",
    { params: { path: { rid: selected } } },
    { enabled: selected > 0, refetchInterval: (q) => (running(q.state.data) ? 1500 : false) },
  );
  const rerun = $api.useMutation("post", "/api/resume-reviews/{rid}/rerun");
  const remove = $api.useMutation("delete", "/api/resume-reviews/{rid}");

  // open the latest review when nothing is selected
  const items = useMemo(() => history.data ?? [], [history.data]);
  useEffect(() => {
    if (!selected && items.length) setIdParam(String(items[0].id));
  }, [selected, items, setIdParam]);

  // when the review you watch finishes, refresh the history (scores) once;
  // keyed by id, so opening another, already finished review is not a «finish»
  const runningId = useRef<number | null>(null);
  const d = detail.data;
  useEffect(() => {
    if (d && runningId.current === d.id && !running(d)) {
      void refresh("/api/resume-reviews");
      if (d.status === "done") toast.success(`Готово: ${d.score} из 100`);
      if (d.status === "error") toast.error(d.error || "Проверка не удалась");
    }
    runningId.current = d && running(d) ? d.id : null;
  }, [d, refresh]);

  const open = (id: number) => {
    setIdParam(String(id));
    void refresh("/api/resume-reviews");
  };

  return (
    <>
      <PageHeader
        title="Проверка резюме"
        description="Прогоню резюме через проверки для роли и грейда, сравню с реальными вакансиями и подскажу, что улучшить"
      />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0">
          <ResumeForm onStarted={open} />
          {d && running(d) && <Progress review={d} />}
          {d?.status === "error" && (
            <Section className="bg-danger-soft">
              <b>Проверка не удалась</b>
              <p className="mt-1 text-sm">{d.error}</p>
            </Section>
          )}
          {d?.status === "done" && d.report && (
            <ResumeReportView
              summary={d}
              report={d.report}
              busy={rerun.isPending}
              onRerun={async () => open((await rerun.mutateAsync({ params: { path: { rid: d.id } } })).id)}
              onDelete={async () => {
                await remove.mutateAsync({ params: { path: { rid: d.id } } });
                // refresh first: with the old list the «open the latest» effect would reopen the deleted review
                await refresh("/api/resume-reviews");
                setIdParam("");
                toast.success("Отчёт удалён");
              }}
            />
          )}
        </div>
        <HistoryList items={items} selected={selected} onSelect={open} />
      </div>
    </>
  );
}
