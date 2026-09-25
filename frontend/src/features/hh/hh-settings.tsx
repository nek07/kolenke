"use client";

import { PenLine, Search, Zap } from "lucide-react";
import Link from "next/link";
import { Controller } from "react-hook-form";

import { AutopilotSwitch } from "@/components/autopilot-switch";
import { Field, Segmented, SwitchField, TextField, ToggleChips } from "@/components/form";
import { Disclosure } from "@/components/blocks";
import { TemplateField } from "@/components/template-field";
import { useTasks } from "@/components/providers/tasks";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useSettings } from "@/hooks/use-settings";
import { useSettingsForm } from "@/hooks/use-settings-form";

const AUTOPILOT_KEYS = ["autopilot_mode", "autopilot_from", "autopilot_to", "chat_auto"] as const;
const FILTER_KEYS = [
  "hh_mode",
  "hh_domain",
  "hh_area",
  "hh_exclude",
  "f_salary_min",
  "f_min_match",
  "f_experience",
  "f_exclude_companies",
  "f_skip_no_salary",
  "f_skip_rejected",
  "f_sort_match",
] as const;
const LETTER_KEYS = ["hh_letter_template"] as const;

const AREAS: [string, string][] = [
  ["", "Как в резюме / все"],
  ["40", "Казахстан"],
  ["160", "Алматы"],
  ["159", "Астана"],
  ["177", "Шымкент"],
  ["1", "Москва"],
  ["113", "Россия"],
];
const EXPERIENCE: ["noExperience" | "between1And3" | "between3And6" | "moreThan6", string][] = [
  ["noExperience", "Без опыта"],
  ["between1And3", "1–3 года"],
  ["between3And6", "3–6 лет"],
  ["moreThan6", "Более 6 лет"],
];

const LimitsLink = () => (
  <Link href="/settings#limits" className="underline">
    Настройки → Лимиты и паузы
  </Link>
);

export function AutopilotSettings() {
  const { data: s } = useSettings();
  const { run } = useTasks();
  const { form, submit, saving } = useSettingsForm(AUTOPILOT_KEYS);
  const mode = form.watch("autopilot_mode");
  const summary = s?.autopilot_on
    ? `— включён, ${s.autopilot_mode === "auto" ? "полностью сам" : "с проверкой"}, каждые ${s.autopilot_interval} мин`
    : "— выключен";
  return (
    <Disclosure icon={<Zap />} title="Автопилот" summary={summary}>
      <div className="mb-4 flex items-center gap-3.5">
        <AutopilotSwitch id="hh-autopilot" />
        <label htmlFor="hh-autopilot">
          <b>Искать свежие вакансии по расписанию</b>
          <div className="text-[13px] text-muted-foreground">
            Раз в N минут: новые вакансии за сутки → фильтры → проверка или отклик → ответы HR-роботам в чатах
          </div>
        </label>
      </div>
      <Field
        label="Режим"
        hint={
          mode === "auto"
            ? "Бот сам откликается на всё, что прошло фильтры. Удобно, когда фильтры уже отлажены"
            : "Бот находит вакансии и присылает уведомление «12 новых подходящих». Вы пролистываете карточки, а бот откликается только на одобренные"
        }
      >
        <Controller
          control={form.control}
          name="autopilot_mode"
          render={({ field }) => (
            <Segmented
              label="Режим автопилота"
              value={field.value}
              onChange={field.onChange}
              options={[
                ["review", "С проверкой"],
                ["auto", "Полностью сам"],
              ]}
            />
          )}
        />
      </Field>
      <div className="mt-4 grid gap-3.5 sm:grid-cols-2">
        <TextField form={form} name="autopilot_from" label="Работать с, час" type="number" min={0} max={23} />
        <TextField form={form} name="autopilot_to" label="до, час" type="number" min={1} max={24} />
      </div>
      <p className="mt-2.5 text-[13px] text-muted-foreground">
        Как часто проверять, сколько откликов в день и паузы между ними — в <LimitsLink />
      </p>
      <div className="mt-4">
        <SwitchField
          control={form.control}
          name="chat_auto"
          title="Отвечать HR-роботам самостоятельно"
          hint="Только если ответ есть в «Базе ответов». Живым рекрутерам бот не пишет без вас"
        />
      </div>
      <div className="mt-[18px] flex flex-wrap gap-2">
        <Button variant="brand" disabled={saving} onClick={() => submit()}>
          Сохранить
        </Button>
        <Button variant="outline" onClick={() => submit(false).then(() => run("autopilot_now"))}>
          Запустить цикл сейчас
        </Button>
      </div>
      <p className="mt-3.5 text-[13px] text-muted-foreground">
        💡 Чтобы Mac не засыпал, пока работает автопилот: Системные настройки → Экран блокировки. Дневной потолок 30–60 откликов бережёт
        аккаунт от капчи. Это защита, а не цель: цель считается за неделю.
      </p>
    </Disclosure>
  );
}

export function SearchFilters() {
  const { form, submit, saving } = useSettingsForm(FILTER_KEYS);
  return (
    <Disclosure icon={<Search />} title="Параметры поиска">
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Что искать">
          <Controller
            control={form.control}
            name="hh_mode"
            render={({ field }) => (
              <Segmented
                label="Что искать"
                value={field.value}
                onChange={field.onChange}
                options={[
                  ["resume", "По резюме"],
                  ["query", "По запросу"],
                ]}
              />
            )}
          />
        </Field>
        <Field label="Сайт">
          <Controller
            control={form.control}
            name="hh_domain"
            render={({ field }) => (
              <Select value={field.value ?? ""} onValueChange={field.onChange}>
                <SelectTrigger className="w-full" aria-label="Сайт">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["hh.kz", "hh.ru", "hh.uz", "rabota.by"].map((d) => (
                    <SelectItem key={d} value={d}>
                      {d}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </Field>
        <Field label="Регион">
          <Controller
            control={form.control}
            name="hh_area"
            render={({ field }) => (
              <Select value={field.value || "all"} onValueChange={(v) => field.onChange(v === "all" ? "" : v)}>
                <SelectTrigger className="w-full" aria-label="Регион">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AREAS.map(([v, label]) => (
                    <SelectItem key={v || "all"} value={v || "all"}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </Field>
        <TextField
          form={form}
          name="hh_exclude"
          className="sm:col-span-2 lg:col-span-3"
          label="Не откликаться, если в названии есть"
          placeholder="например: senior, стажёр, продажи, flutter"
          hint="Через запятую. Такие вакансии сразу попадут в «Пропущены»"
        />
      </div>
      <h4 className="mt-6 mb-3 text-[15px] font-bold">Умные фильтры</h4>
      <div className="grid gap-3.5 sm:grid-cols-2">
        <TextField
          form={form}
          name="f_salary_min"
          type="number"
          min={0}
          label="Зарплата не ниже"
          placeholder="например: 400000"
          hint="Сравнивается верхняя граница вилки из вакансии"
        />
        <TextField
          form={form}
          name="f_min_match"
          type="number"
          min={0}
          max={100}
          label="Минимальное совпадение навыков, %"
          hint="Метка hh в выдаче. 0 — не отсеивать. Вакансии без метки не отсеиваются"
        />
        <Field label="Опыт работы" hint="Ничего не выбрано — любой опыт. Фильтр применяет сам hh при поиске" className="sm:col-span-2">
          <Controller
            control={form.control}
            name="f_experience"
            render={({ field }) => (
              <ToggleChips label="Опыт работы" value={field.value ?? []} onChange={field.onChange} options={EXPERIENCE} />
            )}
          />
        </Field>
        <Field label="Компании-исключения" className="sm:col-span-2">
          <Textarea
            className="min-h-[70px]"
            placeholder="По одной в строке или через запятую. Достаточно части названия: «Kaspi», «Народный банк»"
            {...form.register("f_exclude_companies")}
          />
        </Field>
      </div>
      <div className="mt-4 flex flex-col gap-3">
        <SwitchField control={form.control} name="f_skip_no_salary" title="Пропускать вакансии без зарплаты" />
        <SwitchField
          control={form.control}
          name="f_skip_rejected"
          title="Не откликаться туда, где уже был отказ"
          hint="По названию компании. Отказы подтягиваются кнопкой «Обновить ответы с hh» на «Воронке»"
        />
        <SwitchField
          control={form.control}
          name="f_sort_match"
          title="Сначала лучшие совпадения"
          hint="Порядок в проверке, в списке и в очереди откликов"
        />
      </div>
      <Button variant="brand" className="mt-4" disabled={saving} onClick={() => submit()}>
        Сохранить
      </Button>
    </Disclosure>
  );
}

export function LetterSettings() {
  const { form, submit, saving } = useSettingsForm(LETTER_KEYS);
  return (
    <Disclosure icon={<PenLine />} title="Сопроводительное письмо">
      <Controller
        control={form.control}
        name="hh_letter_template"
        render={({ field }) => <TemplateField value={field.value ?? ""} onChange={field.onChange} />}
      />
      <p className="mt-1.5 text-[13px] text-muted-foreground">
        Нажмите на переменную, чтобы вставить её. {"{company}"} и {"{position}"} берутся из вакансии, {"{name}"} и {"{phone}"} — из настроек
      </p>
      <Button variant="brand" className="mt-3.5" disabled={saving} onClick={() => submit()}>
        Сохранить
      </Button>
    </Disclosure>
  );
}
