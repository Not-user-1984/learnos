"use client";

/** Split-view «читаю и обсуждаю» (B-006): материал слева, панель чата справа
 *  (≥1024px — колонка, на мобиле — шторка снизу через Dialog). */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { ChatPanel } from "@/components/chat/chat-panel";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type InsertPayload = { text: string; nonce: number };

export function ReaderSplit({
  sourceUid,
  chapterIdx,
  seekRef,
  children,
}: {
  sourceUid: string;
  chapterIdx: number;
  /** seek-функция видео-плеера (для таймкодов из ответов чата). */
  seekRef?: { current: ((seconds: number) => void) | null };
  children: (args: { openChat: (insert?: InsertPayload) => void }) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [insert, setInsert] = useState<InsertPayload | undefined>();

  const openChat = (payload?: InsertPayload) => {
    setOpen(true);
    if (payload) setInsert(payload);
  };

  const onTimecode = (seconds: number) => seekRef?.current?.(seconds);

  return (
    <div className="flex h-full min-w-0">
      <div className={cn("min-w-0 flex-1", open && "lg:max-w-[calc(100%-26rem)]")}>{children({ openChat })}</div>

      {/* десктоп: постоянная колонка справа */}
      {open && (
        <aside className="relative hidden w-[26rem] shrink-0 border-l lg:block">
          <ChatPanel
            key={`${sourceUid}:${chapterIdx}`}
            sourceUid={sourceUid}
            chapterIdx={chapterIdx}
            insert={insert}
            onTimecode={onTimecode}
            onClose={() => setOpen(false)}
          />
        </aside>
      )}

      {/* мобила: шторка снизу */}
      <Dialog open={open && isMobileFree()} onOpenChange={setOpen}>
        <DialogContent className="top-auto bottom-0 h-[78dvh] max-h-[78dvh] max-w-full translate-y-0 rounded-t-2xl p-0 sm:max-w-full">
          <DialogHeader className="border-b px-4 py-2">
            <DialogTitle className="text-sm">Обсуждение</DialogTitle>
          </DialogHeader>
          <div className="h-[calc(78dvh-3rem)]">
            <ChatPanel
              key={`m-${sourceUid}:${chapterIdx}`}
              sourceUid={sourceUid}
              chapterIdx={chapterIdx}
              insert={insert}
              onTimecode={onTimecode}
            />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Диалог-шторка только на узких экранах: на десктопе панель уже колонкой. */
function isMobileFree(): boolean {
  if (typeof window === "undefined") return false;
  return window.innerWidth < 1024;
}

/** Кнопка «Обсудить» для шапки материала: открывает панель (B-006). */
export function DiscussButton({ onClick, busy }: { onClick: () => void; busy?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm transition hover:bg-accent disabled:opacity-60"
    >
      {busy ? <Icon name="progress_activity" size={15} className="animate-spin" /> : <Icon name="chat_bubble" size={15} />}
      Обсудить
    </button>
  );
}
