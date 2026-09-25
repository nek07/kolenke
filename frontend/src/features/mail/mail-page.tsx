"use client";

import { Eye, Send, Upload } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";

import { $api, type Company, type CompanyStatus, type Schemas } from "@/api/client";
import { fileBody } from "@/api/upload";
import { CompanyStatusBadge } from "@/components/badges";
import { EmptyState, Hint, PageHeader, Section } from "@/components/blocks";
import { Confirm } from "@/components/confirm-button";
import { Chips, Field } from "@/components/form";
import { useTasks } from "@/components/providers/tasks";
import { columnsFor, SelectableTable } from "@/components/selectable-table";
import { TemplateField } from "@/components/template-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRefresh } from "@/hooks/use-refresh";
import { useSettingsForm } from "@/hooks/use-settings-form";
import { plural } from "@/lib/format";

type Filter = CompanyStatus | "all";
const EMPTY: Company[] = [];
const TEMPLATE_KEYS = ["mail_subject_template", "mail_body_template"] as const;

function Step({
  n,
  title,
  description,
  children,
  actions,
}: {
  n: number;
  title: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <Section
      title={
        <>
          <span className="grid size-[26px] place-items-center rounded-lg border-[1.5px] border-foreground bg-brand text-[13px] font-extrabold text-[#141414]">
            {n}
          </span>
          {title}
        </>
      }
      description={description}
      actions={actions}
    >
      {children}
    </Section>
  );
}

function ImportStep() {
  const refresh = useRefresh();
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = $api.useMutation("post", "/api/companies/import");
  const add = $api.useMutation("post", "/api/companies");
  const [company, setCompany] = useState({ name: "", email: "", position: "" });
  return (
    <Step
      n={1}
      title="Список компаний"
      description="CSV или Excel с колонками «компания», «email», «должность». Названия колонок могут быть на русском или английском"
    >
      <div className="flex flex-wrap gap-2">
        <Input ref={fileRef} type="file" accept=".csv,.xlsx,.txt" className="max-w-[320px]" aria-label="Файл со списком" />
        <Button
          variant="brand"
          disabled={upload.isPending}
          onClick={async () => {
            const file = fileRef.current?.files?.[0];
            if (!file) return toast.info("Выберите файл");
            const r = await upload.mutateAsync(fileBody(file));
            if (r.added) toast.success(`Добавлено адресов: ${r.added}`);
            else toast.info("Новых адресов не нашлось");
            if (fileRef.current) fileRef.current.value = "";
            await refresh("/api/companies");
          }}
        >
          <Upload />
          Загрузить
        </Button>
      </div>
      <details className="mt-3.5">
        <summary className="cursor-pointer text-[13px] text-muted-foreground">или добавить одну компанию вручную</summary>
        <form
          className="mt-3 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={async (e) => {
            e.preventDefault();
            await add.mutateAsync({ body: company });
            setCompany({ name: "", email: "", position: "" });
            toast.success("Компания добавлена");
            await refresh("/api/companies");
          }}
        >
          <Field label="Компания">
            <Input placeholder="Halyk Bank" value={company.name} onChange={(e) => setCompany({ ...company, name: e.target.value })} />
          </Field>
          <Field label="Email">
            <Input
              type="email"
              required
              placeholder="hr@company.kz"
              value={company.email}
              onChange={(e) => setCompany({ ...company, email: e.target.value })}
            />
          </Field>
          <Field label="Должность">
            <Input
              placeholder="Backend-разработчик"
              value={company.position}
              onChange={(e) => setCompany({ ...company, position: e.target.value })}
            />
          </Field>
          <Button type="submit" variant="outline" disabled={add.isPending}>
            Добавить
          </Button>
        </form>
      </details>
    </Step>
  );
}

function TemplateStep() {
  const { form, submit, saving } = useSettingsForm(TEMPLATE_KEYS);
  return (
    <Step n={2} title="Текст письма" description="Файл резюме прикладывается автоматически">
      <Field label="Тема">
        <Controller
          control={form.control}
          name="mail_subject_template"
          render={({ field }) => <TemplateField multiline={false} value={field.value ?? ""} onChange={field.onChange} />}
        />
      </Field>
      <Field label="Письмо" className="mt-3.5">
        <Controller
          control={form.control}
          name="mail_body_template"
          render={({ field }) => <TemplateField value={field.value ?? ""} onChange={field.onChange} />}
        />
      </Field>
      <Hint>
        {"{company}"} и {"{position}"} берутся из списка компаний (если должность пустая, то «желаемая должность» из настроек), {"{name}"} и{" "}
        {"{phone}"} из настроек
      </Hint>
      <Hint>
        Сколько писем в день и паузы между ними — в{" "}
        <Link href="/settings#limits" className="underline">
          Настройки → Лимиты и паузы
        </Link>
      </Hint>
      <Button variant="brand" className="mt-3.5" disabled={saving} onClick={() => submit()}>
        Сохранить
      </Button>
    </Step>
  );
}

function Preview({ p }: { p: Schemas["MailPreview"] }) {
  return (
    <pre className="mt-3.5 rounded-xl border bg-surface-2 p-4 font-sans text-sm leading-relaxed whitespace-pre-wrap">
      <b>Кому:</b> {p.to}
      {"\n"}
      <b>Тема:</b> {p.subject}
      {"\n"}
      <b>Вложение:</b> {p.attachments.length ? `📎 ${p.attachments.join(", ")}` : "⚠️ резюме не загружено (Настройки)"}
      {"\n\n"}
      {p.body}
    </pre>
  );
}

export function MailPage() {
  const params = useSearchParams();
  const highlight = Number(params.get("company")) || null;
  const refresh = useRefresh();
  const { run } = useTasks();
  const [filter, setFilter] = useState<Filter>("all");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const { data: rows = EMPTY } = $api.useQuery("get", "/api/companies");
  const preview = $api.useQuery(
    "get",
    "/api/companies/{cid}/preview",
    { params: { path: { cid: previewId ?? 0 } } },
    { enabled: previewId != null },
  );
  const setStatus = $api.useMutation("patch", "/api/companies/status");
  const remove = $api.useMutation("post", "/api/companies/delete");

  useEffect(() => {
    if (!highlight || !rows.length) return;
    document.getElementById(`company-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight, rows.length]);

  const count = (f: Filter) => (f === "all" ? rows.length : rows.filter((c) => c.status === f).length);
  const shown = filter === "all" ? rows : rows.filter((c) => c.status === filter);
  const columns = useMemo(() => {
    const col = columnsFor<Company>();
    return [
      col.accessor("name", {
        header: "Компания",
        cell: ({ row: { original: c } }) => (
          <div id={`company-${c.id}`} className={c.id === highlight ? "rounded bg-brand-soft" : undefined}>
            <b className="font-medium">{c.name || "—"}</b>
            <div className="text-[13px] text-muted-foreground">{c.email}</div>
          </div>
        ),
      }),
      col.accessor("position", { header: "Должность", meta: { className: "hidden md:table-cell" } }),
      col.accessor("status", {
        header: "Статус",
        cell: ({ row: { original: c } }) => (
          <>
            <CompanyStatusBadge status={c.status} />
            {c.note && <div className="text-[13px] text-muted-foreground">{c.note}</div>}
          </>
        ),
      }),
      col.display({
        id: "preview",
        header: "",
        meta: { className: "text-right" },
        cell: ({ row: { original: c } }) => (
          <Button size="sm" variant="ghost" onClick={() => setPreviewId(c.id)}>
            <Eye />
            Письмо
          </Button>
        ),
      }),
    ];
  }, [highlight]);

  async function move(ids: number[], status: CompanyStatus, clear: () => void) {
    await setStatus.mutateAsync({ body: { ids, status } });
    toast.success(`Готово: ${ids.length}`);
    clear();
    await refresh("/api/companies", "/api/status");
  }

  return (
    <>
      <PageHeader
        title="Письма компаниям"
        description="Разошлите резюме в HR-отделы банков и компаний с вашего Gmail, аккуратно и без спама"
      />
      <ImportStep />
      <TemplateStep />
      <Step
        n={3}
        title="Отправка"
        actions={
          <Button variant="brand" onClick={() => run("mail_send")}>
            <Send />
            Отправить очередь
          </Button>
        }
      >
        <div className="mb-3.5">
          <Chips
            label="Фильтр по статусу"
            value={filter}
            onChange={setFilter}
            options={(
              [
                ["all", "Все"],
                ["new", "Новые"],
                ["queued", "В очереди"],
                ["sent", "Отправлено"],
                ["error", "Ошибки"],
              ] as [Filter, string][]
            )
              .filter(([f]) => f === "all" || count(f))
              .map(([f, label]) => ({ value: f, label, count: count(f) }))}
          />
        </div>
        <SelectableTable
          label="Компании"
          data={shown}
          columns={columns}
          resetKey={filter}
          actions={(ids, clear) => (
            <>
              <Button size="sm" variant="outline" onClick={() => move(ids, "queued", clear)}>
                В очередь
              </Button>
              <Button size="sm" variant="outline" onClick={() => move(ids, "new", clear)}>
                Убрать из очереди
              </Button>
              <Confirm
                title={`Удалить ${ids.length} ${plural(ids.length, "компанию", "компании", "компаний")}?`}
                description="Их можно будет загрузить снова"
                confirm="Удалить"
                onConfirm={async () => {
                  await remove.mutateAsync({ body: { ids } });
                  clear();
                  await refresh("/api/companies", "/api/status");
                }}
              >
                <Button size="sm" variant="outline">
                  Удалить
                </Button>
              </Confirm>
            </>
          )}
          empty={
            <EmptyState emoji="📬" title="Список пока пуст">
              Загрузите CSV или Excel с адресами HR-отделов
            </EmptyState>
          }
        />
        {preview.data && previewId != null && <Preview p={preview.data} />}
      </Step>
    </>
  );
}
