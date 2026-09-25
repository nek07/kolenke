"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import type { paths } from "@/api/schema";

/** Marks the given API paths stale (with any params), e.g. refresh("/api/vacancies", "/api/status"). */
export function useRefresh() {
  const qc = useQueryClient();
  return useCallback(
    (...paths: (keyof paths)[]) => Promise.all(paths.map((path) => qc.invalidateQueries({ queryKey: ["get", path] }))),
    [qc],
  );
}

/** Everything that shows vacancies: lists, the review queue, one vacancy, the board, counters. */
export const VACANCY_VIEWS: (keyof paths)[] = [
  "/api/vacancies",
  "/api/vacancies/review",
  "/api/vacancies/{vid}",
  "/api/pipeline",
  "/api/reminders",
  "/api/status",
];
