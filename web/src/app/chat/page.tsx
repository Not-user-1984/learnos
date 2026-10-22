/** Список разговоров + запуск сценариев изучения. */

import Link from "next/link";
import { api } from "@/lib/api";
import { Icon } from "@/components/ui/icon";
import { modeIcon, modeLabel } from "@/lib/format";
import type { ConversationItem } from "@/lib/types";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { StudyButtons, StudyEmptyState } from "@/components/chat/study-buttons";

export const dynamic = "force-dynamic";



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
            <div
              key={c.uid}
              className="group relative flex items-center gap-3 rounded-xl border bg-card p-4 transition hover:border-violet-500/50"
            >
              <Link href={`/chat/${c.uid}`} className="flex min-w-0 flex-1 items-center gap-3">
                <Icon name={modeIcon(c.mode)} size={22} className="text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{c.title}</p>
                  <p className="text-xs text-muted-foreground">{modeLabel(c.mode)}</p>
                </div>
                <span className="text-xs text-muted-foreground">{new Date(c.updated_at).toLocaleString("ru-RU")}</span>
              </Link>
              <ConfirmDeleteButton
                endpoint={`/conversations/${c.uid}`}
                title="Удалить разговор?"
                name={c.title}
                description="Сообщения разговора удалятся безвозвратно. Блоки базы знаний, созданные по нему, останутся."
                successMessage="Разговор удалён"
                className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 transition group-hover:opacity-100"
                buttonClassName="rounded-lg bg-background/60 p-1.5 text-muted-foreground backdrop-blur transition hover:text-rose-500"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
