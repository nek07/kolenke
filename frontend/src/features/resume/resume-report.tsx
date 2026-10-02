"use client";

import { Check, CircleAlert, Copy, Download, ExternalLink, RefreshCw, Sparkles, Trash2, TrendingDown, TrendingUp, X } from "lucide-react";
import { toast } from "sonner";

import type { ResumeReport, ReviewSummary, Schemas } from "@/api/client";
import { Pill } from "@/components/badges";
import { EmptyState, ProgressBar, Section } from "@/components/blocks";
import { Confirm } from "@/components/confirm-button";
import { Button } from "@/components/ui/button";
import { pluralN } from "@/lib/format";
import { cn } from "@/lib/utils";

type CheckItem = Schemas["Check"];

const GRADE: Record<string, string> = { intern: "Стажёр", junior: "Junior", middle: "Middle", senior: "Senior", lead: "Lead" };

export const scoreTone = (score: number) => (score >= 80 ? "success" : score >= 60 ? "info" : score >= 40 ? "warning" : "danger");

function years(months: number | null | undefined): string {
  if (months == null) return "не удалось посчитать";
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? pluralN(y, "год", "года", "лет") : "", m ? `${m} мес.` : ""].filter(Boolean).join(" ") || "меньше месяца";
}

function StatusIcon({ status }: { status: CheckItem["status"] }) {
  const cls = "grid size-[22px] shrink-0 place-items-center rounded-full [&_svg]:size-[13px] [&_svg]:stroke-3";
  if (status === "pass")
    return (
      <span className={cn(cls, "bg-success text-white")} aria-label="пройдено">
        <Check />
      </span>
    );
  if (status === "warn")
    return (
      <span className={cn(cls, "bg-warning-soft text-warning")} aria-label="стоит улучшить">
        <CircleAlert />
      </span>
    );
  return (
    <span className={cn(cls, "bg-danger-soft text-destructive")} aria-label="не пройдено">
      <X />
    </span>
  );
}

function Hero({ report, summary }: { report: ResumeReport; summary: ReviewSummary }) {
  const d = report.diff;
  const f = report.facts;
  return (
    <section className="mb-4 grid gap-4 rounded-2xl border-[1.5px] border-foreground bg-brand p-5 text-[#141414] shadow-hard-lg md:grid-cols-[auto_1fr] md:p-6">
      <div className="flex items-end gap-1.5">
        <b className="text-[64px] leading-none font-extrabold tracking-[-0.04em] tabular-nums">{report.score}</b>
        <span className="mb-2 text-sm font-semibold opacity-70">из 100</span>
      </div>
      <div className="min-w-0">
        <p className="text-lg font-bold tracking-[-0.01em]">{report.verdict}</p>
        <p className="mt-1 text-sm opacity-80">
          {report.role} · {GRADE[report.grade]}
          {report.role_profile && report.role_profile !== report.role ? ` · профиль «${report.role_profile}»` : ""} · {summary.source_name}
        </p>
        <p className="mt-1 text-sm opacity-80">
          Стаж по датам: {years(f.experience_months)} · {pluralN(f.words, "слово", "слова", "слов")}
          {f.contacts.length ? ` · контакты: ${f.contacts.join(", ")}` : ""}
        </p>
        {d && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#141414] px-3 py-1 font-bold text-white">
              {d.score_delta >= 0 ? <TrendingUp className="size-4" /> : <TrendingDown className="size-4" />}
              {d.score_delta >= 0 ? "+" : ""}
              {d.score_delta} с прошлой проверки ({d.previous_score})
            </span>
            {d.same_resume && <span className="opacity-80">Резюме то же: изменился рынок</span>}
            {d.fixed.length > 0 && <span>Исправлено: {d.fixed.join(", ")}</span>}
            {d.new_issues.length > 0 && <span className="opacity-80">Хуже стало: {d.new_issues.join(", ")}</span>}
          </div>
        )}
      </div>
    </section>
  );
}

function AiBlock({ ai }: { ai: ResumeReport["ai"] }) {
  if (!ai.used) return null;
  if (ai.error)
    return (
      <Section title="ИИ-разбор" className="bg-warning-soft">
        <p className="text-sm">{ai.error}. Остальной отчёт собран без ИИ.</p>
      </Section>
    );
  const tone = ai.grade_fit === "соответствует" ? "success" : ai.grade_fit === "ниже" ? "warning" : "info";
  return (
    <Section
      title={
        <>
          <Sparkles className="size-[18px]" />
          Мнение ИИ
        </>
      }
      actions={ai.grade_fit ? <Pill tone={tone}>Грейд: {ai.grade_fit}</Pill> : null}
    >
      <p className="leading-relaxed">{ai.summary}</p>
      {ai.grade_comment && <p className="mt-2 text-sm text-ink-2">{ai.grade_comment}</p>}
    </Section>
  );
}

function ListBlock({ title, items, tone }: { title: string; items: string[]; tone: "success" | "danger" }) {
  return (
    <Section title={title} className="mb-0">
      {items.length ? (
        <ul className="flex flex-col gap-2 text-sm">
          {items.map((x) => (
            <li key={x} className="flex gap-2">
              <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", tone === "success" ? "bg-success" : "bg-destructive")} />
              <span>{x}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{tone === "success" ? "Пока нечем похвастаться" : "Серьёзных проблем не нашлось"}</p>
      )}
    </Section>
  );
}

const PRIORITY: Record<number, [string, "danger" | "warning" | "neutral"]> = {
  1: ["Сначала", "danger"],
  2: ["Важно", "warning"],
  3: ["На потом", "neutral"],
};

function Recommendations({ items }: { items: ResumeReport["recommendations"] }) {
  if (!items.length) return null;
  return (
    <Section title="Что сделать" description="По порядку: первые пункты дадут больше всего">
      <ol className="flex flex-col divide-y">
        {items.map((r, i) => {
          const [label, tone] = PRIORITY[r.priority] ?? PRIORITY[3];
          return (
            <li key={`${r.title}-${i}`} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <b className="w-5 shrink-0 text-muted-foreground tabular-nums">{i + 1}</b>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <b className="font-semibold">{r.title}</b>
                  <Pill tone={tone}>{label}</Pill>
                </div>
                <p className="mt-1 text-sm text-ink-2">{r.detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

function Rewrites({ items }: { items: ResumeReport["rewrites"] }) {
  if (!items.length) return null;
  const copy = (text: string) =>
    navigator.clipboard.writeText(text).then(
      () => toast.success("Скопировано"),
      () => toast.error("Не удалось скопировать"),
    );
  return (
    <Section
      title="Как усилить формулировки"
      description="Шаблоны сохраняют ваши факты: заполните [квадратные скобки] своими цифрами. Ничего не выдумывайте"
    >
      <div className="flex flex-col gap-3">
        {items.map((r, i) => (
          <div key={i} className="rounded-xl border bg-surface-2 p-3.5 text-sm">
            <div className="mb-1.5 flex items-center gap-2">
              <Pill tone={r.by_ai ? "info" : "neutral"}>{r.by_ai ? "Вариант ИИ" : "Шаблон"}</Pill>
              <span className="flex-1" />
              <Button variant="ghost" size="sm" onClick={() => copy(r.after)}>
                <Copy />
                Копировать
              </Button>
            </div>
            <p className="text-muted-foreground line-through decoration-muted-foreground/40">{r.before}</p>
            <p className="mt-1.5 font-medium">{r.after}</p>
            <p className="mt-1.5 text-[13px] text-muted-foreground">{r.why}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Checks({ checks }: { checks: CheckItem[] }) {
  const groups = [...new Set(checks.map((c) => c.group))];
  const passed = checks.filter((c) => c.status === "pass").length;
  return (
    <Section title="Проверки" description={`Пройдено ${passed} из ${checks.length}`}>
      <div className="grid gap-5 lg:grid-cols-2">
        {groups.map((g) => (
          <div key={g}>
            <h4 className="mb-2 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">{g}</h4>
            <ul className="flex flex-col gap-3">
              {checks
                .filter((c) => c.group === g)
                .map((c) => (
                  <li key={c.id} className="flex gap-3 text-sm">
                    <StatusIcon status={c.status} />
                    <div className="min-w-0">
                      <b className="font-semibold">{c.title}</b>
                      <p className="text-ink-2">{c.detail}</p>
                      {c.fix && <p className="mt-0.5 text-[13px] text-muted-foreground">→ {c.fix}</p>}
                    </div>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  );
}

const money = (n: number) => n.toLocaleString("ru-RU");
const CURRENCY: Record<string, string> = { KZT: "₸", RUB: "₽", USD: "$", EUR: "€" };
const SOURCE: Record<string, string> = { hh: "hh", habr: "Хабр Карьера", enbek: "Enbek" };

function MarketBlock({ market }: { market: NonNullable<ResumeReport["market"]> }) {
  if (!market.skills.length)
    return (
      <Section title="Рынок">
        <EmptyState emoji="🔍" title="Не с чем сравнить">
          {market.note || "Подходящих вакансий не нашлось: попробуйте назвать роль так, как её пишут в вакансиях"}
        </EmptyState>
      </Section>
    );
  const s = market.salary;
  return (
    <Section
      title="Рынок"
      description={`${pluralN(market.sample_size, "вакансия", "вакансии", "вакансий")} по запросу «${market.query}» · ${market.sources
        .map((x) => SOURCE[x] ?? x)
        .join(", ")}`}
      actions={
        <Pill tone={market.coverage >= 60 ? "success" : market.coverage >= 35 ? "warning" : "danger"}>Покрытие {market.coverage}%</Pill>
      }
    >
      {market.note && <p className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-[13px]">{market.note}</p>}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div>
          <h4 className="mb-2.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">Что просят в вакансиях</h4>
          <ul className="flex flex-col gap-2">
            {market.skills.map((k) => (
              <li key={k.name} className="grid grid-cols-[minmax(0,9rem)_1fr_3rem] items-center gap-3 text-sm">
                <span className={cn("flex items-center gap-1.5 truncate", !k.have && "text-muted-foreground")}>
                  {k.have ? <Check className="size-3.5 shrink-0 text-success" /> : <X className="size-3.5 shrink-0" />}
                  <span className="truncate">{k.name}</span>
                </span>
                <ProgressBar value={k.share} className="h-1.5" barClassName={k.have ? "bg-success" : "bg-muted-foreground/40"} />
                <b className="text-right tabular-nums">{k.share}%</b>
              </li>
            ))}
          </ul>
          <p className="mt-2.5 text-[13px] text-muted-foreground">
            ✓ есть в резюме, ✕ не найдено. Если навыком владеете, а он не отмечен, значит его не видно в тексте
          </p>
        </div>
        <div className="flex flex-col gap-5">
          {s && (
            <div>
              <h4 className="mb-1.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">Зарплаты</h4>
              <p className="text-[22px] font-extrabold tracking-[-0.02em]">
                {money(s.median)} {CURRENCY[s.currency] ?? s.currency}
              </p>
              <p className="text-sm text-ink-2">
                медиана, середина рынка {money(s.low)}–{money(s.high)} · {pluralN(s.count, "вакансия", "вакансии", "вакансий")} с зарплатой
              </p>
            </div>
          )}
          {market.title_words.length > 0 && (
            <div>
              <h4 className="mb-1.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">Слова в названиях</h4>
              <div className="flex flex-wrap gap-1.5">
                {market.title_words.map((w) => (
                  <Pill key={w}>{w}</Pill>
                ))}
              </div>
              <p className="mt-1.5 text-[13px] text-muted-foreground">Используйте их в заголовке резюме: по ним ищут рекрутеры</p>
            </div>
          )}
          {market.examples.length > 0 && (
            <div>
              <h4 className="mb-1.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase">Примеры вакансий</h4>
              <ul className="flex flex-col gap-1.5 text-sm">
                {market.examples.map((v) => (
                  <li key={v.url}>
                    <a href={v.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1.5 hover:underline">
                      <ExternalLink className="mt-0.5 size-3.5 shrink-0" />
                      <span>
                        {v.title}
                        {v.company && <span className="text-muted-foreground"> · {v.company}</span>}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}

export function ResumeReportView({
  summary,
  report,
  onRerun,
  onDelete,
  busy,
}: {
  summary: ReviewSummary;
  report: ResumeReport;
  onRerun: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        <Button variant="outline" asChild>
          <a href={`/api/resume-reviews/${summary.id}/export`} download>
            <Download />
            Скачать отчёт
          </a>
        </Button>
        <Button variant="outline" disabled={busy} onClick={onRerun}>
          <RefreshCw />
          Проверить снова
        </Button>
        <span className="flex-1" />
        <Confirm title="Удалить отчёт?" description="Текст резюме в этой проверке тоже удалится" confirm="Удалить" onConfirm={onDelete}>
          <Button variant="ghost">
            <Trash2 />
            Удалить
          </Button>
        </Confirm>
      </div>
      <Hero report={report} summary={summary} />
      <AiBlock ai={report.ai} />
      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <ListBlock title="Сильные стороны" items={report.strengths} tone="success" />
        <ListBlock title="Что мешает" items={report.weaknesses} tone="danger" />
      </div>
      <Recommendations items={report.recommendations} />
      <Rewrites items={report.rewrites} />
      <Checks checks={report.checks} />
      {report.market && <MarketBlock market={report.market} />}
    </div>
  );
}
