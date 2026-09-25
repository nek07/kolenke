"use client";

import { AlertCircle, Check, Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { $api, type Answer } from "@/api/client";
import { Pill } from "@/components/badges";
import { Banner, PageHeader, ProgressBar, Section } from "@/components/blocks";
import { Confirm } from "@/components/confirm-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useRefresh } from "@/hooks/use-refresh";
import { celebrate } from "@/lib/celebrate";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A topic being edited; new ones get a negative key until saved. */
type Draft = { key: number; id: number | null; topic: string; keywords: string; answer: string };

const toDraft = (a: Answer): Draft => ({ key: a.id ?? 0, id: a.id, topic: a.topic, keywords: a.keywords, answer: a.answer });
let nextKey = -1;

function TestQuestion({ onCreate }: { onCreate: (topic: string) => void }) {
  const [q, setQ] = useState("");
  const [asked, setAsked] = useState("");
  const { data: r } = $api.useQuery("get", "/api/answers/match", { params: { query: { q: asked } } }, { enabled: !!asked });
  return (
    <Section
      title={
        <>
          <Search className="size-[18px]" />
          Проверить вопрос
        </>
      }
      description="Вставьте вопрос работодателя и посмотрите, что ответит бот"
    >
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setAsked(q.trim());
        }}
      >
        <Input
          aria-label="Вопрос"
          placeholder="Например: Какие у вас зарплатные ожидания?"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Button type="submit" variant="outline">
          Проверить
        </Button>
      </form>
      {asked && r && (
        <div className="mt-2.5">
          {!r.topic ? (
            <Banner
              tone="info"
              icon={<AlertCircle />}
              title="Подходящей темы нет. Бот передаст вопрос вам"
              action={
                <Button size="sm" variant="outline" onClick={() => onCreate(asked.slice(0, 60))}>
                  Создать тему
                </Button>
              }
            />
          ) : r.answer ? (
            <Banner tone="success" icon={<Check />} title={`Тема «${r.topic}». Бот ответит: ${r.answer}`} />
          ) : (
            <Banner tone="warning" icon={<AlertCircle />} title={`Тема «${r.topic}» найдена, но ответ пустой. Заполните его ниже`} />
          )}
        </div>
      )}
    </Section>
  );
}

function NewQuestions({ onAnswer }: { onAnswer: (text: string) => void }) {
  const refresh = useRefresh();
  const { data: questions } = $api.useQuery("get", "/api/questions");
  const remove = $api.useMutation("delete", "/api/questions/{qid}");
  if (!questions?.length) return null;
  const drop = async (qid: number) => {
    await remove.mutateAsync({ params: { path: { qid } } });
    await refresh("/api/questions");
  };
  return (
    <Section
      title="Новые вопросы от работодателей"
      description="На эти вопросы в базе пока нет ответа. Добавьте, и в следующий раз бот ответит сам"
    >
      <ul>
        {questions.map((q) => (
          <li key={q.id} className="flex items-center gap-3 border-b border-muted py-2.5 last:border-0">
            <span className="grid size-[30px] flex-none place-items-center rounded-[9px] bg-warning-soft text-warning">
              <AlertCircle className="size-[15px]" />
            </span>
            <div className="min-w-0 flex-1 text-sm">
              {q.text}
              <div className="text-[13px] text-muted-foreground">
                {q.source === "chat" ? "из чата" : "из анкеты"} · встречался {q.seen} {plural(q.seen, "раз", "раза", "раз")}
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                onAnswer(q.text.slice(0, 60));
                void drop(q.id);
              }}
            >
              Ответить
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label="Убрать" onClick={() => drop(q.id)}>
              <X />
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function TopicRow({ d, onChange, onDelete }: { d: Draft; onChange: (d: Draft) => void; onDelete: () => void }) {
  const ok = !!d.answer.trim();
  return (
    <div id={`topic-${d.key}`} className="grid grid-cols-[28px_1fr] gap-3 border-b border-muted py-4 last:border-0">
      <span
        className={cn(
          "mt-[7px] grid size-[22px] place-items-center rounded-full border-2",
          ok ? "border-success bg-success text-white" : "border-border text-transparent",
        )}
        aria-label={ok ? "Ответ есть" : "Ответа нет"}
      >
        <Check className="size-3.5 stroke-3" />
      </span>
      <div>
        <div className="flex gap-2">
          <input
            aria-label="Тема"
            className="min-w-0 flex-1 bg-transparent py-0.5 text-base font-bold outline-none"
            placeholder="Название темы"
            value={d.topic}
            onChange={(e) => onChange({ ...d, topic: e.target.value })}
          />
          {d.id != null ? (
            <Confirm
              title="Удалить тему?"
              description="Бот перестанет отвечать на такие вопросы сам"
              confirm="Удалить"
              onConfirm={onDelete}
            >
              <Button size="icon-sm" variant="ghost" aria-label="Удалить тему">
                <X />
              </Button>
            </Confirm>
          ) : (
            <Button size="icon-sm" variant="ghost" aria-label="Убрать тему" onClick={onDelete}>
              <X />
            </Button>
          )}
        </div>
        <Input
          aria-label="Ключевые слова"
          className="my-1 mb-2 bg-surface-2 text-[13px] text-ink-2"
          placeholder="ключевые слова через запятую"
          value={d.keywords}
          onChange={(e) => onChange({ ...d, keywords: e.target.value })}
        />
        <Textarea
          aria-label="Ответ"
          className="min-h-[46px]"
          placeholder="Ваш ответ. Пусто — бот спросит вас"
          value={d.answer}
          onChange={(e) => onChange({ ...d, answer: e.target.value })}
        />
      </div>
    </div>
  );
}

export function AnswersPage() {
  const refresh = useRefresh();
  const { data } = $api.useQuery("get", "/api/answers");
  const save = $api.useMutation("put", "/api/answers");
  const remove = $api.useMutation("delete", "/api/answers/{aid}");
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const items = drafts ?? data?.map(toDraft) ?? [];

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const edit = (next: Draft[]) => {
    setDrafts(next);
    setDirty(true);
  };
  function addTopic(topic = "") {
    const d: Draft = { key: nextKey--, id: null, topic, keywords: "", answer: "" };
    edit([d, ...items]);
    requestAnimationFrame(() => {
      const row = document.getElementById(`topic-${d.key}`);
      row?.scrollIntoView({ behavior: "smooth", block: "center" });
      row?.querySelector<HTMLInputElement>(topic ? '[aria-label="Ключевые слова"]' : '[aria-label="Тема"]')?.focus();
    });
  }

  const filled = items.filter((d) => d.answer.trim()).length;
  const complete = items.length > 0 && filled === items.length;

  async function submit() {
    const before = (data ?? []).filter((a) => a.answer.trim()).length;
    await save.mutateAsync({ body: { items: items.map(({ id, topic, keywords, answer }) => ({ id, topic, keywords, answer })) } });
    setDrafts(null);
    setDirty(false);
    await refresh("/api/answers", "/api/answers/match");
    if (complete && filled > before) celebrate("База ответов заполнена полностью! Бот готов отвечать за вас 🎉");
    else toast.success("Сохранено. Теперь бот знает больше");
  }

  return (
    <>
      <PageHeader
        title="База ответов"
        description="Один раз расскажите о себе, и бот будет отвечать на типовые вопросы HR и анкеты за вас"
      />
      <Section
        title="Готовность базы"
        actions={
          <Pill tone={complete ? "success" : "brand"}>{`${filled} из ${items.length} ${plural(items.length, "темы", "тем", "тем")}`}</Pill>
        }
      >
        <ProgressBar value={items.length ? (filled * 100) / items.length : 0} />
        <p className="mt-2.5 text-[13px] text-muted-foreground">
          Бот ищет в вопросе <b>ключевые слова</b> (можно писать части слов: «зарплат» подходит и к «зарплата», и к «зарплатные»). Если
          ответ пустой, бот не отвечает сам и передаёт вопрос вам.
        </p>
      </Section>
      <TestQuestion onCreate={addTopic} />
      <NewQuestions onAnswer={addTopic} />
      <Section
        title="Темы"
        actions={
          <Button size="sm" variant="outline" onClick={() => addTopic()}>
            <Plus />
            Новая тема
          </Button>
        }
      >
        {items.map((d) => (
          <TopicRow
            key={d.key}
            d={d}
            onChange={(next) => edit(items.map((x) => (x.key === d.key ? next : x)))}
            onDelete={async () => {
              if (d.id == null) return edit(items.filter((x) => x.key !== d.key));
              await remove.mutateAsync({ params: { path: { aid: d.id } } });
              setDrafts(drafts ? drafts.filter((x) => x.key !== d.key) : null);
              await refresh("/api/answers");
            }}
          />
        ))}
      </Section>
      {dirty && (
        <div className="sticky bottom-5 mt-4 flex items-center gap-3 rounded-2xl bg-foreground py-3 pr-3.5 pl-[18px] text-background">
          <span className="flex-1">Есть несохранённые изменения</span>
          <Button variant="brand" disabled={save.isPending} onClick={submit}>
            Сохранить
          </Button>
        </div>
      )}
    </>
  );
}
