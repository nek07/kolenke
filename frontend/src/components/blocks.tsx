import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end gap-4">
      <div className="min-w-0 flex-1">
        <h1 className="text-[25px] leading-tight font-extrabold tracking-[-0.03em] md:text-[30px]">{title}</h1>
        {description && <p className="mt-1.5 text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A white block with a title: the basic unit of every screen. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("mb-4 min-w-0 rounded-2xl border bg-card p-5 md:p-[22px]", className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            {title && <h2 className="flex items-center gap-2 text-[17px] font-bold tracking-[-0.01em]">{title}</h2>}
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ emoji, title, children }: { emoji: string; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="px-5 py-11 text-center text-muted-foreground">
      <div className="mb-2 text-[34px]" aria-hidden>
        {emoji}
      </div>
      <b className="mb-1 block text-base text-foreground">{title}</b>
      {children}
    </div>
  );
}

export function Hint({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("mt-1.5 text-[13px] text-muted-foreground", className)}>{children}</p>;
}

/** A banner that asks for one action: «Подключите hh», «12 вакансий ждут проверки». */
export function Banner({
  icon,
  title,
  children,
  action,
  tone = "brand",
}: {
  icon: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "brand" | "info" | "success" | "warning";
}) {
  const bg = { brand: "bg-brand-soft", info: "bg-info-soft", success: "bg-success-soft", warning: "bg-warning-soft" }[tone];
  return (
    <div className={cn("mb-4 flex flex-wrap items-center gap-x-3.5 gap-y-3 rounded-2xl px-[18px] py-4", bg)}>
      <span className="[&_svg]:size-[22px]">{icon}</span>
      <div className="min-w-[min(100%,180px)] flex-1">
        <b>{title}</b>
        {children && <div className="mt-0.5 text-[13px] text-ink-2">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ProgressBar({ value, className, barClassName }: { value: number; className?: string; barClassName?: string }) {
  return (
    <div
      className={cn("h-2 overflow-hidden rounded-full bg-muted", className)}
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <i
        className={cn("block h-full rounded-full bg-foreground transition-[width] duration-500", barClassName)}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

/** A collapsible settings block (native <details>: keyboard and screen readers work out of the box). */
export function Disclosure({
  icon,
  title,
  summary,
  children,
  id,
}: {
  icon?: ReactNode;
  title: ReactNode;
  summary?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <details id={id} className="group mb-3 rounded-2xl border bg-card">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-[22px] py-4 font-bold [&::-webkit-details-marker]:hidden [&_svg]:size-[18px]">
        {icon}
        {title}
        {summary && <small className="font-medium text-muted-foreground">{summary}</small>}
        <svg
          className="ml-auto text-muted-foreground transition-transform group-open:rotate-180"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          aria-hidden
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </summary>
      <div className="px-[22px] pb-[22px]">{children}</div>
    </details>
  );
}
