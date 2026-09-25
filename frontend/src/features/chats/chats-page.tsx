"use client";

import { Bot, ExternalLink, Mail, RefreshCw, Send, User } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { $api, type ChatItem } from "@/api/client";
import { CHAT_REPLY_STATE, Pill } from "@/components/badges";
import { EmptyState, PageHeader, Section } from "@/components/blocks";
import { Segmented } from "@/components/form";
import { useTasks } from "@/components/providers/tasks";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useQueryParam } from "@/hooks/use-query-param";
import { useRefresh } from "@/hooks/use-refresh";
import { useSettings } from "@/hooks/use-settings";
import { ago, messageParts } from "@/lib/format";
import { cn } from "@/lib/utils";

type View = "pending" | "history" | "info";
const EMPTY: ChatItem[] = [];

function PendingCard({ c, domain }: { c: ChatItem; domain: string }) {
  const refresh = useRefresh();
  const [reply, setReply] = useState(c.reply ?? "");
  const send = $api.useMutation("post", "/api/chats/{cid}/reply");
  const hide = $api.useMutation("post", "/api/chats/{cid}/hide");
  const initial = (c.company ?? "?").replace(/[«»"]/g, "").trim().slice(0, 1).toUpperCase();
  return (
    <article className="mb-3 rounded-2xl border bg-card p-[18px]">
      <div className="mb-3 flex items-center gap-2.5">
        <div className="grid size-[38px] flex-none place-items-center rounded-xl bg-brand font-extrabold text-[#141414]">{initial}</div>
        <div className="min-w-0 flex-1">
          <b>{c.company}</b>
          <div className="text-[13px] text-muted-foreground">{c.vacancy}</div>
        </div>
        <Pill tone={c.robot ? "info" : "brand"}>{c.robot ? "HR-робот" : "Рекрутер"}</Pill>
        <span className="text-[13px] text-muted-foreground">{ago(c.created_at)}</span>
      </div>
      {messageParts(c.message).map((m, i) => (
        <div key={i} className="mb-3 rounded-[4px_16px_16px_16px] bg-muted px-3.5 py-3 whitespace-pre-wrap">
          {m}
        </div>
      ))}
      <Textarea
        className="min-h-20"
        placeholder="Напишите ответ…"
        aria-label="Ответ"
        value={reply}
        onChange={(e) => setReply(e.target.value)}
      />
      <div className="mt-2.5 flex flex-wrap gap-2">
        <Button
          variant="brand"
          disabled={!reply.trim() || send.isPending}
          onClick={async () => {
            const r = await send.mutateAsync({ params: { path: { cid: c.id } }, body: { reply } });
            toast.info(r.started ? "Отправляю ответ…" : "Бот занят, отправлю, как освободится");
            await refresh("/api/chats", "/api/status");
          }}
        >
          <Send />
          Отправить
        </Button>
        <Button variant="ghost" asChild>
          <a href={`https://${domain}/chat/${c.chat_id}`} target="_blank" rel="noreferrer">
            <ExternalLink />
            Открыть чат
          </a>
        </Button>
        <span className="flex-1" />
        <Button
          variant="ghost"
          onClick={async () => {
            await hide.mutateAsync({ params: { path: { cid: c.id } } });
            await refresh("/api/chats", "/api/status");
          }}
        >
          Скрыть
        </Button>
      </div>
    </article>
  );
}

function HistoryRow({ c, view }: { c: ChatItem; view: View }) {
  const Icon = view === "info" ? Mail : c.status === "auto_sent" ? Bot : User;
  const tone =
    view === "info" ? "bg-muted text-ink-2" : c.status === "auto_sent" ? "bg-info-soft text-info" : "bg-success-soft text-success";
  return (
    <li className="flex gap-3 border-b border-muted py-2.5 last:border-0">
      <span className={cn("grid size-[30px] flex-none place-items-center rounded-[9px]", tone)}>
        <Icon className="size-[15px]" />
      </span>
      <div className="min-w-0 flex-1 text-sm">
        <b>{c.company}</b> <span className="text-[13px] text-muted-foreground">{c.vacancy}</span>
        <div className="mt-1 text-[13px] text-muted-foreground">
          {messageParts(c.message).join(" · ").replace(/\s+/g, " ").slice(0, 220)}
        </div>
        {c.reply && view !== "info" && (
          <div className="mt-1.5">
            ↳ {c.reply} <span className="text-[13px] text-muted-foreground">· {CHAT_REPLY_STATE[c.status] ?? ""}</span>
          </div>
        )}
      </div>
      <time className="text-[12.5px] whitespace-nowrap text-muted-foreground">{ago(c.sent_at || c.created_at)}</time>
    </li>
  );
}

export function ChatsPage() {
  const [view, setView] = useQueryParam<View>("view", "pending");
  const { run } = useTasks();
  const { data: s } = useSettings();
  const domain = s?.hh_domain ?? "hh.kz";
  const pending = $api.useQuery(
    "get",
    "/api/chats",
    { params: { query: { status: view === "info" ? "info" : "pending" } } },
    { enabled: view !== "history" },
  );
  const history = $api.useQuery("get", "/api/chats/history", {}, { enabled: view === "history" });
  const rows = (view === "history" ? history.data : pending.data) ?? EMPTY;

  return (
    <>
      <PageHeader title="Чаты" description="Сообщения работодателей. Роботам бот отвечает сам, а вам остаются только живые разговоры" />
      <div className="mb-[18px] flex flex-wrap items-center gap-2">
        <Segmented
          label="Какие сообщения"
          value={view}
          onChange={setView}
          options={[
            ["pending", "Ждут ответа"],
            ["history", "Отправленные"],
            ["info", "Уведомления"],
          ]}
        />
        <span className="flex-1" />
        <Button variant="outline" onClick={() => run("chat_check")}>
          <RefreshCw />
          Проверить сейчас
        </Button>
        <Button variant="ghost" asChild>
          <a href={`https://${domain}/chat`} target="_blank" rel="noreferrer">
            <ExternalLink />
            Чаты на hh
          </a>
        </Button>
      </div>
      {view === "pending" ? (
        rows.length ? (
          rows.map((c) => <PendingCard key={c.id} c={c} domain={domain} />)
        ) : (
          <Section>
            <EmptyState emoji="💬" title="Все сообщения отвечены">
              Когда работодатель напишет, сообщение появится здесь, а на Mac придёт уведомление
            </EmptyState>
          </Section>
        )
      ) : (
        <Section className="py-2">
          {rows.length ? (
            <ul>
              {rows.map((c) => (
                <HistoryRow key={c.id} c={c} view={view} />
              ))}
            </ul>
          ) : (
            <EmptyState emoji="🗂️" title="Пока пусто" />
          )}
        </Section>
      )}
    </>
  );
}
