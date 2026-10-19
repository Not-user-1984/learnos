"use client";

/** Читалка главы: e-book-режим — подглавы заголовками, выбор гарнитуры,
 *  выделение фрагмента → обсуждение или ресёрч в новой вкладке. */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AArrowDown, AArrowUp, ChevronLeft, ChevronRight, Loader2, MessageCircle, Search } from "lucide-react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { formatChapter } from "@/lib/reader-format";
import { Markdown } from "@/components/markdown/Markdown";
import { Button } from "@/components/ui/button";
import { ChapterHistoryButton } from "./chapter-history";

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
const FAMILY_KEY = "learnos-reader-family";
const FAMILY_EVENT = "learnos-reader-family-change";

const FAMILIES = [
  { value: "sans", label: "Обычный", css: "ui-sans-serif, system-ui, sans-serif" },
  { value: "serif", label: "Книжный", css: "Georgia, 'Iowan Old Style', serif" },
  { value: "mono", label: "Моно", css: "ui-monospace, 'SF Mono', Menlo, monospace" },
];

function clampFont(v: number): number {
  return Math.min(1.4, Math.max(0.85, Math.round(v * 100) / 100));
}

/** Значение из localStorage без setState-в-эффекте: подписка на событие изменения. */
function useStored(key: string, event: string, fallback: string): [string, (v: string) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      window.addEventListener(event, cb);
      return () => window.removeEventListener(event, cb);
    },
    () => localStorage.getItem(key) ?? fallback,
    () => fallback,
  );
  const set = (v: string) => {
    localStorage.setItem(key, v);
    window.dispatchEvent(new Event(event));
  };
  return [value, set];
}

function useReaderFont(): [number, (delta: number) => void] {
  const scale = Number(useStored(FONT_KEY, FONT_EVENT, "1")[0]) || 1;
  const change = (delta: number) => {
    localStorage.setItem(FONT_KEY, String(clampFont(scale + delta)));
    window.dispatchEvent(new Event(FONT_EVENT));
  };
  return [scale, change];
}

export function ChapterReader({ sourceUid, sourceTitle, chapter, text, prevIdx, nextIdx }: Props) {
  const router = useRouter();
  const [fontScale, changeFont] = useReaderFont();
  const [family, setFamily] = useStored(FAMILY_KEY, FAMILY_EVENT, "sans");
  const [selection, setSelection] = useState<string | null>(null);
  const [starting, setStarting] = useState<"chat" | "research" | null>(null);
  const selTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const familyCss = FAMILIES.find((f) => f.value === family)?.css ?? FAMILIES[0].css;

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

  const openDiscussion = async (quote: string | null) => {
    setStarting("chat");
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
      setStarting(null);
    }
  };

  /** Ресёрч по выделенному фрагменту — в новой вкладке, чтобы читалка осталась открытой. */
  const researchSelection = async (quote: string) => {
    setStarting("research");
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode: "free",
        title: `Ресёрч: ${quote.slice(0, 50)}`,
      });
      const url = `/chat/${conv.uid}?initial=${encodeURIComponent(quote)}&research=1`;
      window.open(url, "_blank");
      toast.info("ресёрч открыт в новой вкладке");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось начать ресёрч");
    } finally {
      setStarting(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/95 px-3 backdrop-blur sm:px-4">
        <Link href={`/library/${sourceUid}`} className="flex min-w-0 items-center gap-1 text-sm text-violet-500 hover:underline">
          <ChevronLeft className="h-4 w-4 shrink-0" />
          <span className="truncate">{sourceTitle}</span>
        </Link>
        <span className="ml-auto hidden text-sm text-muted-foreground sm:block">Глава {chapter.idx}</span>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Меньше шрифт" onClick={() => changeFont(-0.05)}>
            <AArrowDown className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Больше шрифт" onClick={() => changeFont(0.05)}>
            <AArrowUp className="h-4 w-4" />
          </Button>
          <select
            aria-label="Гарнитура"
            value={family}
            onChange={(e) => setFamily(e.target.value)}
            className="h-8 rounded-md border bg-background px-1.5 text-xs"
          >
            {FAMILIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <ChapterHistoryButton sourceUid={sourceUid} chapterIdx={chapter.idx} chapterTitle={chapter.title} />
          <Button size="sm" variant="outline" disabled={starting !== null} onClick={() => void openDiscussion(null)}>
            {starting === "chat" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-1 h-4 w-4" />}
            <span className="hidden sm:inline">Обсудить главу</span>
            <span className="sm:hidden">Чат</span>
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <article
          className="mx-auto max-w-2xl px-5 py-8 sm:px-8 sm:py-10"
          style={{ fontSize: `${fontScale}rem`, lineHeight: 1.8, fontFamily: familyCss }}
        >
          <h1 className="mb-3 text-2xl font-bold leading-tight">
            {chapter.idx}. {chapter.title}
          </h1>
          {chapter.summary && (
            <p className="mb-8 border-l-2 border-violet-400 pl-4 text-muted-foreground">{chapter.summary}</p>
          )}
          <Markdown content={formatChapter(text, chapter.title)} />
        </article>

        <nav className="mx-auto flex max-w-2xl items-center justify-between border-t px-5 py-5 sm:px-8">
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
          <div className="pointer-events-auto flex max-w-2xl flex-wrap items-center gap-2 rounded-2xl border bg-card p-3 shadow-lg">
            <p className="line-clamp-2 min-w-0 flex-1 text-xs text-muted-foreground">«{selection.slice(0, 140)}…»</p>
            <Button size="sm" disabled={starting !== null} onClick={() => void openDiscussion(selection)}>
              {starting === "chat" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <MessageCircle className="mr-1 h-4 w-4" />}
              Обсудить
            </Button>
            <Button size="sm" variant="outline" disabled={starting !== null} onClick={() => void researchSelection(selection)}>
              {starting === "research" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
              Ресёрч
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
