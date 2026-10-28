"use client";

/** Действия на странице источника: разбор/сессия (до lg — иконки без текста).
 *  Разговор всегда root: сценарий уходит серверу интентом (review/session),
 *  сессию по интенту сервер создаёт сам и привязывает к разговору. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SourceActions({
  sourceUid,
  chapterIdx,
  chapterTitle,
  className,
}: {
  sourceUid: string;
  chapterIdx?: number;
  chapterTitle?: string;
  className?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  const start = async (intent: "review" | "session") => {
    setBusy(intent);
    try {
      const act = await apiPost<{ uid: string }>("/activities", { source: sourceUid });
      const conv = await apiPost<{ uid: string }>("/conversations", {
        activity: act.uid,
        chapter: chapterIdx ?? null,
        title: chapterTitle ? `${intent === "session" ? "Сессия" : "Разбор"}: ${chapterTitle}` : undefined,
      });
      const first =
        intent === "session"
          ? `Начнём сессию${chapterIdx ? ` по главе ${chapterIdx}` : ""}`
          : `Начнём быстрый разбор${chapterIdx ? ` главы ${chapterIdx}` : ""}`;
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(first)}&intent=${intent}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={cn("flex shrink-0 flex-wrap items-center gap-2", className)}>
      <Button
        size="sm"
        variant="outline"
        disabled={busy !== null}
        title={chapterIdx ? `Быстрый разбор главы ${chapterIdx}` : "Быстрый разбор источника"}
        onClick={() => void start("review")}
      >
        {busy === "review" ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="bolt" size={16} className="text-amber-500" />}
        <span className="hidden lg:inline">Быстрый разбор</span>
      </Button>
      <Button
        size="sm"
        disabled={busy !== null}
        title={chapterIdx ? `Сессия по главе ${chapterIdx}` : "Сессия по источнику"}
        onClick={() => void start("session")}
      >
        {busy === "session" ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="school" size={16} />}
        <span className="hidden lg:inline">Сессия</span>
      </Button>
    </div>
  );
}
