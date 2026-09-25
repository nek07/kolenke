"use client";

import { Mail, Plus, RefreshCw, Search, Send, Sparkles, User } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { $api, type Vacancy, type VacancyStatus } from "@/api/client";
import { HhStateBadge, MatchBadge, VacancyStatusBadge } from "@/components/badges";
import { Chips, Field } from "@/components/form";
import { Banner, EmptyState, PageHeader, Section } from "@/components/blocks";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import { columnsFor, SelectableTable } from "@/components/selectable-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useQueryParam } from "@/hooks/use-query-param";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";
import { useSaveSettings, useSettings } from "@/hooks/use-settings";
import { plural } from "@/lib/format";

import { AutopilotSettings, LetterSettings, SearchFilters } from "./hh-settings";

type Filter = VacancyStatus | "all";
const EMPTY: Vacancy[] = [];

const FILTERS: [Filter, string][] = [
  ["new", "Новые"],
  ["queued", "В очереди"],
  ["applied", "Отправлены"],
  ["attention", "Нужен ваш ответ"],
  ["skipped", "Пропущены"],
  ["error", "Не получилось"],
  ["all", "Все"],
];

const EMPTY_MESSAGES: Partial<Record<Filter, [string, string, string]>> = {
  new: ["🔍", "Новых вакансий нет", "Нажмите «Найти вакансии» или включите автопилот"],
  queued: ["📭", "Очередь пуста", "Отметьте вакансии и добавьте их в очередь"],
  applied: ["🌱", "Откликов пока нет", "Первый отклик — самый важный шаг"],
  attention: ["🎉", "Всё отвечено", "Анкет без ответа нет"],
};

const col = columnsFor<Vacancy>();
const COLUMNS = [
  col.accessor("title", {
    header: "Вакансия",
    cell: ({ row: { original: v } }) => (
      <>
        <a href={v.url} target="_blank" rel="noreferrer" className="font-semibold hover:underline">
          {v.title}
        </a>
        <div className="text-[13px] text-muted-foreground">{[v.company, v.salary_text, v.note].filter(Boolean).join(" · ")}</div>
      </>
    ),
  }),
  col.accessor("skill_match", {
    header: "Навыки",
    meta: { className: "hidden md:table-cell" },
    cell: (c) => <MatchBadge value={c.getValue()} />,
  }),
  col.accessor("status", { header: "Статус", cell: (c) => <VacancyStatusBadge status={c.getValue()} /> }),
  col.display({
    id: "resume",
    header: "Резюме и письмо",
    meta: { className: "hidden md:table-cell text-[13px] text-muted-foreground" },
    cell: ({ row: { original: v } }) => (
      <>
        {v.resume}
        {v.status === "applied" && v.letter_sent != null && <div>{v.letter_sent ? "письмо ✓" : "без письма"}</div>}
      </>
    ),
  }),
  col.accessor("hh_state", { header: "Ответ", cell: (c) => <HhStateBadge state={c.getValue()} /> }),
];

function SearchAndApply({ queued }: { queued: number }) {
  const { data: s } = useSettings();
  const { save } = useSaveSettings();
  const { run } = useTasks();
  const [query, setQuery] = useState<string | null>(null);
  if (!s) return null;
  const byResume = s.hh_mode === "resume";
  const saveQuery = () => (query !== null && query !== s.hh_query ? save({ hh_query: query }, false) : Promise.resolve());
  return (
    <Section>
      <div className="grid items-end gap-3.5 md:grid-cols-[1fr_auto]">
        {byResume ? (
          <Field label="Резюме, с которого откликаемся">
            <div className="flex gap-2">
              <Select value={s.hh_resume_hash} onValueChange={(v) => save({ hh_resume_hash: v }, "Резюме выбрано")}>
                <SelectTrigger className="w-full" aria-label="Резюме">
                  <SelectValue placeholder="Сначала войдите в hh" />
                </SelectTrigger>
                <SelectContent>
                  {s.hh_resumes.map((r) => (
                    <SelectItem key={r.hash} value={r.hash}>
                      {r.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="icon"
                title="Обновить список резюме"
                aria-label="Обновить список резюме"
                onClick={() => run("hh_resumes")}
              >
                <RefreshCw />
              </Button>
            </div>
          </Field>
        ) : (
          <Field label="Поисковый запрос">
            <Input
              placeholder="например: backend разработчик"
              value={query ?? s.hh_query}
              onChange={(e) => setQuery(e.target.value)}
              onBlur={saveQuery}
            />
          </Field>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => saveQuery().then(() => run("hh_search"))}>
            <Search />
            Найти вакансии
          </Button>
          <Button variant="brand" onClick={() => run("hh_apply")}>
            <Send />
            Откликнуться {queued ? `(${queued})` : ""}
          </Button>
        </div>
      </div>
    </Section>
  );
}

export function HhPage() {
  const [filter, setFilter] = useQueryParam<Filter>("status", "new");
  const { data: s } = useSettings();
  const { status } = useTasks();
  const { run } = useTasks();
  const { openVacancy, setReviewOpen } = useUI();
  const refresh = useRefresh();
  const { data: rows = EMPTY } = $api.useQuery("get", "/api/vacancies", { params: { query: { source: "hh" } } });
  const setStatus = $api.useMutation("patch", "/api/vacancies/status");
  const queueNew = $api.useMutation("post", "/api/vacancies/queue-new");

  const count = (f: Filter) => (f === "all" ? rows.length : rows.filter((v) => v.status === f).length);
  const shown = useMemo(() => {
    const list = filter === "all" ? rows : rows.filter((v) => v.status === filter);
    if (!s?.f_sort_match || (filter !== "new" && filter !== "queued")) return list;
    return [...list].sort((a, b) => (b.skill_match ?? -1) - (a.skill_match ?? -1));
  }, [rows, filter, s?.f_sort_match]);
  const fresh = count("new");
  const empty = EMPTY_MESSAGES[filter] ?? ["✨", "Здесь пусто", ""];

  async function move(ids: number[], to: VacancyStatus, clear: () => void) {
    await setStatus.mutateAsync({ body: { ids, status: to } });
    toast.success(`Готово: ${ids.length}`);
    clear();
    await refresh(...VACANCY_VIEWS);
  }

  return (
    <>
      <PageHeader title="HeadHunter" description="Отклики на вакансии, подходящие вашему резюме, вручную или на автопилоте" />
      {s && !s.hh_resumes.length && (
        <Banner
          icon={<User />}
          title="Подключите аккаунт hh"
          action={
            <Button variant="brand" onClick={() => run("hh_login")}>
              Войти в hh
            </Button>
          }
        >
          Войдите один раз в открывшемся окне, и бот увидит ваши резюме
        </Banner>
      )}
      {fresh > 0 && (
        <Banner
          icon={<Sparkles />}
          title={`${fresh} ${plural(fresh, "новая подходящая вакансия", "новые подходящие вакансии", "новых подходящих вакансий")}`}
          action={
            <Button variant="brand" onClick={() => setReviewOpen(true)}>
              Проверить
            </Button>
          }
        >
          Пролистайте карточки: «Откликнуться» или «Пропустить». Лучшие совпадения первыми
        </Banner>
      )}
      {!!status?.no_letter && (
        <Banner
          icon={<Mail />}
          title={`${status.no_letter} ${plural(status.no_letter, "отклик ушёл", "отклика ушли", "откликов ушли")} без сопроводительного письма`}
          action={
            <Button variant="brand" onClick={() => run("hh_letters")}>
              Дослать письма
            </Button>
          }
        >
          Бот отправит ваше сопроводительное письмо сообщением в чат каждой такой вакансии
        </Banner>
      )}
      <SearchAndApply queued={count("queued")} />
      <AutopilotSettings />
      <SearchFilters />
      <LetterSettings />
      <Section
        title="Вакансии"
        actions={
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              const r = await queueNew.mutateAsync({ body: { source: "hh" } });
              if (r.count) toast.success(`В очереди: ${r.count}. Нажмите «Откликнуться»`);
              else toast.info("Новых вакансий нет");
              await refresh(...VACANCY_VIEWS);
            }}
          >
            <Plus />
            Все новые в очередь
          </Button>
        }
      >
        <div className="mb-3.5">
          <Chips
            label="Фильтр по статусу"
            value={filter}
            onChange={setFilter}
            options={FILTERS.filter(([f]) => f === "all" || f === "new" || f === filter || count(f)).map(([f, label]) => ({
              value: f,
              label,
              count: count(f),
            }))}
          />
        </div>
        <p className="mb-3 text-[13px] text-muted-foreground">Нажмите на строку, чтобы открыть историю вакансии</p>
        <SelectableTable
          label="Вакансии hh"
          data={shown}
          columns={COLUMNS}
          resetKey={filter}
          onRowClick={(v) => openVacancy(v.id)}
          actions={(ids, clear) => (
            <>
              <Button size="sm" variant="outline" onClick={() => move(ids, "queued", clear)}>
                В очередь
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "skipped", clear)}>
                Пропустить
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "new", clear)}>
                Вернуть в новые
              </Button>
            </>
          )}
          empty={
            <EmptyState emoji={empty[0]} title={empty[1]}>
              {empty[2]}
            </EmptyState>
          }
        />
      </Section>
    </>
  );
}
