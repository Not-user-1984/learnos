"use client";

/** Действия на странице источника: активность/разбор/сессия/чтение. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function SourceActions({ sourceUid, chapterIdx, chapterTitle }: { sourceUid: string; chapterIdx?: number; chapterTitle?: string }) {
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
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void start("quick")}>
        ⚡ Быстрый разбор{chapterIdx ? ` гл. ${chapterIdx}` : ""}
      </Button>
      <Button size="sm" disabled={busy !== null} onClick={() => void start("session")}>
        🎓 Сессия{chapterIdx ? ` по гл. ${chapterIdx}` : ""}
      </Button>
    </div>
  );
}
