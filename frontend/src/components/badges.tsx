import type { ChatStatus, CompanyStatus, VacancyStatus } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { INVITE_RE } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

const TONES: Record<Tone, string> = {
  neutral: "bg-muted text-ink-2",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-destructive",
  brand: "bg-brand text-brand-foreground",
};

export function Pill({ tone = "neutral", className, ...props }: React.ComponentProps<"span"> & { tone?: Tone }) {
  return <Badge className={cn("h-auto rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold", TONES[tone], className)} {...props} />;
}

const VACANCY: Record<VacancyStatus, [string, Tone]> = {
  new: ["Новая", "neutral"],
  queued: ["В очереди", "info"],
  applied: ["Отклик отправлен", "success"],
  attention: ["Нужен ваш ответ", "warning"],
  skipped: ["Пропущена", "neutral"],
  error: ["Не получилось", "danger"],
};

export function VacancyStatusBadge({ status }: { status: VacancyStatus }) {
  const [label, tone] = VACANCY[status];
  return <Pill tone={tone}>{label}</Pill>;
}

const COMPANY: Record<CompanyStatus, [string, Tone]> = {
  new: ["Новая", "neutral"],
  queued: ["В очереди", "info"],
  sent: ["Отправлено", "success"],
  error: ["Ошибка", "danger"],
};

export function CompanyStatusBadge({ status }: { status: CompanyStatus }) {
  const [label, tone] = COMPANY[status];
  return <Pill tone={tone}>{label}</Pill>;
}

/** The employer's reaction on hh; a refusal is shown softly as «не сейчас». */
export function HhStateBadge({ state }: { state: string | null | undefined }) {
  if (!state) return null;
  const tone: Tone = INVITE_RE.test(state) ? "success" : /отказ|не просм/.test(state) ? "neutral" : "info";
  return <Pill tone={tone}>{/отказ/.test(state) ? "не сейчас" : state}</Pill>;
}

/** hh «совпадение навыков». */
export function MatchBadge({ value, label = "" }: { value: number | null | undefined; label?: string }) {
  if (value == null) return <span className="text-sm text-muted-foreground">—</span>;
  const tone = value >= 70 ? "success" : value >= 40 ? "warning" : "neutral";
  return (
    <Pill tone={tone} className="tabular-nums">
      {label}
      {value}%
    </Pill>
  );
}

export const CHAT_REPLY_STATE: Partial<Record<ChatStatus, string>> = {
  auto_sent: "ответил бот",
  approved: "отправляется",
  closed: "не отправлено: работодатель закрыл чат",
  sent: "ответили вы",
};
