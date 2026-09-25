"use client";

import { Globe, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";

import { $api, type Vacancy, type VacancyStatus } from "@/api/client";
import { VacancyStatusBadge } from "@/components/badges";
import { Disclosure, EmptyState, PageHeader, Section } from "@/components/blocks";
import { Confirm } from "@/components/confirm-button";
import { Chips, Field, SwitchField, TextField, ToggleChips } from "@/components/form";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import { columnsFor, SelectableTable } from "@/components/selectable-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Contacts, Place } from "@/components/vacancy-panel";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";
import { useSettings } from "@/hooks/use-settings";
import { useSettingsForm } from "@/hooks/use-settings-form";

const BOARDS: [string, string][] = [
  ["habr", "Хабр Карьера"],
  ["enbek", "Enbek"],
];
const SOURCE_NAMES: Record<string, string> = {
  habr: "Хабр Карьера",
  enbek: "Enbek",
  linkedin: "LinkedIn",
  superjob: "SuperJob",
  other: "Вручную",
};
const MONITOR_KEYS = ["other_query", "other_sites", "other_countries", "other_monitor"] as const;
const EMPTY: Vacancy[] = [];

type Source = "all" | "habr" | "enbek" | "manual";
type StatusFilter = "new" | "applied" | "skipped" | "all";

const isManual = (v: Vacancy) => v.source !== "habr" && v.source !== "enbek";
const inSource = (v: Vacancy, s: Source) => s === "all" || (s === "manual" ? isManual(v) : v.source === s);
const hasEmail = (v: Vacancy) => !!v.contacts?.emails.length;

function Monitoring() {
  const { run } = useTasks();
  const { data: s } = useSettings();
  const { form, submit, saving } = useSettingsForm(MONITOR_KEYS);
  const fallback = s?.hh_query || s?.desired_position;
  return (
    <Section
      title="Мониторинг"
      actions={
        <SwitchField
          control={form.control}
          name="other_monitor"
          title={<span className="text-[13px] font-normal text-muted-foreground">Проверять вместе с автопилотом</span>}
          onToggle={() => void submit(false)}
        />
      }
    >
      <div className="grid gap-3.5 sm:grid-cols-3">
        <TextField
          form={form}
          name="other_query"
          className="sm:col-span-2"
          label="Что ищем"
          placeholder={fallback ? `пусто — ищем «${fallback}»` : "например: backend разработчик"}
        />
        <Field label="Площадки">
          <Controller
            control={form.control}
            name="other_sites"
            render={({ field }) => <ToggleChips label="Площадки" value={field.value ?? []} onChange={field.onChange} options={BOARDS} />}
          />
        </Field>
        <TextField
          form={form}
          name="other_countries"
          className="sm:col-span-3"
          label="Страны и города"
          placeholder="например: Астана, Алматы, удалённо — пусто: любые"
          hint="Через запятую: страна («Казахстан») или город («Астана»). «удалённо» пропускает вакансии, где можно работать из дома. Слова-исключения, зарплата и компании-исключения берутся из фильтров HeadHunter"
        />
      </div>
      <div className="mt-3.5 flex flex-wrap items-center gap-2">
        <Button variant="brand" onClick={() => submit(false).then(() => run("other_search"))}>
          <Search />
          Найти сейчас
        </Button>
        <Button variant="outline" disabled={saving} onClick={() => submit()}>
          Сохранить
        </Button>
        <span className="text-[13px] text-muted-foreground">
          Бот открывает только публичные страницы и ничего не отправляет от вашего имени. Сколько страниц смотреть — в{" "}
          <Link href="/settings#limits" className="underline">
            лимитах
          </Link>
        </span>
      </div>
    </Section>
  );
}

function ManualTracker() {
  const refresh = useRefresh();
  const { data: s } = useSettings();
  const add = $api.useMutation("post", "/api/vacancies");
  const [q, setQ] = useState<string | null>(null);
  const [item, setItem] = useState({ source: "other", url: "", title: "", company: "" });
  const query = encodeURIComponent((q ?? s?.hh_query ?? s?.desired_position ?? "").trim());
  const sites: [string, string, string, string][] = [
    ["Habr Career", "IT-вакансии", "#6F8FAF", `https://career.habr.com/vacancies?q=${query}&type=all`],
    ["LinkedIn", "Казахстан", "#2F6FB5", `https://www.linkedin.com/jobs/search/?keywords=${query}&location=Kazakhstan`],
    ["Enbek.kz", "Портал занятости РК", "#2E8B57", `https://www.enbek.kz/ru/search/vacancy?prof=${query}`],
    ["SuperJob", "Россия", "#1DAF5B", `https://www.superjob.ru/vacancy/search/?keywords=${query}`],
  ];
  return (
    <Disclosure icon={<Globe />} title="Ручной поиск и трекер" summary="— LinkedIn, SuperJob, сайты компаний">
      <Input
        className="mb-3.5"
        placeholder="Что ищем?"
        aria-label="Что ищем"
        value={q ?? s?.hh_query ?? s?.desired_position ?? ""}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {sites.map(([name, sub, color, url]) => (
          <a
            key={name}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-3 rounded-2xl border-[1.5px] bg-card p-3.5 font-semibold hover:border-foreground"
          >
            <span className="grid size-[38px] place-items-center rounded-[10px] font-extrabold text-white" style={{ background: color }}>
              {name[0]}
            </span>
            <span>
              {name}
              <small className="block text-[12.5px] font-medium text-muted-foreground">{sub}</small>
            </span>
          </a>
        ))}
      </div>
      <h4 className="mt-6 mb-2.5 text-[15px] font-bold">Добавить вакансию вручную</h4>
      <form
        className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={async (e) => {
          e.preventDefault();
          await add.mutateAsync({ body: item });
          setItem({ ...item, url: "", title: "", company: "" });
          toast.success("Добавлено в трекер");
          await refresh(...VACANCY_VIEWS);
        }}
      >
        <Field label="Сайт">
          <Select value={item.source} onValueChange={(v) => setItem({ ...item, source: v })}>
            <SelectTrigger className="w-full" aria-label="Сайт">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="other">Сайт компании / другое</SelectItem>
              <SelectItem value="linkedin">LinkedIn</SelectItem>
              <SelectItem value="superjob">SuperJob</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Ссылка" className="lg:col-span-2">
          <Input
            type="url"
            required
            placeholder="https://..."
            value={item.url}
            onChange={(e) => setItem({ ...item, url: e.target.value })}
          />
        </Field>
        <Field label="Должность">
          <Input value={item.title} onChange={(e) => setItem({ ...item, title: e.target.value })} />
        </Field>
        <Field label="Компания">
          <Input value={item.company} onChange={(e) => setItem({ ...item, company: e.target.value })} />
        </Field>
        <Button type="submit" variant="outline" disabled={add.isPending}>
          <Plus />
          Добавить
        </Button>
      </form>
    </Disclosure>
  );
}

export function SitesPage() {
  const refresh = useRefresh();
  const { openVacancy } = useUI();
  const [source, setSource] = useState<Source>("all");
  const [status, setStatus] = useState<StatusFilter>("new");
  const [onlyEmail, setOnlyEmail] = useState(false);
  const { data: all = EMPTY } = $api.useQuery("get", "/api/vacancies");
  const setVacancyStatus = $api.useMutation("patch", "/api/vacancies/status");
  const remove = $api.useMutation("post", "/api/vacancies/delete");
  const toCompanies = $api.useMutation("post", "/api/vacancies/to-companies");

  const rows = useMemo(() => all.filter((v) => v.source !== "hh"), [all]);
  const bySource = useMemo(() => rows.filter((v) => inSource(v, source)), [rows, source]);
  const shown = useMemo(
    () => bySource.filter((v) => (status === "all" || v.status === status) && (!onlyEmail || hasEmail(v))),
    [bySource, status, onlyEmail],
  );

  const columns = useMemo(() => {
    const col = columnsFor<Vacancy>();
    return [
      col.accessor("title", {
        header: "Вакансия",
        meta: { className: "min-w-[240px]" },
        cell: ({ row: { original: v } }) => (
          <>
            <a href={v.url} target="_blank" rel="noreferrer" className="font-semibold hover:underline">
              {v.title}
            </a>
            <div className="text-[13px] text-muted-foreground">
              {[v.company, SOURCE_NAMES[v.source] ?? v.source, v.experience].filter(Boolean).join(" · ")}
            </div>
            {v.summary && <div className="mt-1 line-clamp-2 max-w-[520px] text-[13px] text-ink-2">{v.summary}</div>}
            {v.status === "skipped" && v.note && <div className="text-[13px] text-muted-foreground">{v.note}</div>}
          </>
        ),
      }),
      col.accessor("salary_text", {
        header: "Зарплата",
        meta: { className: "min-w-[110px] max-w-[150px] tabular-nums" },
        cell: (c) => c.getValue() ?? <span className="text-[13px] text-muted-foreground">не указана</span>,
      }),
      col.display({
        id: "place",
        header: "Где",
        meta: { className: "hidden md:table-cell max-w-[170px]" },
        cell: ({ row }) => <Place v={row.original} />,
      }),
      col.display({
        id: "contacts",
        header: "Контакты",
        cell: ({ row }) => <Contacts contacts={row.original.contacts} />,
      }),
      col.accessor("status", {
        header: "Статус",
        meta: { className: "hidden md:table-cell" },
        cell: (c) => <VacancyStatusBadge status={c.getValue()} />,
      }),
    ];
  }, []);

  async function move(ids: number[], to: VacancyStatus, clear: () => void) {
    await setVacancyStatus.mutateAsync({ body: { ids, status: to } });
    toast.success(to === "applied" ? "Отмечено: откликнулись" : "Готово");
    clear();
    await refresh(...VACANCY_VIEWS);
  }

  return (
    <>
      <PageHeader
        title="Другие сайты"
        description="Хабр Карьера и Enbek: бот находит свежие вакансии, достаёт зарплату, город и контакты работодателя. Откликаетесь вы сами или пишете компании на почту"
      />
      <Monitoring />
      <Section
        title="Найденные вакансии"
        actions={
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px] text-muted-foreground">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              checked={onlyEmail}
              onChange={(e) => setOnlyEmail(e.target.checked)}
            />
            только с почтой
          </label>
        }
      >
        <div className="mb-2">
          <Chips
            label="Площадка"
            value={source}
            onChange={setSource}
            options={(
              [
                ["all", "Все площадки"],
                ["habr", "Хабр Карьера"],
                ["enbek", "Enbek"],
                ["manual", "Добавлены вручную"],
              ] as [Source, string][]
            )
              .map(([s, label]) => ({ value: s, label, count: rows.filter((v) => inSource(v, s)).length }))
              .filter((o) => o.value === "all" || o.count || o.value === source)}
          />
        </div>
        <div className="mb-3.5">
          <Chips
            label="Статус"
            value={status}
            onChange={setStatus}
            options={(
              [
                ["new", "Новые"],
                ["applied", "Откликнулся"],
                ["skipped", "Пропущены"],
                ["all", "Все"],
              ] as [StatusFilter, string][]
            ).map(([s, label]) => ({
              value: s,
              label,
              count: s === "all" ? bySource.length : bySource.filter((v) => v.status === s).length,
            }))}
          />
        </div>
        <SelectableTable
          label="Вакансии с других сайтов"
          data={shown}
          columns={columns}
          maxHeight={640}
          resetKey={`${source}-${status}-${onlyEmail}`}
          onRowClick={(v) => openVacancy(v.id)}
          actions={(ids, clear) => (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  const r = await toCompanies.mutateAsync({ body: { ids } });
                  if (r.added)
                    toast.success(`В «Письма компаниям» добавлено адресов: ${r.added}${r.no_email ? `, без почты: ${r.no_email}` : ""}`);
                  else toast.info(r.no_email ? "У выбранных вакансий нет почты" : "Эти адреса уже есть в списке");
                  await refresh("/api/companies");
                }}
              >
                В письма компаниям
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "applied", clear)}>
                Откликнулся ✓
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "skipped", clear)}>
                Пропустить
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "new", clear)}>
                Вернуть
              </Button>
              <Confirm
                title="Удалить из трекера?"
                confirm="Удалить"
                onConfirm={async () => {
                  await remove.mutateAsync({ body: { ids } });
                  clear();
                  await refresh(...VACANCY_VIEWS);
                }}
              >
                <Button size="sm" variant="outline">
                  Удалить
                </Button>
              </Confirm>
            </>
          )}
          empty={
            <EmptyState emoji="🔭" title={rows.length ? "Здесь пусто" : "Вакансий пока нет"}>
              {rows.length ? "Попробуйте другой фильтр" : "Нажмите «Найти сейчас» — бот посмотрит Хабр Карьеру и Enbek"}
            </EmptyState>
          }
        />
      </Section>
      <ManualTracker />
    </>
  );
}
