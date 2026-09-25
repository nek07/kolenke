"use client";

import { keepPreviousData } from "@tanstack/react-query";
import { Briefcase, ExternalLink, Mail, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { $api } from "@/api/client";
import { CompanyStatusBadge, VacancyStatusBadge } from "@/components/badges";
import { useUI } from "@/components/providers/ui-state";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { useSettings } from "@/hooks/use-settings";
import { messageParts } from "@/lib/format";

const SOURCES: Record<string, string> = { hh: "hh", habr: "Хабр Карьера", enbek: "Enbek", other: "вручную" };

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Highlights the query words in a text. */
function Marked({ text, query }: { text: string | null | undefined; query: string }) {
  const words = query
    .toLowerCase()
    .split(/\s+/)
    .filter((w) => w.length > 1);
  if (!text || !words.length) return <>{text}</>;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return (
    <>
      {text.split(re).map((part, i) =>
        i % 2 ? (
          <mark key={i} className="rounded-sm bg-brand px-px text-brand-foreground">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}

function Result({ icon, title, children }: { icon: ReactNode; title: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2.5">
      <span className="grid size-[30px] flex-none place-items-center rounded-lg bg-muted text-ink-2 [&_svg]:size-[15px]">{icon}</span>
      <div className="min-w-0 flex-1">
        <b className="font-medium">{title}</b>
        <div className="truncate text-[13px] text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

/** ⌘K: one box for a company anywhere — vacancies on all sites, employer chats, the mail list. */
export function SearchDialog() {
  const { searchOpen, setSearchOpen, openVacancy } = useUI();
  const router = useRouter();
  const { data: settings } = useSettings();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 150);
  const { data, isError } = $api.useQuery(
    "get",
    "/api/search",
    { params: { query: { q: query } } },
    { enabled: searchOpen && !!query, placeholderData: keepPreviousData, meta: { quiet: true } },
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = (e.target as HTMLElement).closest("input,textarea,select,[contenteditable]");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        setSearchOpen(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setSearchOpen]);

  const go = (action: () => void) => {
    setSearchOpen(false);
    action();
  };
  const snippet = (message: string | null | undefined) => {
    const text = messageParts(message).join(" · ").replace(/\s+/g, " ");
    const at = text.toLowerCase().indexOf(query.toLowerCase().split(/\s+/)[0] ?? "");
    const from = Math.max(0, at - 60);
    return (from > 0 ? "…" : "") + text.slice(from, from + 160);
  };
  const external: [string, string][] = [
    [`https://${settings?.hh_domain ?? "hh.kz"}/employers_list?query=`, "Компания на hh"],
    ["https://www.google.com/search?q=", "Google"],
  ];
  const found = data && query ? data.vacancies.length + data.chats.length + data.companies.length : 0;

  return (
    <CommandDialog
      open={searchOpen}
      onOpenChange={setSearchOpen}
      title="Поиск"
      description="Вакансии, чаты и письма компаниям"
      className="sm:max-w-[640px]"
    >
      <Command shouldFilter={false}>
        <CommandInput value={q} onValueChange={setQ} placeholder="Компания, вакансия, почта или текст сообщения" />
        <CommandList className="max-h-[min(480px,calc(100vh-200px))]">
          {!query && (
            <div className="px-3 py-5 text-sm text-muted-foreground">
              Ищет по вакансиям со всех сайтов, чатам с работодателями и списку писем компаниям
            </div>
          )}
          {query && isError && <CommandEmpty>Поиск сейчас недоступен: kolenke не отвечает</CommandEmpty>}
          {query && data && !found && (
            <div className="px-3 pt-4 pb-1 text-sm text-muted-foreground">В kolenke про «{query}» ничего нет. Можно поискать снаружи:</div>
          )}
          {query && !!data?.vacancies.length && (
            <CommandGroup heading="Вакансии">
              {data.vacancies.map((v) => (
                <CommandItem key={`v${v.id}`} value={`v${v.id}`} onSelect={() => go(() => openVacancy(v.id))}>
                  <Result icon={<Briefcase />} title={<Marked text={v.title} query={query} />}>
                    <Marked text={v.company} query={query} /> · {SOURCES[v.source] ?? v.source} · <VacancyStatusBadge status={v.status} />
                  </Result>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {query && !!data?.chats.length && (
            <CommandGroup heading="Чаты">
              {data.chats.map((c) => (
                <CommandItem
                  key={`c${c.id}`}
                  value={`c${c.id}`}
                  onSelect={() =>
                    go(() => router.push(`/chats?view=${c.status === "pending" || c.status === "info" ? c.status : "history"}`))
                  }
                >
                  <Result icon={<MessageCircle />} title={<Marked text={c.company} query={query} />}>
                    {c.vacancy && (
                      <>
                        <Marked text={c.vacancy} query={query} /> ·{" "}
                      </>
                    )}
                    <Marked text={snippet(c.message)} query={query} />
                  </Result>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {query && !!data?.companies.length && (
            <CommandGroup heading="Письма компаниям">
              {data.companies.map((c) => (
                <CommandItem key={`m${c.id}`} value={`m${c.id}`} onSelect={() => go(() => router.push(`/mail?company=${c.id}`))}>
                  <Result icon={<Mail />} title={<Marked text={c.name || c.email} query={query} />}>
                    <Marked text={c.email} query={query} />
                    {c.position && (
                      <>
                        {" "}
                        · <Marked text={c.position} query={query} />
                      </>
                    )}{" "}
                    · <CompanyStatusBadge status={c.status} />
                  </Result>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {query && (
            <CommandGroup heading="В интернете">
              {external.map(([url, label]) => (
                <CommandItem
                  key={label}
                  value={`x${label}`}
                  onSelect={() => go(() => window.open(url + encodeURIComponent(query), "_blank", "noopener"))}
                >
                  <Result icon={<ExternalLink />} title={`${label}: «${query}»`}>
                    откроется в новой вкладке
                  </Result>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
