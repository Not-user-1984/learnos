"use client";

/** Действия на странице источника: разбор/сессия (до lg — иконки без текста). */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { GraduationCap, Zap } from "lucide-react";
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

  const start = async (mode: "quick" | "session") => {
    setBusy(mode);
    try {
      const act = await apiPost<{ uid: string }>("/activities", { source: sourceUid });
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode,
        activity: act.uid,
        chapter: chapterIdx ?? null,
        title: chapterTitle ? `${mode === "quick" ? "Разбор" : "Сессия"}: ${chapterTitle}` : undefined,
      });
      const first =
        mode === "session"
          ? `Начни сессию${chapterIdx ? ` по главе ${chapterIdx}` : ""}: теория по первым понятиям, коротко.`
          : `Начнём быстрый разбор${chapterIdx ? ` главы ${chapterIdx}` : ""}: главное и ключевые понятия.`;
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(first)}`);
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
        onClick={() => void start("quick")}
      >
        <Zap className="h-4 w-4 text-amber-500" />
        <span className="hidden lg:inline">Быстрый разбор</span>
      </Button>
      <Button
        size="sm"
        disabled={busy !== null}
        title={chapterIdx ? `Сессия по главе ${chapterIdx}` : "Сессия по источнику"}
        onClick={() => void start("session")}
      >
        <GraduationCap className="h-4 w-4" />
        <span className="hidden lg:inline">Сессия</span>
      </Button>
    </div>
  );
}
