import type { Metadata } from "next";

import { ChatsPage } from "@/features/chats/chats-page";

export const metadata: Metadata = { title: "Чаты" };

export default function Page() {
  return <ChatsPage />;
}
