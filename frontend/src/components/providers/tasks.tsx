"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import { toast } from "sonner";

import { $api, fetchClient, type Status, type TaskKey } from "@/api/client";
import { pluralN } from "@/lib/format";

const START_MESSAGE: Record<TaskKey, string> = {
  hh_login: "Открываю окно hh. Войдите в аккаунт",
  hh_check: "Проверяю вход в hh",
  hh_resumes: "Загружаю ваши резюме",
  hh_search: "Ищу подходящие вакансии",
  hh_apply: "Отправляю отклики",
  hh_sync: "Обновляю ответы работодателей",
  hh_letters: "Досылаю письма в чаты",
  hh_followups: "Отправляю напоминания",
  other_search: "Смотрю другие сайты",
  chat_check: "Проверяю чаты",
  autopilot_now: "Запускаю цикл автопилота",
  mail_send: "Отправляю письма",
};

const POLL_MS = 2500;

type Snapshot = { key: TaskKey; applied: number; sent: number; fresh: number };

type TasksContext = {
  status: Status | undefined;
  run: (key: TaskKey) => Promise<boolean>;
  stop: () => Promise<void>;
};

const Ctx = createContext<TasksContext | null>(null);

const counts = (s: Status | undefined) => ({
  applied: s?.vacancies.applied ?? 0,
  sent: s?.companies.sent ?? 0,
  fresh: s?.vacancies.new ?? 0,
});

/** Polls /api/status, starts background tasks and reports what a finished task did. */
export function TasksProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data: status } = $api.useQuery("get", "/api/status", {}, { refetchInterval: POLL_MS });
  const snapshot = useRef<Snapshot | null>(null);
  const wasRunning = useRef(false);

  useEffect(() => {
    if (!status) return;
    if (wasRunning.current && !status.running) {
      report(snapshot.current, status);
      snapshot.current = null;
      // a task changes vacancies, chats, settings (resumes) and more: refresh everything the page shows
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[1] !== "/api/status" });
    }
    wasRunning.current = status.running;
  }, [status, qc]);

  const run = useCallback(
    async (key: TaskKey) => {
      const { error } = await fetchClient.POST("/api/jobs/{key}", { params: { path: { key } } });
      if (error) {
        toast.error((error as { detail?: string }).detail ?? "Не удалось запустить");
        return false;
      }
      snapshot.current = { key, ...counts(status) };
      wasRunning.current = true;
      toast.info(`${START_MESSAGE[key]}…`);
      void qc.invalidateQueries({ queryKey: ["get", "/api/status"] });
      return true;
    },
    [qc, status],
  );

  const stop = useCallback(async () => {
    await fetchClient.POST("/api/jobs/stop");
    toast.info("Останавливаю после текущего шага");
  }, []);

  const value = useMemo(() => ({ status, run, stop }), [status, run, stop]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function report(before: Snapshot | null, after: Status) {
  if (!before) return;
  const now = counts(after);
  const applied = now.applied - before.applied;
  const sent = now.sent - before.sent;
  const fresh = now.fresh - before.fresh;
  if (applied > 0) toast.success(`Отправлено ${pluralN(applied, "отклик", "отклика", "откликов")}`);
  else if (sent > 0) toast.success(`Отправлено ${pluralN(sent, "письмо", "письма", "писем")}`);
  else if (before.key === "hh_search" && fresh > 0)
    toast.success(`Найдено ${pluralN(fresh, "новая вакансия", "новые вакансии", "новых вакансий")}`);
  else if (before.key === "hh_search") toast.info("Новых вакансий не появилось. Загляну позже");
  else toast.success("Готово");
}

export function useTasks() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTasks must be used inside <TasksProvider>");
  return ctx;
}
