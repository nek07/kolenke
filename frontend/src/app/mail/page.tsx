import type { Metadata } from "next";

import { MailPage } from "@/features/mail/mail-page";

export const metadata: Metadata = { title: "Письма компаниям" };

export default function Page() {
  return <MailPage />;
}
