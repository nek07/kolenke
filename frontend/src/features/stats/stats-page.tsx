"use client";

import { Download, RefreshCw } from "lucide-react";

import { $api } from "@/api/client";
import { EmptyState, PageHeader, Section } from "@/components/blocks";
import { Funnel } from "@/components/funnel";
import { useTasks } from "@/components/providers/tasks";
import { Button } from "@/components/ui/button";
import { INVITE_RE, isoDay } from "@/lib/format";
import { cn } from "@/lib/utils";

function LastDays({ byDay }: { byDay: { day: string | null; hh: number; mail: number }[] }) {
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - 13 + i);
    const key = isoDay(d);
    const r = byDay.find((x) => x.day === key);
    return { key, date: d.getDate(), n: (r?.hh ?? 0) + (r?.mail ?? 0) };
  });
  const max = Math.max(1, ...days.map((d) => d.n));
  const today = isoDay();
  return (
    <div className="flex h-[120px] items-end gap-1.5 pt-2.5">
      {days.map((d) => (
        <div key={d.key} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5" title={`${d.key}: ${d.n}`}>
          <small className="text-[11.5px] text-muted-foreground">{d.n || ""}</small>
          <i
            className={cn(
              "block min-h-[3px] w-full max-w-[26px] rounded-md bg-border",
              d.key === today && "border-[1.5px] border-foreground bg-brand",
            )}
            style={{ height: `${(d.n * 80) / max}%` }}
          />
          <small className="text-[11.5px] text-muted-foreground">{d.date}</small>
        </div>
      ))}
    </div>
  );
}

export function StatsPage() {
  const { run, status } = useTasks();
  const { data: d } = $api.useQuery("get", "/api/stats");
  const states = d?.hh_states ?? [];
  const total = states.reduce((a, s) => a + s.n, 0);
  const viewed = states.filter((s) => /^просмотрен|отказ/.test(s.state) || INVITE_RE.test(s.state)).reduce((a, s) => a + s.n, 0);
  const w = status?.week;
  const kpis: [string | number, string][] = [
    [w?.invites ?? 0, "приглашений за неделю 🎉"],
    [w?.rate != null ? `${String(w.rate).replace(".", ",")}%` : "—", "откликов → приглашение"],
    [total ? `${Math.round((viewed * 100) / total)}%` : "—", "просмотрено работодателями"],
    [total, `откликов на hh, писем: ${status?.companies.sent ?? 0}`],
  ];
  const th = "border-b px-3 py-2 text-left text-[12.5px] font-semibold text-muted-foreground";
  const td = "border-b border-muted px-3 py-2";
  return (
    <>
      <PageHeader title="Статистика" description="Что работает, а что стоит поправить" />
      <div className="mb-4 flex flex-wrap gap-2">
        <Button variant="brand" onClick={() => run("hh_sync")}>
          <RefreshCw />
          Обновить ответы с hh
        </Button>
        <span className="flex-1" />
        <Button variant="ghost" asChild>
          <a href="/api/export/vacancies" download>
            <Download />
            Отклики в Excel
          </a>
        </Button>
        <Button variant="ghost" asChild>
          <a href="/api/export/companies" download>
            <Download />
            Письма в Excel
          </a>
        </Button>
      </div>
      <div className="mb-4 grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map(([value, label]) => (
          <div key={label} className="rounded-2xl border bg-card p-[22px]">
            <div className="text-[28px] leading-tight font-extrabold tracking-[-0.03em]">{value}</div>
            <div className="text-[13.5px] font-medium text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Путь откликов" description="Реакция работодателей на hh" className="mb-0">
          <Funnel states={states} />
        </Section>
        <Section title="Последние 14 дней" description="Отклики на hh и письма" className="mb-0">
          <LastDays byDay={d?.by_day ?? []} />
        </Section>
        <Section title="По резюме" description="Какое резюме приносит приглашения" className="mb-0">
          {d?.by_resume.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className={th}>Резюме</th>
                    <th className={th}>Откликов</th>
                    <th className={th}>Приглашений</th>
                    <th className={th}>Не сейчас</th>
                  </tr>
                </thead>
                <tbody>
                  {d.by_resume.map((r) => (
                    <tr key={r.resume}>
                      <td className={td}>{r.resume}</td>
                      <td className={td}>{r.n}</td>
                      <td className={td}>{r.invites ?? 0}</td>
                      <td className={td}>{r.discards ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState emoji="📄" title="Данных пока нет" />
          )}
        </Section>
        <Section title="Почему пропущено" description="Вакансии, где отклик не получился" className="mb-0">
          {d?.skipped.length ? (
            <table className="w-full text-sm">
              <tbody>
                {d.skipped.map((r, i) => (
                  <tr key={i}>
                    <td className={td}>{r.note || "без причины"}</td>
                    <td className={cn(td, "text-right font-bold")}>{r.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState emoji="👌" title="Всё прошло гладко" />
          )}
        </Section>
      </div>
    </>
  );
}
