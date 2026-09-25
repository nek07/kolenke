"use client";

import { useRef } from "react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const VARIABLES: [string, string][] = [
  ["{company}", "компания"],
  ["{position}", "должность"],
  ["{name}", "имя"],
  ["{phone}", "телефон"],
];

/** A letter template with clickable {variables} that are inserted at the cursor. */
export function TemplateField({
  value,
  onChange,
  multiline = true,
  id,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  id?: string;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);

  function insert(variable: string) {
    const el = ref.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? start;
    onChange(value.slice(0, start) + variable + value.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + variable.length, start + variable.length);
    });
  }

  const Field = multiline ? Textarea : Input;
  return (
    <div className={className}>
      <Field id={id} ref={ref} value={value} onChange={(e) => onChange(e.target.value)} className={multiline ? "min-h-32" : undefined} />
      <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Переменные">
        {VARIABLES.map(([v, title]) => (
          <button
            key={v}
            type="button"
            title={title}
            onClick={() => insert(v)}
            className="rounded-lg border-[1.5px] border-dashed bg-surface-2 px-2 py-0.5 font-mono text-[13px] text-ink-2 hover:border-foreground hover:text-foreground"
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}
