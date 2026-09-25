"use client";

import { Check, ExternalLink, Mail, User, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { $api, type Stage, type VacancyDetail } from "@/api/client";
import { HhStateBadge, MatchBadge, Pill, VacancyStatusBadge } from "@/components/badges";
import { Hint } from "@/components/blocks";
import { useUI } from "@/components/providers/ui-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";
import { celebrate } from "@/lib/celebrate";
import { dateTime, gentle, messageParts, whenText } from "@/lib/format";
import { cn } from "@/lib/utils";

export const STAGES: [Stage, string][] = [
  ["applied", "Отклик"],
  ["viewed", "Просмотрен"],
  ["invited", "Приглашение"],
  ["interview", "Собеседование"],
  ["offer", "Оффер"],
  ["declined", "Не сейчас"],
];

const STAGE_PARTY: Partial<Record<Stage, string>> = {
  invited: "Приглашение! Вас заметили — это ваш результат 🎉",
  interview: "Собеседование! Подготовьтесь спокойно, у вас всё получится 💪",
  offer: "Оффер! Поздравляем, это большая победа 🎉",
};

const EVENT_DOT: Record<string, string> = {
  filtered: "border-destructive",
  queued: "border-info",
  applied: "border-success bg-success",
  letter: "border-success bg-success",
  form: "border-info",
  attention: "border-warning bg-brand",
  error: "border-destructive",
  employer: "border-warning bg-brand",
  stage: "border-success bg-success",
  plan: "border-info",
  followup: "border-info",
  contact: "border-success bg-success",
};

/** Moving a card on the board or in the panel: same celebration everywhere. */
export function useSetStage() {
  const refresh = useRefresh();
  const m = $api.useMutation("patch", "/api/vacancies/{vid}/pipeline");
  return async (vid: number, stage: Stage) => {
    await m.mutateAsync({ params: { path: { vid } }, body: { stage } });
    const party = STAGE_PARTY[stage];
    if (party) celebrate(party);
    else if (stage === "declined") toast.info("Не в этот раз. Опыт засчитан, идём дальше");
    else toast.success("Этап обновлён");
    await refresh(...VACANCY_VIEWS);
  };
}

function H({ children }: { children: ReactNode }) {
  return <h4 className="mt-6 mb-2.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">{children}</h4>;
}

function Box({ label, children }: { label?: ReactNode; children: ReactNode }) {
  return (
    <div className="mb-2 rounded-xl border border-muted px-3 py-2.5 text-sm">
      {label && <div className="mb-1 text-[13px] text-muted-foreground">{label}</div>}
      {children}
    </div>
  );
}

export function Contacts({ contacts, full }: { contacts: VacancyDetail["contacts"] | undefined; full?: boolean }) {
  const c = contacts ?? { emails: [], phones: [], telegram: [], person: "" };
  const chip = "mr-1 mb-1 inline-flex max-w-[230px] items-center gap-1 truncate rounded-lg bg-muted px-2 py-0.5 text-[12.5px] no-underline";
  const items = [
    ...(c.emails ?? []).map((e) => (
      <a key={e} className={cn(chip, "hover:bg-brand-soft")} href={`mailto:${e}`}>
        <Mail className="size-3" />
        {e}
      </a>
    )),
    ...(c.phones ?? []).slice(0, full ? 9 : 1).map((p) => (
      <span key={p} className={chip}>
        {p}
      </span>
    )),
    ...(c.telegram ?? []).slice(0, full ? 9 : 1).map((t) => (
      <a key={t} className={cn(chip, "hover:bg-brand-soft")} href={`https://t.me/${t.slice(1)}`} target="_blank" rel="noreferrer">
        {t}
      </a>
    )),
    ...(full && c.person
      ? [
          <span key="person" className={chip}>
            <User className="size-3" />
            {c.person}
          </span>,
        ]
      : []),
  ];
  return items.length ? (
    <div className="flex max-w-[240px] flex-wrap">{items}</div>
  ) : (
    <span className="text-sm text-muted-foreground">—</span>
  );
}

export function Place({ v }: { v: Pick<VacancyDetail, "location" | "country" | "remote"> }) {
  return (
    <div>
      {v.location}
      {v.country && !(v.location ?? "").includes(v.country) && <div className="text-[13px] text-muted-foreground">{v.country}</div>}
      {!!v.remote && (
        <div>
          <Pill tone="info">можно удалённо</Pill>
        </div>
      )}
    </div>
  );
}

function PipelineEditor({ v }: { v: VacancyDetail }) {
  const refresh = useRefresh();
  const setStage = useSetStage();
  const save = $api.useMutation("patch", "/api/vacancies/{vid}/pipeline");
  const [step, setStep] = useState(v.next_step ?? "");
  const [at, setAt] = useState(v.next_at?.slice(0, 16) ?? "");
  const [notes, setNotes] = useState(v.notes ?? "");
  const current = v.stage ?? "applied";

  async function submit(body: { next_step: string; next_at: string; notes?: string }) {
    await save.mutateAsync({ params: { path: { vid: v.id } }, body });
    toast.success(body.next_at ? `Запомнил. Напомню ${whenText(body.next_at).toLowerCase()}` : "Сохранено");
    await refresh(...VACANCY_VIEWS);
  }

  return (
    <>
      <H>Этап</H>
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Этап">
        {STAGES.map(([id, label]) => (
          <button
            key={id}
            role="radio"
            aria-checked={id === current}
            onClick={() => id !== current && setStage(v.id, id)}
            className={cn(
              "rounded-full border-[1.5px] px-3 py-1 text-[13px] font-semibold text-ink-2",
              id === current ? "border-foreground bg-foreground text-background" : "bg-card hover:border-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {!!v.stage_manual && <Hint>Этап выставлен вручную. Ответы с hh его не откатят назад</Hint>}
      <H>Следующий шаг</H>
      <div className="grid grid-cols-2 gap-2">
        <Input aria-label="Следующий шаг" placeholder="Собеседование, тестовое…" value={step} onChange={(e) => setStep(e.target.value)} />
        <Input aria-label="Когда" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
      </div>
      <Hint>Напомню на Mac за сутки и за час</Hint>
      <H>Заметки</H>
      <Textarea
        className="min-h-20"
        placeholder="Имя рекрутера, вопросы, впечатления…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="mt-2.5 flex gap-2">
        <Button
          size="sm"
          variant="brand"
          disabled={save.isPending}
          onClick={() => submit({ next_step: step, next_at: at ? `${at}:00` : "", notes })}
        >
          Сохранить
        </Button>
        {v.next_at && (
          <Button size="sm" variant="ghost" onClick={() => submit({ next_step: "", next_at: "" })}>
            Убрать шаг
          </Button>
        )}
      </div>
      {v.followup === "sent" && <Hint>Вы уже напоминали о себе в чате</Hint>}
    </>
  );
}

function OtherSiteBlock({ v }: { v: VacancyDetail }) {
  const refresh = useRefresh();
  const toCompanies = $api.useMutation("post", "/api/vacancies/to-companies");
  return (
    <>
      {v.summary && (
        <>
          <H>Кратко</H>
          <p className="text-sm">{v.summary}</p>
        </>
      )}
      <H>Где</H>
      {v.location || v.country || v.remote ? <Place v={v} /> : <span className="text-sm text-muted-foreground">не указано</span>}
      {v.skills && <Hint>{v.skills}</Hint>}
      <H>Контакты</H>
      <Contacts contacts={v.contacts} full />
      {v.company_url && (
        <Hint>
          <a href={v.company_url} target="_blank" rel="noreferrer" className="underline">
            Страница компании
          </a>
        </Hint>
      )}
      {!!v.contacts?.emails?.length && (
        <Button
          size="sm"
          variant="outline"
          className="mt-2.5"
          onClick={async () => {
            const r = await toCompanies.mutateAsync({ body: { ids: [v.id] } });
            toast.success(r.added ? `В «Письма компаниям» добавлено адресов: ${r.added}` : "Эти адреса уже есть в списке");
            await refresh("/api/companies", "/api/vacancies/{vid}");
          }}
        >
          <Mail />В письма компаниям
        </Button>
      )}
    </>
  );
}

function PanelBody({ v }: { v: VacancyDetail }) {
  const refresh = useRefresh();
  const setStatus = $api.useMutation("patch", "/api/vacancies/status");
  // events are recorded since v1.3; older rows get their history rebuilt from what is known
  const events = v.events.length
    ? v.events
    : [
        { ts: v.created_at ?? "", kind: "found", text: "Найдена в поиске" },
        ...(v.applied_at
          ? [{ ts: v.applied_at, kind: "applied", text: `Отклик отправлен${v.resume ? ` с резюме «${v.resume}»` : ""}` }]
          : []),
        ...(v.hh_state ? [{ ts: v.hh_state_at ?? "", kind: "employer", text: `Работодатель: ${v.hh_state}` }] : []),
      ];
  const failed = v.status === "skipped" && v.match_info.some((r) => !r.ok);

  async function move(status: "queued" | "skipped" | "new") {
    await setStatus.mutateAsync({ body: { ids: [v.id], status } });
    toast.success(status === "queued" ? "В очереди на отклик" : "Готово");
    await refresh(...VACANCY_VIEWS);
  }

  return (
    <>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <VacancyStatusBadge status={v.status} />
        <HhStateBadge state={v.hh_state} />
        {v.skill_match != null && <MatchBadge value={v.skill_match} label="навыки " />}
        {v.salary_text && <Pill>{v.salary_text}</Pill>}
        {v.experience && <Pill>{v.experience}</Pill>}
      </div>
      <div className="mt-3.5 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" asChild>
          <a href={v.url} target="_blank" rel="noreferrer">
            <ExternalLink />
            Открыть вакансию
          </a>
        </Button>
        {v.status === "new" && (
          <>
            <Button size="sm" variant="brand" onClick={() => move("queued")}>
              Откликнуться
            </Button>
            <Button size="sm" variant="outline" onClick={() => move("skipped")}>
              Пропустить
            </Button>
          </>
        )}
        {v.status === "skipped" && (
          <Button size="sm" variant="outline" onClick={() => move("new")}>
            Вернуть в новые
          </Button>
        )}
      </div>

      {v.source !== "hh" && <OtherSiteBlock v={v} />}
      {v.status === "applied" && <PipelineEditor key={`${v.id}-${v.next_at}-${v.stage}`} v={v} />}

      <H>История</H>
      <ol className="relative pl-[22px] before:absolute before:top-1.5 before:bottom-1.5 before:left-1.5 before:w-0.5 before:bg-muted">
        {events.map((e, i) => (
          <li key={i} className="relative pb-3.5 text-sm">
            <span
              className={cn("absolute top-[5px] -left-5 size-2.5 rounded-full border-2 bg-card", EVENT_DOT[e.kind] ?? "border-border")}
            />
            {gentle(e.text)}
            <time className="block text-[12.5px] text-muted-foreground">{dateTime(e.ts)}</time>
          </li>
        ))}
      </ol>

      {v.match_info.length ? (
        <>
          <H>Почему {failed ? "не прошла" : "прошла"} фильтры</H>
          <ul className="flex flex-col gap-1.5 text-sm">
            {v.match_info.map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                {r.ok ? <Check className="mt-0.5 size-4 text-success" /> : <X className="mt-0.5 size-4 text-destructive" />}
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <H>Фильтры</H>
          <Hint className="mt-0">Вакансия найдена до появления умных фильтров, причины не записаны</Hint>
        </>
      )}

      {(v.applied_at || v.resume) && (
        <>
          <H>Отклик</H>
          <Box label="Резюме">{v.resume || "неизвестно"}</Box>
        </>
      )}
      {v.letter ? (
        <Box label="Сопроводительное письмо">
          <div className="whitespace-pre-wrap">{v.letter}</div>
        </Box>
      ) : (
        v.letter_sent === 0 && <Box label="Сопроводительное письмо">Не ушло. Можно дослать кнопкой «Дослать письма»</Box>
      )}
      {!!v.form_answers.length && (
        <>
          <H>Ответы в анкете</H>
          {v.form_answers.map((a, i) => (
            <Box key={i} label={a.q}>
              {a.a}
            </Box>
          ))}
        </>
      )}
      {v.status === "attention" && v.note && (
        <>
          <H>Анкета</H>
          <Box>
            {v.note}
            <Hint>Добавьте ответы в «Базу ответов» и верните вакансию в очередь</Hint>
          </Box>
        </>
      )}

      <H>Переписка</H>
      {v.chats.length ? (
        v.chats.map((c) => (
          <Box key={c.id} label={`${c.robot ? "HR-робот" : "Работодатель"} · ${dateTime(c.created_at)}`}>
            <div className="whitespace-pre-wrap">{messageParts(c.message).join("\n\n")}</div>
            {c.reply && c.status !== "pending" && c.status !== "info" && (
              <div className="mt-2 border-t border-muted pt-2">
                <span className="text-[13px] text-muted-foreground">
                  {c.status === "auto_sent" ? "Ответил бот" : "Вы ответили"} · {dateTime(c.sent_at)}
                </span>
                <div>{c.reply}</div>
              </div>
            )}
            {c.status === "pending" && <Hint>Ждёт вашего ответа на вкладке «Чаты»</Hint>}
          </Box>
        ))
      ) : (
        <Hint className="mt-0">Сообщений от работодателя пока нет</Hint>
      )}

      <H>Реакция работодателя</H>
      {v.hh_state ? (
        <div className="flex items-center gap-2">
          <HhStateBadge state={v.hh_state} />
          <span className="text-[13px] text-muted-foreground">обновлено {dateTime(v.hh_state_at)}</span>
        </div>
      ) : (
        <Hint className="mt-0">Ещё нет данных. Нажмите «Обновить ответы с hh» на «Воронке»</Hint>
      )}
    </>
  );
}

/** The side panel with everything about one vacancy. Any screen opens it with useUI().openVacancy(id). */
export function VacancyPanel() {
  const { vacancyId, closeVacancy } = useUI();
  const { data: v, isPending } = $api.useQuery(
    "get",
    "/api/vacancies/{vid}",
    { params: { path: { vid: vacancyId ?? 0 } } },
    { enabled: vacancyId != null },
  );
  return (
    <Sheet open={vacancyId != null} onOpenChange={(open) => !open && closeVacancy()}>
      <SheetContent className="w-full overflow-y-auto px-6 pt-6 pb-16 sm:max-w-[520px]">
        <SheetHeader className="p-0 pr-8">
          <SheetTitle className="text-[21px] leading-tight font-extrabold tracking-[-0.02em]">{v?.title}</SheetTitle>
          <SheetDescription className="text-[14.5px]">{v?.company}</SheetDescription>
        </SheetHeader>
        {isPending || !v ? (
          <div className="mt-4 space-y-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-24" />
            <Skeleton className="h-40" />
          </div>
        ) : (
          <PanelBody v={v} />
        )}
      </SheetContent>
    </Sheet>
  );
}
