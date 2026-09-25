import type { Schemas } from "@/api/client";
import { EmptyState, ProgressBar } from "@/components/blocks";
import { INVITE_RE } from "@/lib/format";

/** Sent → viewed → invited, from the hh states of your responses. */
export function Funnel({ states }: { states: Schemas["StateCount"][] }) {
  const sum = (re: RegExp) => states.filter((s) => re.test(s.state)).reduce((a, s) => a + s.n, 0);
  const total = states.reduce((a, s) => a + s.n, 0);
  if (!total)
    return (
      <EmptyState emoji="🌱" title="Пока пусто">
        Отправьте первые отклики, и здесь появится путь от отклика до приглашения
      </EmptyState>
    );
  const invited = sum(INVITE_RE);
  const declined = sum(/отказ/);
  const viewed = sum(/^просмотрен/) + invited + declined;
  const rows: [string, number, string][] = [
    ["Отправлено", total, "bg-foreground"],
    ["Просмотрено", viewed, "bg-info"],
    ["Приглашения", invited, "bg-success"],
    ["Не сейчас", declined, "bg-border"],
  ];
  return (
    <div className="flex flex-col gap-3.5">
      {rows.map(([label, n, color]) => (
        <div key={label} className="grid grid-cols-[120px_1fr_48px] items-center gap-3 text-sm">
          <span>{label}</span>
          <ProgressBar value={n ? Math.max(3, (n * 100) / total) : 0} barClassName={color} />
          <b className="text-right tabular-nums">{n}</b>
        </div>
      ))}
    </div>
  );
}
