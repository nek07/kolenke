"use client";

import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { $api, type Settings, type SettingsUpdate } from "@/api/client";

export function useSettings() {
  return $api.useQuery("get", "/api/settings", {}, { staleTime: 30_000 });
}

/** PATCH /api/settings; the response is the saved settings, so the cache is updated without a refetch. */
export function useSaveSettings() {
  const qc = useQueryClient();
  const mutation = $api.useMutation("patch", "/api/settings", {
    onSuccess: (data) => qc.setQueryData(["get", "/api/settings", {}], data),
  });
  return {
    ...mutation,
    save: (body: SettingsUpdate, message: string | false = "Сохранено") =>
      mutation.mutateAsync({ body }).then((s: Settings) => {
        if (message) toast.success(message);
        return s;
      }),
  };
}
