"use client";

import {
  AlertCircle,
  CalendarDays,
  Check,
  Clock,
  Mail,
  MessageCircle,
  PenLine,
  Search,
  Send,
  Sparkles,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { $api, type Schemas } from "@/api/client";
import { AutopilotSwitch, useAutopilotText } from "@/components/autopilot-switch";
import { Funnel } from "@/components/funnel";
import { EmptyState, ProgressBar, Section } from "@/components/blocks";
import { Pill } from "@/components/badges";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import { Button } from "@/components/ui/button";
import { useSettings } from "@/hooks/use-settings";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";
import { celebrate, memory } from "@/lib/celebrate";
import { ago, daysAgo, INVITE_RE, isoDay, plural, pluralN, whenText } from "@/lib/format";
import { cn } from "@/lib/utils";

import { FollowupDialog } from "./followup-dialog";

const MOTTOS = [
  "Каждый отклик — ещё один шанс. Вы на верном пути.",
  "Отказ — это просто «не сейчас». Следующий ответ может быть «да».",
  "Ранний отклик замечают чаще. Автопилот поможет успевать первым.",
  "Маленькие шаги каждый день складываются в большой результат.",
  "Хорошие ответы в базе — меньше рутины для вас.",
  "Сегодня отличный день, чтобы получить приглашение.",
];

function greeting(name: string) {
  const h = new Date().getHours();
  const hello = h < 5 ? "Доброй ночи" : h < 12 ? "Доброе утро" : h < 18 ? "Добрый день" : "Добрый вечер";
  return `${hello}${name ? `, ${name}` : ""} 👋`;
}

/** Days in a row with at least one response or letter; a single missed day is forgiven. */
function softStreak(byDay: Schemas["DayCount"][]) {
  const active = new Set(byDay.filter((d) => d.hh > 0 || d.mail > 0).map((d) => d.day));
  const d = new Date();
  if (!active.has(isoDay(d))) d.setDate(d.getDate() - 1);
  let n = 0;
  let miss = 0;
  for (let i = 0; i < 120; i++) {
    if (active.has(isoDay(d))) {
      n++;
      miss = 0;
    } else if (++miss > 1) break;
    d.setDate(d.getDate() - 1);
  }
  return n;
}

function WeekGoal({ stats }: { stats: Schemas["Stats"] | undefined }) {
  const { status } = useTasks();
  const { data: s } = useSettings();
  const w = status?.week;
  const goal = s?.hh_weekly_goal ?? 150;
  const streak = stats ? softStreak(stats.by_day) : 0;
  return (
    <div className="rounded-2xl border-[1.5px] border-foreground bg-brand p-[22px] text-[#141414] shadow-hard-lg md:col-span-2 lg:col-span-1">
      <div className="text-[14.5px] font-bold">Приглашения за неделю</div>
      <div className="mt-2 mb-1.5 text-[64px] leading-none font-extrabold tracking-[-0.04em] tabular-nums">{w?.invites ?? 0}</div>
      <div className="text-[14.5px] font-medium">
        {w?.rate != null ? (
          <>
            <b className="font-extrabold">{String(w.rate).replace(".", ",")}%</b> откликов заканчиваются приглашением
          </>
        ) : (
          "Доля приглашений появится после первых ответов работодателей"
        )}
      </div>
      <div className="mt-4 flex flex-col gap-1.5 text-[12.5px] opacity-75">
        <span>
          Откликов за неделю: {w?.applied ?? 0} из {goal}
        </span>
        <ProgressBar value={((w?.applied ?? 0) * 100) / goal} className="h-[5px] bg-[#141414]/12" barClassName="bg-[#141414]" />
      </div>
      {streak >= 2 && (
        <div
          className="mt-3 inline-flex rounded-full bg-[#141414] px-3 py-0.5 text-[12.5px] font-bold text-white"
          title="Один пропущенный день серию не обнуляет"
        >
          🔥 {pluralN(streak, "день", "дня", "дней")} в ритме
        </div>
      )}
    </div>
  );
}

function AutopilotCard() {
  const { data: s } = useSettings();
  const text = useAutopilotText();
  const review = s?.autopilot_mode !== "auto";
  const on = !!s?.autopilot_on;
  return (
    <div className="rounded-2xl border bg-card p-[22px]">
      <div className="flex items-center">
        <label htmlFor="today-autopilot" className="text-[13.5px] font-medium text-muted-foreground">
          Автопилот
        </label>
        <span className="flex-1" />
        <AutopilotSwitch id="today-autopilot" />
      </div>
      <div className={cn("mt-3.5 text-[22px] font-extrabold tracking-[-0.03em]", on && "text-success")}>
        {on ? (review ? "Работает, с проверкой" : "Работает сам") : "На паузе"}
      </div>
      <p className="mt-1 text-[13px] text-muted-foreground">
        {on
          ? text
          : review
            ? "Включите — бот будет находить свежие вакансии, а вы решать, куда откликнуться"
            : "Включите — и бот будет откликаться на свежие вакансии сам"}
      </p>
    </div>
  );
}

function Waiting() {
  const { status } = useTasks();
  const { setReviewOpen } = useUI();
  const items: [LucideIcon, string, string | (() => void)][] = [];
  if (status?.review)
    items.push([
      Sparkles,
      `${status.review} ${plural(status.review, "вакансия ждёт", "вакансии ждут", "вакансий ждут")} проверки`,
      () => setReviewOpen(true),
    ]);
  if (status?.chats_pending)
    items.push([
      MessageCircle,
      `${status.chats_pending} ${plural(status.chats_pending, "сообщение ждёт", "сообщения ждут", "сообщений ждут")} ответа`,
      "/chats",
    ]);
  if (status?.attention)
    items.push([
      PenLine,
      `${status.attention} ${plural(status.attention, "анкета ждёт", "анкеты ждут", "анкет ждут")} ответов`,
      "/hh?status=attention",
    ]);
  const queued = status?.vacancies.queued ?? 0;
  if (queued) items.push([Send, `${queued} в очереди на отклик`, "/hh?status=queued"]);
  return (
    <div className="rounded-2xl border bg-card p-[22px]">
      <span className="text-[13.5px] font-medium text-muted-foreground">Ждут вашего внимания</span>
      <div className="mt-2.5 flex flex-col gap-2">
        {items.length ? (
          items.map(([Icon, label, target]) =>
            typeof target === "string" ? (
              <Button key={label} variant="outline" className="h-auto justify-start py-2" asChild>
                <Link href={target}>
                  <Icon />
                  {label}
                </Link>
              </Button>
            ) : (
              <Button key={label} variant="outline" className="h-auto justify-start py-2" onClick={target}>
                <Icon />
                {label}
              </Button>
            ),
          )
        ) : (
          <>
            <div className="text-[22px] font-extrabold tracking-[-0.03em]">Всё спокойно</div>
            <p className="text-[13px] text-muted-foreground">Ничего не требует вашего внимания</p>
          </>
        )}
      </div>
    </div>
  );
}

function When({ at, soft, children }: { at?: string; soft?: boolean; children?: React.ReactNode }) {
  const [day, time] = at ? whenText(at).split(" ") : [];
  return (
    <div
      className={cn(
        "min-w-[74px] flex-none rounded-[10px] border-[1.5px] px-2 py-1.5 text-center text-[13px] leading-tight",
        soft ? "border-border bg-muted font-semibold text-ink-2" : "border-foreground bg-brand font-extrabold text-brand-foreground",
      )}
    >
      {children ?? (
        <>
          {day}
          <br />
          {time}
        </>
      )}
    </div>
  );
}

function Reminders() {
  const { openVacancy } = useUI();
  const refresh = useRefresh();
  const { data: r } = $api.useQuery("get", "/api/reminders");
  const close = $api.useMutation("post", "/api/vacancies/{vid}/followup/close");
  const [followup, setFollowup] = useState<number | null>(null);
  if (!r || !(r.past.length + r.upcoming.length + r.followups.length)) return null;
  const row = "flex items-center gap-3 border-b border-muted py-2.5 last:border-0";
  return (
    <Section
      title={
        <>
          <CalendarDays className="size-[18px]" />
          Напоминания
        </>
      }
      actions={
        <Button variant="ghost" size="sm" asChild>
          <Link href="/pipeline">Вся воронка</Link>
        </Button>
      }
    >
      {r.past.map((p) => (
        <div key={`p${p.id}`} className={row}>
          <When at={p.next_at} soft />
          <div className="min-w-0 flex-1">
            <b>Как прошло? {p.next_step}</b>
            <div className="text-[13px] text-muted-foreground">
              {p.company} · {p.title}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => openVacancy(p.id)}>
            Отметить итог
          </Button>
        </div>
      ))}
      {r.upcoming.map((p) => (
        <div key={`u${p.id}`} className={row}>
          <When at={p.next_at} />
          <div className="min-w-0 flex-1">
            <b>{p.next_step || "Следующий шаг"}</b>
            <div className="text-[13px] text-muted-foreground">
              {p.company} · {p.title}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => openVacancy(p.id)}>
            Открыть
          </Button>
        </div>
      ))}
      {r.followups.slice(0, 5).map((f) => (
        <div key={`f${f.id}`} className={row}>
          <When soft>
            <Clock className="mx-auto size-4" />
          </When>
          <div className="min-w-0 flex-1">
            <b>{daysAgo(f.sent).replace(" назад", "")} без ответа — напомнить о себе?</b>
            <div className="text-[13px] text-muted-foreground">
              {f.company} · {f.title}
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setFollowup(f.id)}>
            Написать
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Не нужно"
            onClick={async () => {
              await close.mutateAsync({ params: { path: { vid: f.id } }, body: { action: "dismissed" } });
              await refresh(...VACANCY_VIEWS);
            }}
          >
            <X />
          </Button>
        </div>
      ))}
      {r.followups.length > 5 && <p className="mt-2 text-[13px] text-muted-foreground">и ещё {r.followups.length - 5} без ответа</p>}
      <FollowupDialog vacancyId={followup} onClose={() => setFollowup(null)} />
    </Section>
  );
}

function Setup() {
  const { data: s } = useSettings();
  const { data: answers } = $api.useQuery("get", "/api/answers");
  if (!s || !answers) return null;
  const filled = answers.filter((a) => a.answer.trim()).length;
  const items: [boolean, string, string][] = [
    [!!s.full_name, "Представьтесь: имя и телефон", "/settings"],
    [!!s.hh_resume_hash, "Подключите hh и выберите резюме", "/hh"],
    [filled >= 5, `Заполните базу ответов (${filled} из 5+)`, "/answers"],
    [s.autopilot_on, "Включите автопилот", "/hh"],
    [!!(s.smtp_user && s.has_password && s.resume_name), "Подключите Gmail и резюме для писем (по желанию)", "/settings"],
  ];
  const done = items.filter(([ok]) => ok).length;
  if (done === items.length) return null;
  return (
    <Section title="Настроим всё за пару минут" actions={<Pill tone="brand">{`${done} из ${items.length}`}</Pill>}>
      <ProgressBar value={(done * 100) / items.length} className="mb-3" />
      <div className="flex flex-col gap-0.5">
        {items.map(([ok, label, href]) => (
          <Link key={label} href={href} className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-medium hover:bg-surface-2">
            <span
              className={cn(
                "grid size-[22px] flex-none place-items-center rounded-full border-2",
                ok ? "border-success bg-success text-white" : "border-border",
              )}
            >
              {ok && <Check className="size-3.5 stroke-3" />}
            </span>
            <span className={cn(ok && "text-muted-foreground line-through")}>{label}</span>
          </Link>
        ))}
      </div>
    </Section>
  );
}

function feedIcon(msg: string): [LucideIcon, string] {
  if (/ошибк|не удалось|капч/i.test(msg)) return [AlertCircle, "bg-danger-soft text-destructive"];
  if (/✓|отправлен|ответил|загружено/i.test(msg)) return [Check, "bg-success-soft text-success"];
  if (/чат/i.test(msg)) return [MessageCircle, "bg-info-soft text-info"];
  if (/почт|письм/i.test(msg)) return [Mail, "bg-brand-soft text-warning"];
  if (/поиск|найдено|страниц/i.test(msg)) return [Search, "bg-muted text-ink-2"];
  if (/^▶|автопилот/i.test(msg)) return [Zap, "bg-brand-soft text-warning"];
  return [Clock, "bg-muted text-ink-2"];
}

function Feed() {
  const { status } = useTasks();
  const [full, setFull] = useState(false);
  const log = (status?.log ?? []).slice(0, full ? 80 : 8);
  return (
    <Section
      title="Что происходит"
      className="mb-0"
      actions={
        <Button variant="ghost" size="sm" onClick={() => setFull(!full)}>
          {full ? "Свернуть" : "Весь журнал"}
        </Button>
      }
    >
      {log.length ? (
        <ul>
          {log.map((l, i) => {
            const [Icon, tone] = feedIcon(l.msg);
            return (
              <li key={`${l.ts}${i}`} className="flex gap-3 border-b border-muted py-2.5 last:border-0">
                <span className={cn("grid size-[30px] flex-none place-items-center rounded-[9px]", tone)}>
                  <Icon className="size-[15px]" />
                </span>
                <span className="flex-1 text-sm">{l.msg.replace(/^▶\s*/, "Запущено: ").replace(/^hh:\s*/, "")}</span>
                <time className="text-[12.5px] whitespace-nowrap text-muted-foreground">{ago(l.ts)}</time>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState emoji="☀️" title="Здесь будет видно всё, что делает бот">
          Запустите поиск или включите автопилот
        </EmptyState>
      )}
    </Section>
  );
}

/** Confetti for a new invitation and for the weekly goal, once per event in this browser. */
function useCelebrations(stats: Schemas["Stats"] | undefined) {
  const { status } = useTasks();
  const { data: s } = useSettings();
  useEffect(() => {
    if (!stats) return;
    const invites = stats.hh_states.filter((x) => INVITE_RE.test(x.state)).reduce((a, x) => a + x.n, 0);
    const seen = memory.get<number | null>("invites", null);
    if (seen !== null && invites > seen) celebrate("У вас новое приглашение! Это ваш результат 🎉");
    memory.set("invites", invites);
  }, [stats]);
  useEffect(() => {
    const w = status?.week;
    const goal = s?.hh_weekly_goal;
    if (!w || !goal || w.applied < goal || memory.get(`wgoal-${w.start}`, false)) return;
    memory.set(`wgoal-${w.start}`, true);
    celebrate("Недельная цель по откликам выполнена! Дальше в своём темпе 💪");
  }, [status?.week, s?.hh_weekly_goal]);
}

export function TodayPage() {
  const { data: s } = useSettings();
  const { data: stats } = $api.useQuery("get", "/api/stats");
  useCelebrations(stats);
  const name = (s?.full_name ?? "").trim().split(/\s+/)[0] ?? "";
  return (
    <>
      <header className="mb-6">
        <h1 className="text-[25px] leading-tight font-extrabold tracking-[-0.03em] md:text-[30px]">{greeting(name)}</h1>
        <p className="mt-1.5 text-ink-2">{MOTTOS[new Date().getDate() % MOTTOS.length]}</p>
      </header>
      <div className="mb-4 grid gap-4 md:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr]">
        <WeekGoal stats={stats} />
        <AutopilotCard />
        <Waiting />
      </div>
      <Reminders />
      <Setup />
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Путь откликов" description="Как работодатели реагируют на ваши отклики на hh" className="mb-0">
          <Funnel states={stats?.hh_states ?? []} />
        </Section>
        <Feed />
      </div>
    </>
  );
}
