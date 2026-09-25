import type { Metadata } from "next";

import { SettingsPage } from "@/features/settings/settings-page";

export const metadata: Metadata = { title: "Настройки" };

export default function Page() {
  return <SettingsPage />;
}
