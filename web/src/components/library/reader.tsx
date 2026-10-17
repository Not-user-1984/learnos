"use client";

/** Читалка главы: полная глава как e-book, выбор фрагмента → обсуждение с агентом. */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AArrowDown, AArrowUp, ChevronLeft, ChevronRight, History, Loader2, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import type { ConversationItem } from "@/lib/types";
import { api, apiPost } from "@/lib/api";
import { MODE_LABEL } from "@/lib/format";
import { Markdown } from "@/components/markdown/Markdown";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type Props = {
  sourceUid: string;
  sourceTitle: string;
  chapter: { idx: number; title: string; summary: string | null };
  text: string;
  prevIdx: number | null;
  nextIdx: number | null;
};

const FONT_KEY = "learnos-reader-font";
const FONT_EVENT = "learnos-reader-font-change";

function clampFont(v: number): number {
  return Math.min(1.4, Math.max(0.85, Math.round(v * 100) / 100));
}

/** Размер шрифта из localStorage без setState-в-эффекте: подписка на событие изменения. */
function useReaderFont(): [number, (delta: number) => void] {
  const scale = useSyncExternalStore(
    (cb) => {
      window.addEventListener(FONT_EVENT, cb);
      return () => window.removeEventListener(FONT_EVENT, cb);
    },
    () => Number(localStorage.getItem(FONT_KEY) ?? "1") || 1,
    () => 1,
  );
  const change = (delta: number) => {
    localStorage.setItem(FONT_KEY, String(clampFont(scale + delta)));
    window.dispatchEvent(new Event(FONT_EVENT));
  };
  return [scale, change];
}

export function ChapterReader({ sourceUid, sourceTitle, chapter, text, prevIdx, nextIdx }: Props) {
  const router = useRouter();
  const [fontScale, changeFont] = useReaderFont();
  const [selection, setSelection] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<ConversationItem[] | null>(null);
  const selTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openHistory = async () => {
    setHistoryOpen(true);
    setHistory(null);
    try {
      const items = await api<ConversationItem[]>(
        `/conversations?source=${encodeURIComponent(sourceUid)}&chapter=${chapter.idx}`,
      );
      setHistory(items);
    } catch {
      setHistory([]);
      toast.error("не удалось загрузить историю");
    }
  };

  useEffect(() => {
    const onSelectionChange = () => {
      if (selTimer.current) clearTimeout(selTimer.current);
      selTimer.current = setTimeout(() => {
        const sel = window.getSelection()?.toString().trim() ?? "";
        setSelection(sel.length > 30 ? sel.slice(0, 1200) : null);
      }, 250);
    };
    document.addEventListener("selectionchange", onSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", onSelectionChange);
      if (selTimer.current) clearTimeout(selTimer.current);
    };
  }, []);

  const startDiscussion = async (quote: string | null) => {
    setStarting(true);
    try {
      const act = await apiPost<{ uid: string }>("/activities", { source: sourceUid });
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode: "quick",
        activity: act.uid,
        chapter: chapter.idx,
        title: quote ? `Фрагмент: ${chapter.title}` : `Разбор: ${chapter.title}`,
      });
      const initial = quote
        ? `Разбери этот фрагмент главы «${chapter.title}»:\n\n> ${quote.replace(/\n/g, "\n> ")}`
        : `Разбери главу «${chapter.title}» кратко: главное и ключевые понятия.`;
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(initial)}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось открыть обсуждение");
      setStarting(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
        <Link href={`/library/${sourceUid}`} className="flex min-w-0 items-center gap-1 text-sm text-violet-500 hover:underline">
          <ChevronLeft className="h-4 w-4 shrink-0" />
          <span className="truncate">{sourceTitle}</span>
        </Link>
        <span className="ml-auto hidden text-sm text-muted-foreground sm:block">
          Глава {chapter.idx}
        </span>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Меньше шрифт" onClick={() => changeFont(-0.05)}>
            <AArrowDown className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Больше шрифт" onClick={() => changeFont(0.05)}>
            <AArrowUp className="h-4 w-4" />
          </Button>
          <Button size="sm" variant="outline" onClick={() => void openHistory()}>
            <History className="mr-1 h-4 w-4" /> История
          </Button>
          <Button size="sm" variant="outline" disabled={starting} onClick={() => void startDiscussion(null)}>
            {starting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-1 h-4 w-4" />}
            Обсудить главу
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <article
          className="mx-auto max-w-2xl px-6 py-10 sm:px-8"
          style={{ fontSize: `${fontScale}rem`, lineHeight: 1.8 }}
        >
          <h1 className="mb-3 text-2xl font-bold leading-tight">
            {chapter.idx}. {chapter.title}
          </h1>
          {chapter.summary && (
            <p className="mb-8 border-l-2 border-violet-400 pl-4 text-muted-foreground">{chapter.summary}</p>
          )}
          <Markdown content={text} />
        </article>

        <nav className="mx-auto flex max-w-2xl items-center justify-between border-t px-6 py-5 sm:px-8">
          {prevIdx ? (
            <Link href={`/library/${sourceUid}/${prevIdx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
              <ChevronLeft className="h-4 w-4" /> Глава {prevIdx}
            </Link>
          ) : (
            <span />
          )}
          {nextIdx && (
            <Link href={`/library/${sourceUid}/${nextIdx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
              Глава {nextIdx} <ChevronRight className="h-4 w-4" />
            </Link>
          )}
        </nav>
      </div>

      {selection && (
        <div className="pointer-events-none fixed inset-x-0 bottom-24 z-20 flex justify-center px-4">
          <div className="pointer-events-auto flex max-w-2xl items-center gap-3 rounded-2xl border bg-card p-3 shadow-lg">
            <p className="line-clamp-2 flex-1 text-xs text-muted-foreground">«{selection.slice(0, 140)}…»</p>
            <Button size="sm" disabled={starting} onClick={() => void startDiscussion(selection)}>
              {starting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-1 h-4 w-4" />}
              Обсудить выделенное
            </Button>
          </div>
        </div>
      )}

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[80dvh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>История: глава {chapter.idx}</DialogTitle>
          </DialogHeader>
          {history === null && (
            <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> ищу разговоры по этой главе…
            </p>
          )}
          {history !== null && history.length === 0 && (
            <p className="py-6 text-sm text-muted-foreground">
              По этой главе ещё не было разговоров — начни первым кнопкой «Обсудить главу».
            </p>
          )}
          <div className="flex flex-col gap-2">
            {(history ?? []).map((c) => (
              <Link
                key={c.uid}
                href={`/chat/${c.uid}`}
                className="flex items-center gap-3 rounded-xl border px-4 py-3 transition hover:border-violet-500/50 hover:bg-accent"
                onClick={() => setHistoryOpen(false)}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.title}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {MODE_LABEL[c.mode] ?? c.mode} · {new Date(c.updated_at).toLocaleString("ru-RU", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    {c.messages_count ? ` · ${c.messages_count} сообщ.` : ""}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </Link>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
