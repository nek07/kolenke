"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type UIState = {
  /** The vacancy shown in the side panel, or null. */
  vacancyId: number | null;
  openVacancy: (id: number) => void;
  closeVacancy: () => void;
  reviewOpen: boolean;
  setReviewOpen: (open: boolean) => void;
  searchOpen: boolean;
  setSearchOpen: (open: boolean) => void;
};

const Ctx = createContext<UIState | null>(null);

/** Overlays that any screen can open: the vacancy panel, the review deck and the global search. */
export function UIStateProvider({ children }: { children: ReactNode }) {
  const [vacancyId, setVacancyId] = useState<number | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const value = useMemo(
    () => ({
      vacancyId,
      openVacancy: setVacancyId,
      closeVacancy: () => setVacancyId(null),
      reviewOpen,
      setReviewOpen,
      searchOpen,
      setSearchOpen,
    }),
    [vacancyId, reviewOpen, searchOpen],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useUI() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useUI must be used inside <UIStateProvider>");
  return ctx;
}
