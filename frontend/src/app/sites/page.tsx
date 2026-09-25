import type { Metadata } from "next";

import { SitesPage } from "@/features/sites/sites-page";

export const metadata: Metadata = { title: "Другие сайты" };

export default function Page() {
  return <SitesPage />;
}
