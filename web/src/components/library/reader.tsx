"use client";

/** Читалка главы: e-book-режим — подглавы заголовками, выбор гарнитуры,
 *  выделение фрагмента → обсуждение или ресёрч в новой вкладке.
 *  Для книг — режим «чистый PDF»: встроенный просмотрщик с оригинальной вёрсткой. */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { formatChapter } from "@/lib/reader-format";
import { useStored } from "@/lib/use-stored";
import { Markdown } from "@/components/markdown/Markdown";
import { Button } from "@/components/ui/button";
import { ChapterHistoryButton } from "./chapter-history";
import { PdfViewer } from "./pdf-viewer";

type Props = {
  sourceUid: string;
  sourceTitle: string;
  chapter: { idx: number; title: string; summary: string | null; number?: number | null };
  text: string;
  prevIdx: number | null;
  nextIdx: number | null;
  /** У источника есть PDF-оригинал (kind=book) — доступен режим «чистый PDF». */
  isBook?: boolean;
  /** Режим из URL (?mode=pdf) — применяется один раз при монтировании. */
  initialMode?: string | null;
  /** Прогресс книги по активной активности (null — у материала одна глава, кнопка «Прочитал» не нужна). */
  progress?: { cursor: number; total: number } | null;
  /** Split-view (B-006): обсудить главу/цитату в панели рядом, без ухода на /chat. */
  onDiscuss?: (text: string) => void;
};

const FONT_KEY = "learnos-reader-font";
const FONT_EVENT = "learnos-reader-font-change";
const FAMILY_KEY = "learnos-reader-family";
const FAMILY_EVENT = "learnos-reader-family-change";
const MODE_KEY = "learnos-reader-mode";
const MODE_EVENT = "learnos-reader-mode-change";

const FAMILIES = [
  { value: "sans", label: "Обычный", css: "ui-sans-serif, system-ui, sans-serif" },
  { value: "serif", label: "Книжный", css: "var(--font-serif), Georgia, 'Iowan Old Style', serif" },
  { value: "mono", label: "Моно", css: "ui-monospace, 'SF Mono', Menlo, monospace" },
];

function clampFont(v: number): number {
  return Math.min(1.4, Math.max(0.85, Math.round(v * 100) / 100));
}

function useReaderFont(): [number, (delta: number) => void] {
  const scale = Number(useStored(FONT_KEY, FONT_EVENT, "1")[0]) || 1;
  const change = (delta: number) => {
    localStorage.setItem(FONT_KEY, String(clampFont(scale + delta)));
    window.dispatchEvent(new Event(FONT_EVENT));
  };
  return [scale, change];
}

export function ChapterReader({
  sourceUid,
  sourceTitle,
  chapter,
  text,
  prevIdx,
  nextIdx,
  isBook = false,
  initialMode = null,
  progress = null,
  onDiscuss,
}: Props) {
  const router = useRouter();
  const [fontScale, changeFont] = useReaderFont();
  const [family, setFamily] = useStored(FAMILY_KEY, FAMILY_EVENT, "sans");
  const [modeRaw, setMode] = useStored(MODE_KEY, MODE_EVENT, "text");
  const mode = isBook && modeRaw === "pdf" ? "pdf" : "text";
  const [pages, setPages] = useState<Record<string, number> | null>(null);
  const [visiblePage, setVisiblePage] = useState<number | null>(null);
  const [selection, setSelection] = useState<string | null>(null);
  const [starting, setStarting] = useState<"chat" | "research" | null>(null);
  // курсор книги монотонен: сервер — источник истины, локально помним только свою отметку
  const [localCursor, setLocalCursor] = useState<number | null>(null);
  const [marking, setMarking] = useState(false);
  const selTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const familyCss = FAMILIES.find((f) => f.value === family)?.css ?? FAMILIES[0].css;
  const serverCursor = progress?.cursor ?? null;
  const readCursor =
    localCursor !== null && serverCursor !== null
      ? Math.max(serverCursor, localCursor)
      : (localCursor ?? serverCursor);
  const chapterRead = readCursor !== null && chapter.idx < readCursor;

  // ссылка «открыть PDF» ведёт в режим pdf (запоминаем выбор)
  useEffect(() => {
    if (initialMode === "pdf" && isBook) setMode("pdf");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // страницы глав по закладкам PDF — один запрос на сессию читалки
  useEffect(() => {
    if (mode !== "pdf" || pages !== null) return;
    fetch(`/api/sources/${sourceUid}/outline`)
      .then((r) => (r.ok ? r.json() : { pages: {} }))
      .then((body: { pages?: Record<string, number> }) => setPages(body.pages ?? {}))
      .catch(() => setPages({}));
  }, [mode, pages, sourceUid]);

  const pdfPage = pages?.[String(chapter.idx)] ?? 1;

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
    // split-view (B-006): обсуждение живёт в панели рядом — цитата уходит в композер
    if (onDiscuss) {
      onDiscuss(
        quote
          ? `Разбери фрагмент главы «${chapter.title}»:\n\n${quote}`
          : `Разберём главу «${chapter.title}»`,
      );
      return;
    }
    setStarting("chat");
    try {
      const act = await apiPost<{ uid: string }>("/activities", { source: sourceUid });
      const conv = await apiPost<{ uid: string }>("/conversations", {
        activity: act.uid,
        chapter: chapter.idx,
        title: quote ? `Фрагмент: ${chapter.title}` : `Разбор: ${chapter.title}`,
      });
      // видимое сообщение — цитата или короткое намерение; сценарий (quote/review)
      // сервер превращает в директиву агенту
      const initial = quote ?? `Разберём главу «${chapter.title}»`;
      const intent = quote ? "quote" : "review";
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(initial)}&intent=${intent}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось открыть обсуждение");
      setStarting(null);
    }
  };

  /** «Прочитал сам»: глава идёт в прогресс книги без разбора агентом (идемпотентно, разговор не создаётся). */
  const markRead = async () => {
    setMarking(true);
    try {
      const out = await apiPost<{ cursor_chapter: number; total_chapters: number }>(
        "/activities/mark-read",
        { source: sourceUid, chapter: chapter.idx },
      );
      setLocalCursor(out.cursor_chapter);
      toast.success(
        `Глава ${chapter.idx} отмечена · прочитано ${Math.max(0, out.cursor_chapter - 1)} из ${out.total_chapters}`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось отметить главу");
    } finally {
      setMarking(false);
    }
  };

  /** Ресёрч по выделенному фрагменту — в новой вкладке, чтобы читалка осталась открытой. */
  const researchSelection = async (quote: string) => {    setStarting("research");
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {
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
        <Link href={`/library/${sourceUid}`} className="flex min-w-0 items-center gap-1 text-sm text-primary hover:underline">
          <Icon name="chevron_left" size={16} className="shrink-0" />
          <span className="truncate">{sourceTitle}</span>
        </Link>
        <span className="ml-auto hidden text-sm text-muted-foreground sm:block">
          {chapter.number ? `Глава ${chapter.number}` : `Глава ${chapter.idx}`}
        </span>
        <div className="flex items-center gap-1">
          {isBook && (
            <div
              className="flex items-center rounded-lg border bg-background p-0.5"
              role="tablist"
              aria-label="Режим чтения"
            >
              {(
                [
                  { value: "text", label: "Конспект", icon: "auto_stories" },
                  { value: "pdf", label: "PDF", icon: "picture_as_pdf" },
                ] as const
              ).map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="tab"
                  aria-selected={mode === m.value}
                  onClick={() => setMode(m.value)}
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs whitespace-nowrap transition-colors ${
                    mode === m.value
                      ? "bg-accent font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon name={m.icon} size={14} />
                  <span className="hidden sm:inline">{m.label}</span>
                </button>
              ))}
            </div>
          )}
          {mode === "text" && (
            <>
              <Button variant="ghost" size="icon" aria-label="Меньше шрифт" onClick={() => changeFont(-0.05)}>
                <Icon name="text_decrease" size={16} />
              </Button>
              <Button variant="ghost" size="icon" aria-label="Больше шрифт" onClick={() => changeFont(0.05)}>
                <Icon name="text_increase" size={16} />
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
            </>
          )}
          {mode === "pdf" && (
            <span className="hidden text-xs whitespace-nowrap text-muted-foreground lg:inline">
              PDF · глава {chapter.idx} · стр. {visiblePage ?? pdfPage}
            </span>
          )}
          <ChapterHistoryButton sourceUid={sourceUid} chapterIdx={chapter.idx} chapterTitle={chapter.title} />
          {progress && (
            <Button
              size="sm"
              variant="outline"
              disabled={marking || chapterRead}
              title={chapterRead ? "Глава уже учтена в прогрессе книги" : "Отметить главу прочитанной"}
              onClick={() => void markRead()}
            >
              {marking ? (
                <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
              ) : (
                <Icon name="task_alt" size={16} className={chapterRead ? "mr-1 text-primary" : "mr-1"} />
              )}
              <span className="hidden sm:inline">{chapterRead ? "Прочитано" : "Прочитал"}</span>
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={starting !== null} onClick={() => void openDiscussion(null)}>
            {starting === "chat" ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="chat_bubble" size={16} className="mr-1" />}
            <span className="hidden sm:inline">Обсудить главу</span>
            <span className="sm:hidden">Чат</span>
          </Button>
        </div>
      </header>

      {mode === "pdf" ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <PdfViewer
            url={`/api/sources/${sourceUid}/file`}
            page={pdfPage}
            onPageChange={setVisiblePage}
            openHref={`/library/${sourceUid}/read?ch=${chapter.idx}&page=${visiblePage ?? pdfPage}`}
            className="min-h-0"
          />
          <nav className="flex shrink-0 items-center justify-between border-t px-5 py-2.5">
            {prevIdx ? (
              <Link href={`/library/${sourceUid}/${prevIdx}?mode=pdf`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
                <Icon name="chevron_left" size={16} /> Глава {prevIdx}
              </Link>
            ) : (
              <span />
            )}
            <span className="text-xs text-muted-foreground">
              PDF · глава {chapter.idx} · стр. {visiblePage ?? pdfPage}
            </span>
            {nextIdx && (
              <Link href={`/library/${sourceUid}/${nextIdx}?mode=pdf`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
                Глава {nextIdx} <Icon name="chevron_right" size={16} />
              </Link>
            )}
          </nav>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <article
            className="mx-auto max-w-2xl px-5 py-8 sm:px-8 sm:py-10"
            style={{ fontSize: `${fontScale}rem`, lineHeight: 1.8, fontFamily: familyCss }}
          >
            <h1 className="mb-3 text-2xl font-bold leading-tight">
              {chapter.number ? `Глава ${chapter.number}. ` : `${chapter.idx}. `}
              {chapter.title.replace(/^\s*\d+[.)]?\s+/, "")}
            </h1>
            {chapter.summary && (
              <p className="mb-8 border-l-2 border-primary/50 pl-4 text-muted-foreground">{chapter.summary}</p>
            )}
            <Markdown content={formatChapter(text, chapter.title)} />
          </article>

          <nav className="mx-auto flex max-w-2xl items-center justify-between border-t px-5 py-5 sm:px-8">
            {prevIdx ? (
              <Link href={`/library/${sourceUid}/${prevIdx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
                <Icon name="chevron_left" size={16} /> Глава {prevIdx}
              </Link>
            ) : (
              <span />
            )}
            {nextIdx && (
              <Link href={`/library/${sourceUid}/${nextIdx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
                Глава {nextIdx} <Icon name="chevron_right" size={16} />
              </Link>
            )}
          </nav>
        </div>
      )}

      {selection && (
        <div className="pointer-events-none fixed inset-x-0 bottom-24 z-20 flex justify-center px-4">
          <div className="pointer-events-auto flex max-w-2xl flex-wrap items-center gap-2 rounded-2xl border bg-card p-3 shadow-lg">
            <p className="line-clamp-2 min-w-0 flex-1 text-xs text-muted-foreground">«{selection.slice(0, 140)}…»</p>
            <Button size="sm" disabled={starting !== null} onClick={() => void openDiscussion(selection)}>
              {starting === "chat" ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="chat_bubble" size={16} className="mr-1" />}
              Обсудить
            </Button>
            <Button size="sm" variant="outline" disabled={starting !== null} onClick={() => void researchSelection(selection)}>
              {starting === "research" ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="search" size={16} className="mr-1" />}
              Ресёрч
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
