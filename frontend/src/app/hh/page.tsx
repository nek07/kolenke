import type { Metadata } from "next";

import { HhPage } from "@/features/hh/hh-page";

export const metadata: Metadata = { title: "HeadHunter" };

export default function Page() {
  return <HhPage />;
}
