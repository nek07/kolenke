"use client";

import { useState } from "react";
import { toast } from "sonner";

import { $api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useRefresh, VACANCY_VIEWS } from "@/hooks/use-refresh";

/** «Напомнить о себе»: a draft from the template, editable, sent to the vacancy chat on hh. */
export function FollowupDialog({ vacancyId, onClose }: { vacancyId: number | null; onClose: () => void }) {
  return (
    <Dialog open={vacancyId != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Напомнить о себе</DialogTitle>
          <DialogDescription>Сообщение уйдёт в чат вакансии на hh. Можно поправить текст</DialogDescription>
        </DialogHeader>
        {vacancyId != null && <Draft key={vacancyId} vacancyId={vacancyId} onDone={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function Draft({ vacancyId, onDone }: { vacancyId: number; onDone: () => void }) {
  const refresh = useRefresh();
  const { data } = $api.useQuery("get", "/api/vacancies/{vid}/followup-draft", { params: { path: { vid: vacancyId } } });
  const send = $api.useMutation("post", "/api/vacancies/{vid}/followup");
  const [text, setText] = useState<string | null>(null);
  const value = text ?? data?.text ?? "";
  return (
    <>
      <Textarea className="min-h-40" value={value} onChange={(e) => setText(e.target.value)} aria-label="Текст напоминания" />
      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Отмена
        </Button>
        <Button
          variant="brand"
          disabled={!value.trim() || send.isPending}
          onClick={async () => {
            const r = await send.mutateAsync({ params: { path: { vid: vacancyId } }, body: { text: value } });
            toast.info(r.started ? "Отправляю напоминание…" : "Бот занят, отправлю, как освободится");
            await refresh(...VACANCY_VIEWS);
            onDone();
          }}
        >
          Отправить
        </Button>
      </DialogFooter>
    </>
  );
}
