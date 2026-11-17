"use client";

/** Повторения (B-014): карточки-суть — «Показать ответ» → «Не помню / Трудно / Помню»
 *  без LLM; блоки без карточек и режим «объясни своими словами» — через чат, как раньше.
 *  ?source= — набор по книге («Закрепить книгу» со страницы источника). */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import type { ReviewQueueItem } from "@/lib/types";
import { Button } from "@/components/ui/button";

type Stats = { due_today: number; overdue: number; total: number };

const GRADES: { grade: "again" | "hard" | "good"; label: string; icon: string; cls: string }[] = [
  { grade: "again", label: "Не помню", icon: "close", cls: "border-destructive/40 text-destructive hover:bg-destructive/10" },
  { grade: "hard", label: "Трудно", icon: "priority_high", cls: "border-amber-500/40 text-amber-600 hover:bg-amber-500/10 dark:text-amber-400" },
  { grade: "good", label: "Помню", icon: "check", cls: "border-emerald-500/40 text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400" },
];

export default function ReviewPage() {
  return (
    <Suspense fallback={null}>
      <ReviewInner />
    </Suspense>
  );
}

function ReviewInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const source = searchParams.get("source");
  const sourceTitle = searchParams.get("title");

  const [queue, setQueue] = useState<ReviewQueueItem[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [busyUid, setBusyUid] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<string | null>(null);

  const reload = useCallback(() => {
    const q = source ? `&source=${encodeURIComponent(source)}` : "";
    api<ReviewQueueItem[]>(`/review/queue?limit=20${q}`).then(setQueue).catch(() => setQueue([]));
    api<Stats>(`/review/stats${source ? `?source=${encodeURIComponent(source)}` : ""}`)
      .then(setStats)
      .catch(() => setStats(null));
  }, [source]);

  useEffect(() => {
    reload();
  }, [reload]);

  const next = () => {
    setRevealed(null);
    reload();
  };

  const answerCard = async (item: ReviewQueueItem, grade: "again" | "hard" | "good") => {
    const key = `${item.block_uid}:${item.card_id}`;
    setBusyUid(key);
    try {
      await apiPost("/review/answer-card", {
        block_uid: item.block_uid,
        card_id: item.card_id,
        grade,
      });
      toast.success(
        grade === "again" ? "Вернётся завтра" : grade === "hard" ? "Интервал подрос" : "Отлично, интервал вырос",
      );
      next();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusyUid(null);
    }
  };

  const repeatInChat = async (blockUid: string, title: string) => {
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
        {source && (
          <p className="mt-1 inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-sm text-primary">
            <Icon name="auto_stories" size={14} />
            {sourceTitle ?? "набор по источнику"}
            <Link href="/review" className="ml-1 text-muted-foreground hover:text-foreground" title="Вся база">
              <Icon name="close" size={14} />
            </Link>
          </p>
        )}
      </header>

      {queue === null ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="progress_activity" size={15} className="animate-spin" /> загружаю очередь…
        </p>
      ) : queue.length === 0 ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Назревших повторений нет — новые появляются сами после сессий и записанных глав (на следующий день).
        </p>
      ) : (
        <ul className="flex max-w-3xl flex-col gap-2">
          {queue.map((item) => {
            const key = `${item.block_uid}:${item.card_id ?? "block"}`;
            const isCard = item.kind === "card" && item.q && item.a;
            const open = revealed === key;
            return (
              <li key={key} className="rounded-xl border bg-card p-4">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <Link href={`/kb/${item.block_uid}`} className="min-w-0 truncate font-medium text-foreground hover:underline">
                    {item.title}
                  </Link>
                  {isCard && (
                    <span className="rounded-full border px-1.5">карточка</span>
                  )}
                  <span>
                    назрело:{" "}
                    {new Date(item.due_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    {" · "}интервал {item.interval_days} дн.
                    {item.weak_spots_count > 0 ? ` · слабых мест: ${item.weak_spots_count}` : ""}
                  </span>
                </div>

                {isCard ? (
                  <div className="mt-2">
                    <p className="font-medium">{item.q}</p>
                    {open ? (
                      <>
                        <p className="mt-2 rounded-lg bg-muted px-3 py-2 text-sm">{item.a}</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {GRADES.map((g) => (
                            <Button
                              key={g.grade}
                              size="sm"
                              variant="outline"
                              className={g.cls}
                              disabled={busyUid !== null}
                              onClick={() => void answerCard(item, g.grade)}
                            >
                              <Icon name={g.icon} size={15} /> {g.label}
                            </Button>
                          ))}
                        </div>
                      </>
                    ) : (
                      <Button size="sm" variant="outline" className="mt-2" onClick={() => setRevealed(key)}>
                        <Icon name="visibility" size={15} /> Показать ответ
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <p className="min-w-0 flex-1 text-sm text-muted-foreground">
                      Проговорить блок своими словами — оценит нейронка.
                    </p>
                    <Button size="sm" disabled={busyUid !== null} onClick={() => void repeatInChat(item.block_uid, item.title)}>
                      {busyUid === item.block_uid ? (
                        <Icon name="progress_activity" size={15} className="mr-1 animate-spin" />
                      ) : (
                        <Icon name="replay" size={15} className="mr-1" />
                      )}
                      Повторить
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
