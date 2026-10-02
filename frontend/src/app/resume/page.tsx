import type { Metadata } from "next";

import { ResumePage } from "@/features/resume/resume-page";

export const metadata: Metadata = { title: "Проверка резюме" };

export default function Page() {
  return <ResumePage />;
}
