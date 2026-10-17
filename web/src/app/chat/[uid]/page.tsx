/** Разговор: лента + SSE-стриминг. */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { ConversationDetail } from "@/lib/types";
import { ChatViewWithInitial as ChatView } from "@/components/chat/chat-view";

export const dynamic = "force-dynamic";

export default async function ChatPage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let conversation: ConversationDetail;
  try {
    conversation = await api<ConversationDetail>(`/conversations/${uid}`);
  } catch {
    notFound();
  }
  return <ChatView conversation={conversation} />;
}
