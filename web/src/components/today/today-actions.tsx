"use client";

/** Действия дашборда «Сегодня»: старт сессии по элементу курса, переходы (B-005). */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";

/** «Начать сессию» по элементу курса: сервер создаёт разговор + сессию (B-004/B-005). */
export function StartItemButton({
  courseUid,
  itemId,
  label = "Начать сессию",
  className,
}: {
  courseUid: string;
  itemId: number;
  label?: string;
  className?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const start = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const out = await apiPost<{ conversation_uid: string }>(`/courses/${courseUid}/items/${itemId}/start`, {});
      const params = new URLSearchParams({
        initial: "Начинаем урок по этому элементу курса.",
        intent: "session",
      });
      router.push(`/chat/${out.conversation_uid}?${params.toString()}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось начать сессию");
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={() => void start()}
      disabled={busy}
      className={
        className ??
        "inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
      }
    >
      {busy ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="play_circle" size={16} />}
      {label}
    </button>
  );
}

/** «Прочитал сам»: глава закрыта без сессии — элемент станет read (B-004). */
export function MarkReadButton({
  sourceUid,
  chapter,
  onDone,
  className,
}: {
  sourceUid: string;
  chapter: number | null;
  onDone?: () => void;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const mark = async () => {
    if (busy || done || chapter === null) return;
    setBusy(true);
    try {
      await apiPost("/activities/mark-read", { source: sourceUid, chapter });
      setDone(true);
      toast.success(`Глава ${chapter} отмечена прочитанной`);
      onDone?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось отметить главу");
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      type="button"
      onClick={() => void mark()}
      disabled={busy || done || chapter === null}
      className={
        className ??
        "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition hover:bg-accent disabled:opacity-60"
      }
    >
      {busy ? (
        <Icon name="progress_activity" size={16} className="animate-spin" />
      ) : (
        <Icon name={done ? "check" : "menu_book"} size={16} />
      )}
      {done ? "Прочитано" : "Прочитал сам"}
    </button>
  );
}
