"use client";

import { Briefcase, FileText, Mail, SlidersHorizontal, Upload, User } from "lucide-react";
import { useRef } from "react";
import { toast } from "sonner";

import { $api } from "@/api/client";
import { fileBody } from "@/api/upload";
import { PageHeader, Section } from "@/components/blocks";
import { Confirm } from "@/components/confirm-button";
import { TextField } from "@/components/form";
import { useTasks } from "@/components/providers/tasks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRefresh } from "@/hooks/use-refresh";
import { useSaveSettings, useSettings } from "@/hooks/use-settings";
import { useSettingsForm } from "@/hooks/use-settings-form";

const PROFILE_KEYS = ["full_name", "phone", "desired_position"] as const;
const MAIL_KEYS = ["smtp_user", "smtp_password", "smtp_host", "smtp_port"] as const;

/** Recommended limits: «Вернуть рекомендуемые» restores exactly these. */
const LIMIT_DEFAULTS = {
  hh_daily_limit: 50,
  hh_weekly_goal: 150,
  hh_pause_min: 4,
  hh_pause_max: 9,
  hh_pages: 3,
  autopilot_interval: 30,
  chat_max: 20,
  chat_robot_steps: 10,
  mail_daily_limit: 80,
  mail_delay_min: 40,
  mail_delay_max: 90,
  other_pages: 2,
  other_max_details: 40,
  followup_days: 5,
};
const LIMIT_KEYS = Object.keys(LIMIT_DEFAULTS) as (keyof typeof LIMIT_DEFAULTS)[];

const icon = (Icon: typeof User, text: string) => (
  <>
    <Icon className="size-[18px]" />
    {text}
  </>
);

function Profile() {
  const { form, submit, saving } = useSettingsForm(PROFILE_KEYS);
  return (
    <Section title={icon(User, "О вас")} description="Подставляется в письма и сопроводительные">
      <div className="grid gap-3.5 sm:grid-cols-3">
        <TextField form={form} name="full_name" label="Имя и фамилия" placeholder="Имя Фамилия" />
        <TextField form={form} name="phone" label="Телефон" placeholder="+7 7xx xxx xx xx" />
        <TextField form={form} name="desired_position" label="Желаемая должность" placeholder="Backend-разработчик" />
      </div>
      <Button variant="brand" className="mt-4" disabled={saving} onClick={() => submit()}>
        Сохранить
      </Button>
    </Section>
  );
}

function Limits() {
  const { form, submit, saving } = useSettingsForm(LIMIT_KEYS);
  const { save } = useSaveSettings();
  const num = { type: "number" as const, min: 0 };
  const group = (title: string) => (
    <h4 className="mt-[18px] mb-2.5 text-[13px] font-bold tracking-[0.04em] text-muted-foreground uppercase first:mt-1">{title}</h4>
  );
  const grid = "grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3";
  return (
    <Section
      id="limits"
      title={icon(SlidersHorizontal, "Лимиты и паузы")}
      description="Всё, сколько и как часто делает бот, настраиваете вы. Большие значения ускоряют поиск, но повышают риск капчи и ограничений на hh"
    >
      {group("HeadHunter")}
      <div className={grid}>
        <TextField form={form} name="hh_daily_limit" label="Не больше откликов в день" hint="Безопасно: 30–60" {...num} min={1} />
        <TextField form={form} name="hh_weekly_goal" label="Цель откликов на неделю" {...num} min={1} />
        <TextField form={form} name="hh_pause_min" label="Пауза между откликами, от (сек)" {...num} />
        <TextField form={form} name="hh_pause_max" label="до (сек)" hint="Случайная пауза выглядит естественнее" {...num} />
        <TextField form={form} name="hh_pages" label="Страниц поиска (по 50 вакансий)" {...num} min={1} max={20} />
      </div>
      {group("Автопилот и чаты")}
      <div className={grid}>
        <TextField
          form={form}
          name="autopilot_interval"
          label="Проверять каждые, мин"
          hint="Реже 10 минут почти не даёт выигрыша"
          {...num}
          min={1}
        />
        <TextField form={form} name="chat_max" label="Чатов за одну проверку" {...num} min={1} />
        <TextField form={form} name="chat_robot_steps" label="Вопросов HR-робота подряд" {...num} min={1} />
      </div>
      {group("Письма компаниям")}
      <div className={grid}>
        <TextField form={form} name="mail_daily_limit" label="Писем в день" hint="Для Gmail безопасно 80–100" {...num} min={1} />
        <TextField form={form} name="mail_delay_min" label="Пауза между письмами, от (сек)" {...num} />
        <TextField form={form} name="mail_delay_max" label="до (сек)" {...num} />
      </div>
      {group("Хабр Карьера и Enbek")}
      <div className={grid}>
        <TextField form={form} name="other_pages" label="Страниц поиска на каждой" {...num} min={1} max={10} />
        <TextField
          form={form}
          name="other_max_details"
          label="Открывать новых вакансий за проверку"
          hint="Остальные откроются при следующей. 0 — только списки, без контактов"
          {...num}
        />
      </div>
      {group("Воронка")}
      <div className={grid}>
        <TextField form={form} name="followup_days" label="Предлагать «напомнить о себе» через, дней" {...num} min={1} />
      </div>
      <div className="mt-4 flex gap-2">
        <Button variant="brand" disabled={saving} onClick={() => submit()}>
          Сохранить
        </Button>
        <Confirm
          title="Вернуть рекомендуемые лимиты?"
          description="Ваши значения в этом блоке заменятся на безопасные по умолчанию"
          confirm="Вернуть"
          onConfirm={() => save(LIMIT_DEFAULTS)}
        >
          <Button variant="ghost">Вернуть рекомендуемые</Button>
        </Confirm>
      </div>
    </Section>
  );
}

function HhAccount() {
  const { data: s } = useSettings();
  const { run } = useTasks();
  const resumes = s?.hh_resumes ?? [];
  return (
    <Section
      title={icon(Briefcase, "Аккаунт hh")}
      description={
        resumes.length
          ? `Подключено ✓ Резюме: ${resumes.map((r) => r.title).join(", ")}`
          : "Бот работает от вашего имени в отдельном окне браузера. Вход пока не выполнен"
      }
    >
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => run("hh_login")}>
          Войти в hh
        </Button>
        <Button variant="outline" onClick={() => run("hh_check")}>
          Проверить вход
        </Button>
      </div>
    </Section>
  );
}

function ResumeFile() {
  const { data: s } = useSettings();
  const refresh = useRefresh();
  const ref = useRef<HTMLInputElement>(null);
  const upload = $api.useMutation("post", "/api/settings/resume");
  return (
    <Section
      title={icon(FileText, "Файл резюме для писем")}
      description={s?.resume_name ? `Загружен: ${s.resume_name}` : "Файл не загружен. Нужен, чтобы прикладывать резюме к письмам"}
    >
      <div className="flex flex-wrap gap-2">
        <Input ref={ref} type="file" accept=".pdf,.doc,.docx" className="max-w-[320px]" aria-label="Файл резюме" />
        <Button
          variant="outline"
          disabled={upload.isPending}
          onClick={async () => {
            const file = ref.current?.files?.[0];
            if (!file) return toast.info("Выберите файл резюме");
            await upload.mutateAsync(fileBody(file));
            toast.success("Резюме загружено");
            if (ref.current) ref.current.value = "";
            await refresh("/api/settings");
          }}
        >
          <Upload />
          Загрузить
        </Button>
      </div>
    </Section>
  );
}

function Gmail() {
  const { data: s } = useSettings();
  const { form, submit, saving } = useSettingsForm(MAIL_KEYS);
  const test = $api.useMutation("post", "/api/mail/test");
  return (
    <Section title={icon(Mail, "Gmail для отправки")} description="Нужен «пароль приложения», обычный пароль Gmail не подойдёт">
      <div className="grid gap-3.5 sm:grid-cols-2">
        <TextField form={form} name="smtp_user" type="email" label="Gmail-адрес" placeholder="you@gmail.com" />
        <TextField
          form={form}
          name="smtp_password"
          type="password"
          label="Пароль приложения"
          autoComplete="new-password"
          placeholder={s?.has_password ? "•••••• сохранён" : "xxxx xxxx xxxx xxxx"}
        />
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-[13px] text-muted-foreground">Как получить пароль приложения и другие параметры</summary>
        <p className="mt-1.5 text-[13px] text-muted-foreground">
          myaccount.google.com → Безопасность → включите двухэтапную аутентификацию → «Пароли приложений» → создайте пароль (16 символов) и
          вставьте сюда.
        </p>
        <div className="mt-2.5 grid gap-3.5 sm:grid-cols-2">
          <TextField form={form} name="smtp_host" label="SMTP-сервер" />
          <TextField form={form} name="smtp_port" type="number" label="Порт" />
        </div>
      </details>
      <div className="mt-4 flex gap-2">
        <Button variant="brand" disabled={saving} onClick={() => submit()}>
          Сохранить
        </Button>
        <Button
          variant="outline"
          disabled={test.isPending}
          onClick={async () => {
            await submit(false);
            const r = await test.mutateAsync({});
            if (r.ok) toast.success(r.message);
            else toast.error(r.message);
          }}
        >
          Проверить подключение
        </Button>
      </div>
    </Section>
  );
}

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Настройки" description="Всё хранится только на вашем компьютере" />
      <Profile />
      <Limits />
      <HhAccount />
      <ResumeFile />
      <Gmail />
    </>
  );
}
