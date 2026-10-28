/** Стартовый экран чата: единый вход + история разговоров внизу. */

import { api } from "@/lib/api";
import type { ConversationItem } from "@/lib/types";
import { ChatStart } from "@/components/chat/chat-start";

export const dynamic = "force-dynamic";

export default async function ChatPage() {
  const conversations = await api<ConversationItem[]>("/conversations").catch(() => [] as ConversationItem[]);
  return <ChatStart conversations={conversations} />;
}
