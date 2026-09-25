import type { Metadata } from "next";

import { AnswersPage } from "@/features/answers/answers-page";

export const metadata: Metadata = { title: "База ответов" };

export default function Page() {
  return <AnswersPage />;
}
