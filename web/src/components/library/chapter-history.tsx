"use client";

/** История разговоров по главе — кнопка + модал (в читалке и в списке глав источника). */

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { ConversationItem } from "@/lib/types";
import { api } from "@/lib/api";
import { modeLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function ChapterHistoryButton({
  sourceUid,
  chapterIdx,
  chapterTitle,
  size = "sm",
}: {
  sourceUid: string;
  chapterIdx: number;
  chapterTitle?: string;
  size?: "sm" | "icon";
}) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ConversationItem[] | null>(null);

  const openHistory = async () => {
    setOpen(true);
    setHistory(null);
    try {
      const items = await api<ConversationItem[]>(
        `/conversations?source=${encodeURIComponent(sourceUid)}&chapter=${chapterIdx}`,
      );
      setHistory(items);
    } catch {
      setHistory([]);
      toast.error("не удалось загрузить историю");
    }
  };

  return (
    <>
      <Button variant="outline" size={size === "icon" ? "icon" : "sm"} aria-label="История разговоров по главе" onClick={() => void openHistory()}>
        <Icon name="history" size={16} className={size === "icon" ? "" : "mr-1"} />
        {size === "sm" && "История"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="truncate">
              История: {chapterTitle ?? `глава ${chapterIdx}`}
            </DialogTitle>
          </DialogHeader>
          {history === null && (
            <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Icon name="progress_activity" size={16} className="animate-spin" /> ищу разговоры…
            </p>
          )}
          {history !== null && history.length === 0 && (
            <p className="py-6 text-sm text-muted-foreground">
              По этой главе ещё не было разговоров — начни с кнопки «Обсудить».
            </p>
          )}
          <div className="flex flex-col gap-2">
            {(history ?? []).map((c) => (
              <Link
                key={c.uid}
                href={`/chat/${c.uid}`}
                className="flex items-center gap-3 rounded-xl border px-4 py-3 transition hover:border-primary/50 hover:bg-accent"
                onClick={() => setOpen(false)}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {c.scenario || modeLabel(c.mode)} ·{" "}
                    {new Date(c.updated_at).toLocaleString("ru-RU", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {c.messages_count ? ` · ${c.messages_count} сообщ.` : ""}
                  </p>
                </div>
                <Icon name="chevron_right" size={16} className="shrink-0 text-muted-foreground" />
              </Link>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
