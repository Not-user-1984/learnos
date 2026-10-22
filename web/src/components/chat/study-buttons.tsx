"use client";

/** Кнопки запуска сценариев изучения: книга / видео / ресёрч / свободный разговор.
 *  Ресёрч — не отдельный режим и не вкладка: карточка спрашивает тему и открывает
 *  обычный чат, где первое сообщение (тема) запускает ресёрч-цикл агента. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPost } from "@/lib/api";
import { StudyFlowDialog } from "@/components/chat/study-flow";
import { NewConversationButton } from "@/components/chat/new-conversation";

type Tab = "book" | "video";

/** Тема → free-чат с research-запуском: служебная директива уйдёт агенту в
 *  system_extra, в чате видно только сообщение пользователя с темой. */
function useResearchStart() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const start = async (topic: string) => {
    if (!topic.trim() || busy) return;
    setBusy(true);
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode: "free",
        title: `Ресёрч: ${topic.trim().slice(0, 60)}`,
      });
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(topic.trim())}&research=1`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось начать ресёрч");
      setBusy(false);
    }
  };
  return { busy, start };
}

/** Поле ввода темы + кнопка «найти». */
function ResearchTopicInput({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  return (
    <div className="flex w-full items-center gap-2">
      <Input
        autoFocus
        placeholder="Например: observability в Kubernetes для начинающих"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit()}
      />
      <Button aria-label="Начать ресёрч" disabled={busy || !value.trim()} onClick={onSubmit}>
        {busy ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="search" size={16} />}
      </Button>
    </div>
  );
}

export function StudyButtons({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("book");
  const [asking, setAsking] = useState(false);
  const [topic, setTopic] = useState("");
  const research = useResearchStart();

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
          <Icon name="auto_stories" size={16} /> Изучить книгу
        </Button>
        <Button
          size={compact ? "sm" : "default"}
          variant="outline"
          onClick={() => {
            setTab("video");
            setOpen(true);
          }}
        >
          <Icon name="movie" size={16} /> Обсудить видео
        </Button>
        <Button size={compact ? "sm" : "default"} variant="outline" onClick={() => setAsking((v) => !v)}>
          <Icon name="public" size={16} className="text-emerald-500" /> Ресёрч темы
        </Button>
        <NewConversationButton />
      </div>
      {asking && (
        <div className="mt-2 max-w-md">
          <ResearchTopicInput
            value={topic}
            onChange={setTopic}
            onSubmit={() => void research.start(topic)}
            busy={research.busy}
          />
        </div>
      )}
      <StudyFlowDialog open={open} onOpenChange={setOpen} defaultTab={tab} />
    </>
  );
}

/** Пустое состояние чата: три больших сценария + свободный чат. */
export function StudyEmptyState() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("book");
  const [asking, setAsking] = useState(false);
  const [topic, setTopic] = useState("");
  const research = useResearchStart();

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
          <Icon name="auto_stories" size={32} className="text-violet-500" />
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
          <Icon name="movie" size={32} className="text-rose-500" />
          <p className="font-semibold">Обсудить видео</p>
          <p className="text-sm text-muted-foreground">
            Вставь ссылку на YouTube — транскрипт обработается, и агент готов разбирать видео по частям.
          </p>
        </button>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => setAsking(true)}
            className="group flex flex-1 flex-col gap-2 rounded-2xl border bg-card p-6 text-left transition hover:border-emerald-500/60"
          >
            <Icon name="public" size={32} className="text-emerald-500" />
            <p className="font-semibold">Ресёрч темы</p>
            <p className="text-sm text-muted-foreground">
              Опиши тему — агент обойдёт сеть (доки, статьи, видео) и добавит лучшее в Библиотеку.
            </p>
          </button>
          {asking && (
            <ResearchTopicInput
              value={topic}
              onChange={setTopic}
              onSubmit={() => void research.start(topic)}
              busy={research.busy}
            />
          )}
        </div>
      </div>
      <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon name="chat" size={14} /> Нужен просто вопрос без источника — «Новый разговор» сверху
      </p>
      <StudyFlowDialog open={open} onOpenChange={setOpen} defaultTab={tab} />
    </>
  );
}
