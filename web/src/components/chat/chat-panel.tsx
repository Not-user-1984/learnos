"use client";

/** Панель чата рядом с читалкой/видео (B-006): get-or-create разговора главы
 *  на сервере, дальше — обычный ChatView в компактном panel-варианте. */

import { Suspense, useEffect, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { api, apiPost } from "@/lib/api";
import type { ConversationDetail } from "@/lib/types";
import { ChatView } from "@/components/chat/chat-view";

type Props = {
  sourceUid: string;
  chapterIdx: number;
  /** Вставка в композер: цитата из текста или момент видео (B-006). */
  insert?: { text: string; nonce: number };
  /** Клик по таймкоду [мм:сс] — seek видео-плеера. */
  onTimecode?: (seconds: number) => void;
  onClose?: () => void;
};

export function ChatPanel({ sourceUid, chapterIdx, insert, onTimecode, onClose }: Props) {
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiPost<{ uid: string }>(`/sources/${sourceUid}/chapters/${chapterIdx}/conversation`, {})
      .then((c) => api<ConversationDetail>(`/conversations/${c.uid}`))
      .then((detail) => {
        if (!cancelled) setConv(detail);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceUid, chapterIdx]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {failed ? (
        <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-muted-foreground">
          Не удалось открыть разговор — проверь ядро и обнови страницу.
        </div>
      ) : !conv ? (
        <p className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
          <Icon name="progress_activity" size={15} className="animate-spin" /> открываю разговор главы…
        </p>
      ) : (
        <Suspense fallback={null}>
          <ChatView conversation={conv} variant="panel" insert={insert} onTimecode={onTimecode} />
        </Suspense>
      )}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Скрыть чат"
          className="absolute right-2 top-2 z-10 rounded-lg p-1.5 text-muted-foreground transition hover:bg-accent hover:text-foreground"
        >
          <Icon name="close" size={16} />
        </button>
      )}
    </div>
  );
}
