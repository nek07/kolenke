"use client";

import { useId, type ReactNode } from "react";
import { Controller, type Control, type FieldValues, type Path, type UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function Field({
  label,
  hint,
  error,
  children,
  className,
  htmlFor,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <div className={className}>
      <Label htmlFor={htmlFor} className="mb-1.5 text-[13px] font-semibold text-ink-2">
        {label}
      </Label>
      {children}
      {error ? (
        <p className="mt-1.5 text-[13px] text-destructive" role="alert">
          {error}
        </p>
      ) : (
        hint && <p className="mt-1.5 text-[13px] text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}

/** A text or number input bound to a settings form. */
export function TextField<T extends FieldValues>({
  form,
  name,
  label,
  hint,
  type = "text",
  className,
  ...props
}: {
  form: UseFormReturn<T>;
  name: Path<T>;
  label: ReactNode;
  hint?: ReactNode;
  type?: "text" | "number" | "password" | "email";
  className?: string;
} & Omit<React.ComponentProps<typeof Input>, "form" | "name" | "type">) {
  const id = useId();
  const error = form.formState.errors[name]?.message as string | undefined;
  return (
    <Field label={label} hint={hint} error={error} className={className} htmlFor={id}>
      <Input
        id={id}
        type={type}
        aria-invalid={!!error}
        {...form.register(name, {
          setValueAs: type === "number" ? (v: string) => (v === "" ? undefined : Number(v)) : undefined,
        })}
        {...props}
      />
    </Field>
  );
}

/** A labelled on/off setting: «Пропускать вакансии без зарплаты». */
export function SwitchField<T extends FieldValues>({
  control,
  name,
  title,
  hint,
  onToggle,
}: {
  control: Control<T>;
  name: Path<T>;
  title: ReactNode;
  hint?: ReactNode;
  onToggle?: (value: boolean) => void;
}) {
  const id = useId();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className="flex items-center gap-3.5">
          <Switch
            id={id}
            checked={!!field.value}
            onCheckedChange={(v) => {
              field.onChange(v);
              onToggle?.(v);
            }}
            className="data-[state=checked]:bg-success"
          />
          <label htmlFor={id} className="cursor-pointer">
            <b className="font-semibold">{title}</b>
            {hint && <div className="text-[13px] text-muted-foreground">{hint}</div>}
          </label>
        </div>
      )}
    />
  );
}

/** Two or three mutually exclusive options as a segmented control. */
export function Segmented<V extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: V | undefined;
  options: [V, string][];
  onChange: (value: V) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-0.5 rounded-xl bg-muted p-[3px]">
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={v === value}
          onClick={() => onChange(v)}
          className={cn(
            "rounded-[9px] px-3.5 py-1.5 text-[13.5px] font-semibold text-ink-2",
            v === value && "bg-card text-foreground shadow-[0_1px_2px_rgba(0,0,0,.08)]",
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

/** Filter chips with counters: «Новые 12», «В очереди 3». */
export function Chips<V extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: V;
  options: { value: V; label: string; count?: number }[];
  onChange: (value: V) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border-[1.5px] bg-card px-3.5 py-1.5 text-[13.5px] font-semibold text-ink-2 hover:border-foreground hover:text-foreground",
            o.value === value && "border-foreground bg-foreground text-background hover:text-background",
          )}
        >
          {o.label}
          {o.count != null && <span className="opacity-55">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Multi-select chips, e.g. experience levels or job boards. */
export function ToggleChips<V extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: V[];
  options: [V, string][];
  onChange: (value: V[]) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map(([v, text]) => {
        const on = value.includes(v);
        return (
          <button
            key={v}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== v) : [...value, v])}
            className={cn(
              "rounded-full border-[1.5px] bg-card px-3.5 py-1.5 text-[13.5px] font-semibold text-ink-2 hover:border-foreground",
              on && "border-foreground bg-foreground text-background",
            )}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}
