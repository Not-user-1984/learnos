"use client";

/** Повторения: очередь на сегодня, кнопка «Повторить» открывает чат по блоку (B-005). */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import type { ReviewQueueItem } from "@/lib/types";
import { Button } from "@/components/ui/button";

type Stats = { due_today: number; overdue: number; total: number };

export default function ReviewPage() {
  const router = useRouter();
  const [queue, setQueue] = useState<ReviewQueueItem[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busyUid, setBusyUid] = useState<string | null>(null);

  useEffect(() => {
    api<ReviewQueueItem[]>("/review/queue?limit=20").then(setQueue).catch(() => setQueue([]));
    api<Stats>("/review/stats").then(setStats).catch(() => setStats(null));
  }, []);

  const repeat = async (blockUid: string, title: string) => {
    if (busyUid) return;
    setBusyUid(blockUid);
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {});
      const params = new URLSearchParams({
        initial: `Повторение блока «${title}» (${blockUid}): спроси по нему и оцени мой ответ (answer_review).`,
        intent: "reinforce",
      });
      router.push(`/chat/${conv.uid}?${params.toString()}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать разговор");
      setBusyUid(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <header className="mb-5">
        <h1 className="text-xl font-bold">Повторения</h1>
        <p className="text-sm text-muted-foreground">
          {stats
            ? `назревших сегодня: ${stats.due_today} · просрочено: ${stats.overdue} · всего в ротации: ${stats.total}`
            : "…"}
        </p>
      </header>

      {queue === null ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="progress_activity" size={15} className="animate-spin" /> загружаю очередь…
        </p>
      ) : queue.length === 0 ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Назревших повторений нет — новые появляются сами после каждой сессии-урока (на следующий день).
        </p>
      ) : (
        <ul className="flex max-w-3xl flex-col gap-2">
          {queue.map((item) => (
            <li key={item.block_uid} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4">
              <div className="min-w-0 flex-1">
                <Link href={`/kb/${item.block_uid}`} className="truncate font-medium hover:underline">
                  {item.title}
                </Link>
                <p className="text-xs text-muted-foreground">
                  назрело: {new Date(item.due_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                  {" · "}интервал {item.interval_days} дн.
                  {item.weak_spots_count > 0 ? ` · слабых мест: ${item.weak_spots_count}` : ""}
                </p>
              </div>
              <Button size="sm" disabled={busyUid !== null} onClick={() => void repeat(item.block_uid, item.title)}>
                {busyUid === item.block_uid ? (
                  <Icon name="progress_activity" size={15} className="mr-1 animate-spin" />
                ) : (
                  <Icon name="replay" size={15} className="mr-1" />
                )}
                Повторить
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
