"use client";

import { toast } from "sonner";

import { useTasks } from "@/components/providers/tasks";
import { Switch } from "@/components/ui/switch";
import { useSaveSettings, useSettings } from "@/hooks/use-settings";

export function AutopilotSwitch({ id }: { id?: string }) {
  const { data: s } = useSettings();
  const { save, isPending } = useSaveSettings();
  if (!s) return <Switch disabled checked={false} aria-label="Автопилот" />;
  return (
    <Switch
      id={id}
      aria-label="Автопилот"
      checked={s.autopilot_on}
      disabled={isPending}
      className="data-[state=checked]:bg-success"
      onCheckedChange={async (on) => {
        await save({ autopilot_on: on }, false);
        if (!on) toast.info("Автопилот на паузе. Возвращайтесь, когда захотите");
        else if (s.autopilot_mode === "auto") toast.success("Автопилот включён. Первая проверка в течение минуты");
        else toast.success("Автопилот включён. Когда найдутся вакансии, пришлю уведомление");
      }}
    />
  );
}

/** «Следующая проверка в 14:30» / «Работает с 8:00 до 22:00» / «Выключен». */
export function useAutopilotText() {
  const { data: s } = useSettings();
  const { status } = useTasks();
  if (!s?.autopilot_on) return "Выключен";
  return status?.autopilot_next
    ? `Следующая проверка в ${status.autopilot_next}`
    : `Работает с ${s.autopilot_from}:00 до ${s.autopilot_to}:00`;
}
