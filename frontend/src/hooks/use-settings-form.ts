"use client";

import { useEffect } from "react";
import { useForm, type DefaultValues, type FieldValues, type Path } from "react-hook-form";

import { fieldErrors, type Settings, type SettingsUpdate } from "@/api/client";
import { useSaveSettings, useSettings } from "@/hooks/use-settings";

/**
 * A form over a slice of the settings. Validation rules live in the backend (one source of truth):
 * a 422 is mapped onto the fields. Only changed fields are sent.
 */
export function useSettingsForm<K extends keyof SettingsUpdate>(keys: readonly K[]) {
  type Values = { [P in K]: P extends keyof Settings ? Settings[P] : NonNullable<SettingsUpdate[P]> } & FieldValues;
  // write-only fields (the Gmail password) are not in the saved settings: they start empty
  const pick = (source: Settings) =>
    Object.fromEntries(keys.map((k) => [k, (source as Record<string, unknown>)[k]])) as DefaultValues<Values>;
  const { data } = useSettings();
  const { save, isPending } = useSaveSettings();
  const form = useForm<Values>();

  // (re)load the form when the saved settings change, keeping what you are typing
  useEffect(() => {
    if (!data) return;
    form.reset(pick(data), { keepDirtyValues: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- pick depends only on keys
  }, [data, form, keys]);

  const submit = (message: string | false = "Сохранено") =>
    form.handleSubmit(async (values) => {
      const dirty = form.formState.dirtyFields as Record<string, unknown>;
      const changes = Object.fromEntries(Object.entries(values).filter(([k]) => dirty[k])) as SettingsUpdate;
      if (!Object.keys(changes).length) return;
      try {
        const saved = await save(changes, message);
        form.reset(pick(saved));
      } catch (e) {
        // the toast is shown by the query client; here the message goes next to its field
        for (const [field, msg] of Object.entries(fieldErrors(e))) form.setError(field as Path<Values>, { message: msg });
      }
    })();

  return { form, submit, saving: isPending, ready: !!data };
}
