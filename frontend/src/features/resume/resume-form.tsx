"use client";

import { FileSearch, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { $api, type Grade, type Schemas } from "@/api/client";
import { Hint, Section } from "@/components/blocks";
import { Field, Segmented } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useSettings } from "@/hooks/use-settings";

type Source = "file" | "text" | "saved";
type Body = Schemas["Body_create_review"];

/** Multipart body for POST /api/resume-reviews: only the fields that are set, the file as a Blob. */
const reviewBody = (body: Body, file: File | null) => ({
  body,
  bodySerializer: (b: Body) => {
    const fd = new FormData();
    for (const [k, v] of Object.entries(b)) if (v !== undefined && v !== null && k !== "file") fd.append(k, String(v));
    if (file) fd.append("file", file);
    return fd;
  },
});

function SwitchRow({
  id,
  checked,
  onChange,
  disabled,
  title,
  hint,
}: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  title: React.ReactNode;
  hint: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3.5">
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onChange} className="mt-0.5 data-[state=checked]:bg-success" />
      <label htmlFor={id} className="cursor-pointer">
        <b className="font-semibold">{title}</b>
        <div className="text-[13px] text-muted-foreground">{hint}</div>
      </label>
    </div>
  );
}

export function ResumeForm({ onStarted }: { onStarted: (id: number) => void }) {
  const { data: s } = useSettings();
  const { data: options } = $api.useQuery("get", "/api/resume-reviews/options");
  const create = $api.useMutation("post", "/api/resume-reviews");
  const fileRef = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState<Source>("file");
  const [text, setText] = useState("");
  // untouched (null) = the desired position from the settings, the natural first guess for the role
  const [roleInput, setRole] = useState<string | null>(null);
  const role = roleInput ?? s?.desired_position ?? "";
  const [grade, setGrade] = useState<Grade>("middle");
  const [market, setMarket] = useState(true);
  const [ai, setAi] = useState(false);

  const aiAvailable = !!options?.ai_available;
  const sources: [Source, string][] = [
    ["file", "Файл"],
    ["text", "Текст"],
    ...(s?.resume_name ? ([["saved", "Из настроек"]] as [Source, string][]) : []),
  ];

  const start = async () => {
    const file = source === "file" ? (fileRef.current?.files?.[0] ?? null) : null;
    if (source === "file" && !file) return toast.info("Выберите файл резюме");
    if (source === "text" && text.trim().length < 80) return toast.info("Вставьте текст резюме целиком");
    if (role.trim().length < 2) return toast.info("Укажите роль, например «Backend-разработчик Python»");
    const body: Body = {
      role: role.trim(),
      grade,
      use_market: market,
      use_ai: ai && aiAvailable,
      use_saved_file: source === "saved",
      text: source === "text" ? text : undefined,
    };
    const r = await create.mutateAsync(reviewBody(body, file));
    toast.info("Проверяю резюме…");
    if (fileRef.current) fileRef.current.value = "";
    onStarted(r.id);
  };

  return (
    <Section
      title={
        <>
          <FileSearch className="size-[18px]" />
          Новая проверка
        </>
      }
      description="Файл остаётся на вашем компьютере. Для сравнения с рынком бот читает открытые вакансии hh без входа в аккаунт"
    >
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4">
        <Field label="Резюме">
          <div className="mb-2.5">
            <Segmented value={source} options={sources} onChange={setSource} label="Откуда взять резюме" />
          </div>
          {source === "file" && (
            <Input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md" className="max-w-[360px]" aria-label="Файл резюме" />
          )}
          {source === "text" && (
            <Textarea
              className="min-h-44"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Вставьте текст резюме: можно скопировать со страницы резюме на hh"
              aria-label="Текст резюме"
            />
          )}
          {source === "saved" && <p className="text-sm text-ink-2">Возьму файл из настроек: {s?.resume_name}</p>}
          {source === "file" && <Hint>PDF, DOCX или TXT. Если PDF — скан без текста, вставьте текст вручную</Hint>}
        </Field>

        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
          <Field label="Роль" htmlFor="review-role" hint="Как в заголовке вакансий: язык и направление помогают точнее найти рынок">
            <Input
              id="review-role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              list="review-roles"
              placeholder="Backend-разработчик Python"
            />
            <datalist id="review-roles">
              {options?.roles.map((r) => (
                <option key={r.key} value={r.label} />
              ))}
            </datalist>
          </Field>
          <Field label="Грейд" className="min-w-0">
            <div className="max-w-full overflow-x-auto pb-1">
              <Segmented
                value={grade}
                options={(options?.grades ?? []).map((g) => [g.key as Grade, g.label] as [Grade, string])}
                onChange={setGrade}
                label="Грейд"
              />
            </div>
          </Field>
        </div>

        <SwitchRow
          id="review-market"
          checked={market}
          onChange={setMarket}
          title="Сравнить с реальными вакансиями hh"
          hint={`Прочитаю до ${s?.review_market_size ?? 25} свежих вакансий по роли и грейду, около минуты. Повторная проверка в течение суток — мгновенно`}
        />
        <SwitchRow
          id="review-ai"
          checked={ai && aiAvailable}
          onChange={setAi}
          disabled={!aiAvailable}
          title={
            <span className="inline-flex items-center gap-1.5">
              <Sparkles className="size-4" />
              ИИ-разбор (Qwen, локально)
            </span>
          }
          hint={
            aiAvailable ? (
              `Мнение рекрутера и переписанные строки опыта от модели ${s?.ai_model ?? "qwen3:8b"} на вашем компьютере. Добавит 1–2 минуты`
            ) : (
              <>
                Выключен. Включить можно в{" "}
                <Link href="/settings#ai" className="underline">
                  настройках
                </Link>
                . Модель работает у вас на компьютере, бесплатно
              </>
            )
          }
        />

        <div>
          <Button variant="brand" size="lg" disabled={create.isPending} onClick={start}>
            <FileSearch />
            Проверить резюме
          </Button>
        </div>
      </div>
    </Section>
  );
}
