"use client";

/** Кнопки запуска сценариев изучения: книга / видео / ресёрч / свободный разговор. */

import { useState } from "react";
import { BookOpen, Globe, MessageSquare, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StudyFlowDialog } from "@/components/chat/study-flow";
import { NewConversationButton } from "@/components/chat/new-conversation";

type Tab = "book" | "video" | "research";

export function StudyButtons({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("book");

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size={compact ? "sm" : "default"}
          onClick={() => {
            setTab("book");
            setOpen(true);
          }}
        >
          <BookOpen className="h-4 w-4" /> Изучить книгу
        </Button>
        <Button
          size={compact ? "sm" : "default"}
          variant="outline"
          onClick={() => {
            setTab("video");
            setOpen(true);
          }}
        >
          <Video className="h-4 w-4" /> Обсудить видео
        </Button>
        <Button
          size={compact ? "sm" : "default"}
          variant="outline"
          onClick={() => {
            setTab("research");
            setOpen(true);
          }}
        >
          <Globe className="h-4 w-4" /> Ресёрч темы
        </Button>
        <NewConversationButton />
      </div>
      <StudyFlowDialog open={open} onOpenChange={setOpen} defaultTab={tab} />
    </>
  );
}

/** Пустое состояние чата: три больших сценария + свободный чат. */
export function StudyEmptyState() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("book");

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <button
          onClick={() => {
            setTab("book");
            setOpen(true);
          }}
          className="group flex flex-col gap-2 rounded-2xl border bg-card p-6 text-left transition hover:border-violet-500/60"
        >
          <BookOpen className="h-8 w-8 text-violet-500" />
          <p className="font-semibold">Изучить книгу</p>
          <p className="text-sm text-muted-foreground">
            Загрузи PDF — нейронка разобьёт на главы, построит карту изучения и проведёт по ней блок за блоком.
          </p>
        </button>
        <button
          onClick={() => {
            setTab("video");
            setOpen(true);
          }}
          className="group flex flex-col gap-2 rounded-2xl border bg-card p-6 text-left transition hover:border-violet-500/60"
        >
          <Video className="h-8 w-8 text-rose-500" />
          <p className="font-semibold">Обсудить видео</p>
          <p className="text-sm text-muted-foreground">
            Вставь ссылку на YouTube — транскрипт обработается, и агент готов разбирать видео по частям.
          </p>
        </button>
        <button
          onClick={() => {
            setTab("research");
            setOpen(true);
          }}
          className="group flex flex-col gap-2 rounded-2xl border bg-card p-6 text-left transition hover:border-emerald-500/60"
        >
          <Globe className="h-8 w-8 text-emerald-500" />
          <p className="font-semibold">Ресёрч темы</p>
          <p className="text-sm text-muted-foreground">
            Опиши тему — агент обойдёт сеть (доки, статьи, видео), покажет лучших кандидатов и добавит топ в Библиотеку.
          </p>
        </button>
      </div>
      <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
        <MessageSquare className="h-3.5 w-3.5" /> Нужен просто вопрос без источника — «Новый разговор» сверху
      </p>
      <StudyFlowDialog open={open} onOpenChange={setOpen} defaultTab={tab} />
    </>
  );
}
