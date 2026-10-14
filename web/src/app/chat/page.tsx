/** Список разговоров + запуск сценариев изучения. */

import Link from "next/link";
import { api } from "@/lib/api";
import type { ConversationItem } from "@/lib/types";
import { StudyButtons, StudyEmptyState } from "@/components/chat/study-buttons";

export const dynamic = "force-dynamic";

const MODE_LABEL: Record<string, string> = { free: "свободный", quick: "разбор", session: "сессия" };

export default async function ChatListPage() {
  const conversations = await api<ConversationItem[]>("/conversations").catch(() => [] as ConversationItem[]);
  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Чат</h1>
        <StudyButtons compact />
      </header>
      {conversations.length === 0 ? (
        <div className="mx-auto mt-10 max-w-2xl">
          <StudyEmptyState />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {conversations.map((c) => (
            <Link
              key={c.uid}
              href={`/chat/${c.uid}`}
              className="flex items-center gap-3 rounded-xl border bg-card p-4 transition hover:border-violet-500/50"
            >
              <span className="text-lg">{c.mode === "session" ? "🎓" : c.mode === "quick" ? "⚡" : "💬"}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{c.title}</p>
                <p className="text-xs text-muted-foreground">{MODE_LABEL[c.mode] ?? c.mode}</p>
              </div>
              <span className="text-xs text-muted-foreground">{new Date(c.updated_at).toLocaleString("ru-RU")}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
