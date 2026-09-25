import type { Metadata } from "next";

import { TodayPage } from "@/features/today/today-page";

export const metadata: Metadata = { title: "Сегодня" };

export default function Page() {
  return <TodayPage />;
}
