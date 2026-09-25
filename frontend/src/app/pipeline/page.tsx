import type { Metadata } from "next";

import { PipelinePage } from "@/features/pipeline/pipeline-page";

export const metadata: Metadata = { title: "Воронка" };

export default function Page() {
  return <PipelinePage />;
}
