"use client";

/** Полноэкранный PDF-ридер (B-013): PDF + text-layer (выделение → цитата в чат),
 *  оглавление, клавиатура, место чтения на сервере, «Глава прочитана» и
 *  подсказка «Разобрать главу». Чат главы — справа (ReaderSplit). */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useStored } from "@/lib/use-stored";
import { apiPost } from "@/lib/api";
import { PdfViewer } from "./pdf-viewer";

type Chapter = { idx: number; title: string; number?: number | null };

type Props = {
  sourceUid: string;
  sourceTitle: string;
  chapters: Chapter[];
  /** Начальные значения: URL > место чтения активности > глава 1. */
  initialChapter: number;
  initialPage: number | null;
  /** Активность источника: синхронизация места и «прочитано»; null — читать без прогресса. */
  activityUid: string | null;
  /** Главы с idx < cursor уже прочитаны (авто-отметка не нужна). */
  initialCursor: number;
  /** Открыть чат главы с этим сообщением сразу (разбор без чтения). */
  initialDiscuss?: string | null;
  /** Выделение/кнопки зовут чат главы: цитата или стартовое сообщение. */
  onDiscuss: (text?: string) => void;
  /** Текущая глава (по видимой странице) — ключ чата и позиция. */
  onChapterChange?: (idx: number) => void;
};

const BRIGHT_KEY = "learnos-pdf-brightness";
const BRIGHT_EVENT = "learnos-pdf-brightness-change";
const POSITION_DEBOUNCE = 1500; // мс тишины до отправки места на сервер
const QUOTE_MAX = 800; // символы цитаты из выделения

export function PdfReader({
  sourceUid,
  sourceTitle,
  chapters,
  initialChapter,
  initialPage,
  activityUid,
  initialCursor,
  initialDiscuss,
  onDiscuss,
  onChapterChange,
}: Props) {
  // страницы/номера/секции глав из /outline: строим карты «глава → …»;
  // если page в URL не задан — после загрузки outline проматываем к началу главы
  const [starts, setStarts] = useState<Record<string, number>>({});
  const [numbers, setNumbers] = useState<Record<string, number>>({});
  const [sections, setSections] = useState<Record<string, { title: string; page: number }[]>>({});
  const [target, setTarget] = useState<number>(initialPage ?? 1);
  const [current, setCurrent] = useState(target);
  const [tocOpen, setTocOpen] = useState(false);
  const [brightnessRaw, setBrightness] = useStored(BRIGHT_KEY, BRIGHT_EVENT, "1");
  const brightness = Number(brightnessRaw) || 1;
  const urlSync = useRef<ReturnType<typeof setTimeout> | null>(null);
  const positionSync = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [readSet, setReadSet] = useState<Set<number>>(new Set()); // главы, отмеченные «прочитано»
  const markedRef = useRef<Set<number>>(new Set()); // гарда от повторной отметки (события, не рендер)
  const [readHint, setReadHint] = useState<number | null>(null); // глава свежепрочитана → «Разобрать?»
  const [quote, setQuote] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const discussedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/sources/${sourceUid}/outline`)
      .then((r) => (r.ok ? r.json() : { pages: {} }))
      .then(
        (body: {
          pages?: Record<string, number>;
          numbers?: Record<string, number>;
          sections?: Record<string, { title: string; page: number }[]>;
        }) => {
          if (cancelled) return;
          const pages = body.pages ?? {};
          setStarts(pages);
          setNumbers(body.numbers ?? {});
          setSections(body.sections ?? {});
          if (initialPage === null) {
            const s = pages[String(initialChapter)];
            if (s && s > 1) {
              setTarget(s);
              setCurrent(s);
            }
          }
        },
      )
      .catch(() => setStarts({}));
    return () => {
      cancelled = true;
    };
  }, [sourceUid, initialPage, initialChapter]);

  // текущая глава — та, чей диапазон покрывает видимую страницу
  const currentChapter = useMemo(() => {
    let ch = chapters[0]?.idx ?? 1;
    for (const c of chapters) {
      const s = starts[String(c.idx)];
      if (s !== undefined && s <= current) ch = c.idx;
    }
    return ch;
  }, [chapters, current, starts]);

  useEffect(() => {
    onChapterChange?.(currentChapter);
  }, [currentChapter, onChapterChange]);

  // место чтения → URL (без перезагрузки) + на сервер с дебаунсом (B-013)
  useEffect(() => {
    if (urlSync.current) clearTimeout(urlSync.current);
    urlSync.current = setTimeout(() => {
      const url = `/library/${sourceUid}/read?ch=${currentChapter}&page=${current}`;
      window.history.replaceState(null, "", url);
    }, 400);
    if (activityUid) {
      if (positionSync.current) clearTimeout(positionSync.current);
      positionSync.current = setTimeout(() => {
        void apiPost(`/activities/${activityUid}/position`, {
          chapter: currentChapter,
          page: current,
        }).catch(() => undefined);
      }, POSITION_DEBOUNCE);
    }
    return () => {
      if (urlSync.current) clearTimeout(urlSync.current);
    };
  }, [currentChapter, current, sourceUid, activityUid]);

  // разбор без чтения: стартовое сообщение в чат главы при входе (B-013)
  useEffect(() => {
    if (initialDiscuss && !discussedRef.current) {
      discussedRef.current = true;
      onDiscuss(initialDiscuss);
    }
  }, [initialDiscuss, onDiscuss]);

  /** Отметить главу прочитанной (один раз за сессию читалки) и предложить разбор. */
  const markRead = useCallback(
    (chapter: number) => {
      if (markedRef.current.has(chapter)) return;
      markedRef.current.add(chapter);
      setReadSet((prev) => new Set(prev).add(chapter));
      if (!activityUid) return; // без активности прогресс не ведём — кнопка просто скрывается
      void apiPost("/activities/mark-read", { source: sourceUid, chapter })
        .then(() => setReadHint(chapter))
        .catch(() => {
          markedRef.current.delete(chapter);
          setReadSet((prev) => {
            const next = new Set(prev);
            next.delete(chapter);
            return next;
          });
        });
    },
    [activityUid, sourceUid],
  );

  // уход на следующую главу по порядку = предыдущая дочитана — независимо от того,
  // как перешли: кнопка, скролл или листание страниц (fix ревью B-013, один раз на главу)
  const prevChapterRef = useRef(initialChapter);
  useEffect(() => {
    const prev = prevChapterRef.current;
    prevChapterRef.current = currentChapter;
    if (currentChapter === prev + 1) markRead(prev);
  }, [currentChapter, markRead]);

  const goToChapter = (idx: number) => {
    const s = starts[String(idx)];
    if (s) {
      setTarget(s);
      setCurrent(s);
    }
  };

  const goToPage = (page: number) => {
    setTarget(page);
    setCurrent(page);
  };

  // --- выделение текста (text-layer) → плашка «Обсудить выделенное» ---
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const onSelChange = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed) {
          setQuote(null);
          return;
        }
        const anchor = sel.anchorNode;
        const node = anchor instanceof Element ? anchor : anchor?.parentElement ?? null;
        if (!node || !root.contains(node.closest(".textLayer"))) {
          setQuote(null);
          return;
        }
        const text = sel.toString().replace(/\s+/g, " ").trim();
        setQuote(text.length >= 8 ? text.slice(0, QUOTE_MAX) : null);
      }, 250);
    };
    document.addEventListener("selectionchange", onSelChange);
    return () => {
      document.removeEventListener("selectionchange", onSelChange);
      if (timer) clearTimeout(timer);
    };
  }, []);

  /** Подпись главы: номер книги («Глава 3 · Ветвление») или позиция. */
  const chapterName = (c: Chapter): string => {
    const n = c.number ?? numbers[String(c.idx)];
    return n ? `Глава ${n} · ${c.title}` : `${c.idx}. ${c.title}`;
  };

  const chIdxs = chapters.map((c) => c.idx);
  const prevChapter = chIdxs.filter((i) => i < currentChapter).pop();
  const nextChapter = chIdxs.find((i) => i > currentChapter);
  const chapterRead = readSet.has(currentChapter) || currentChapter < initialCursor;

  return (
    <div ref={rootRef} className="relative flex h-full min-w-0 flex-col">
      {/* тулбар PdfViewer + обвязка ридера */}
      <PdfViewer
        url={`/api/sources/${sourceUid}/file`}
        page={target}
        onPageChange={setCurrent}
        keyboard
        canvasFilter={`brightness(${brightness})`}
        openHref={`/library/${sourceUid}/read?ch=${currentChapter}&page=${current}`}
        toolbarStart={
          <Link
            href={`/library/${sourceUid}`}
            className="mr-2 inline-flex min-w-0 items-center gap-1 text-sm text-primary hover:underline"
            title="К странице книги"
          >
            <Icon name="chevron_left" size={16} className="shrink-0" />
            <span className="max-w-[16rem] truncate">{sourceTitle}</span>
          </Link>
        }
        toolbarExtra={
          <>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              aria-label="Чат главы"
              title="Обсудить главу с нейронкой"
              onClick={() => onDiscuss()}
            >
              <Icon name="chat_bubble" size={14} />
              <span className="hidden sm:inline">Обсудить</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              aria-label="Глава прочитана"
              title="Отметить главу прочитанной — она попадёт в прогресс книги"
              disabled={chapterRead || !activityUid}
              onClick={() => markRead(currentChapter)}
            >
              <Icon name={chapterRead ? "task_alt" : "check"} size={14} />
              <span className="hidden sm:inline">{chapterRead ? "Прочитано" : "Глава прочитана"}</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              aria-label="Оглавление"
              onClick={() => setTocOpen(true)}
            >
              <Icon name="toc" size={14} />
              <span className="hidden sm:inline">Оглавление</span>
            </Button>
            <label className="hidden items-center gap-1.5 pl-1 text-xs text-muted-foreground md:inline-flex" title="Яркость страниц">
              <Icon name="brightness_6" size={14} />
              <input
                type="range"
                min={0.4}
                max={1}
                step={0.05}
                value={Math.min(brightness, 1)}
                onChange={(e) => setBrightness(e.target.value)}
                className="h-1 w-24 accent-primary"
                aria-label="Яркость"
              />
            </label>
            <a
              href={`/api/sources/${sourceUid}/file`}
              target="_blank"
              rel="noreferrer"
              className="hidden h-7 items-center gap-1 rounded-md px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground sm:inline-flex"
              title="Оригинальный файл без обвязки"
            >
              <Icon name="download" size={14} /> .pdf
            </a>
          </>
        }
      />

      {/* навигация по главам */}
      <nav className="flex shrink-0 items-center justify-between gap-2 border-t px-3 py-2">
        {prevChapter !== undefined ? (
          <Button variant="outline" size="sm" className="max-w-[40%]" onClick={() => goToChapter(prevChapter)}>
            <Icon name="chevron_left" size={16} className="shrink-0" />
            <span className="truncate">
              {(() => {
                const c = chapters.find((ch) => ch.idx === prevChapter);
                return c ? chapterName(c) : `Глава ${prevChapter}`;
              })()}
            </span>
          </Button>
        ) : (
          <span />
        )}
        <span className="truncate text-xs text-muted-foreground">
          {(() => {
            const c = chapters.find((ch) => ch.idx === currentChapter);
            return c ? chapterName(c) : `глава ${currentChapter}`;
          })()}
        </span>
        {nextChapter !== undefined ? (
          <Button variant="outline" size="sm" className="max-w-[40%]" onClick={() => goToChapter(nextChapter)}>
            <span className="truncate">
              {(() => {
                const c = chapters.find((ch) => ch.idx === nextChapter);
                return c ? chapterName(c) : `Глава ${nextChapter}`;
              })()}
            </span>
            <Icon name="chevron_right" size={16} className="shrink-0" />
          </Button>
        ) : (
          <span />
        )}
      </nav>

      {/* выделение в text-layer → цитата в чат главы (B-013) */}
      {quote && (
        <div className="pointer-events-none absolute inset-x-0 bottom-16 z-20 flex justify-center px-4">
          <div className="pointer-events-auto flex max-w-lg items-center gap-3 rounded-xl border bg-card px-4 py-2.5 shadow-lg">
            <Icon name="format_quote" size={16} className="shrink-0 text-primary" />
            <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground" title={quote}>
              {quote}
            </span>
            <Button
              size="sm"
              onClick={() => {
                onDiscuss(`«${quote}»\n\n`);
                setQuote(null);
              }}
            >
              Обсудить
            </Button>
          </div>
        </div>
      )}

      {/* глава отмечена прочитанной → предложить разбор (можно закрыть) */}
      {readHint !== null && readHint === currentChapter && (
        <div className="absolute inset-x-0 bottom-16 z-20 flex justify-center px-4">
          <div className="flex max-w-lg items-center gap-3 rounded-xl border border-primary/40 bg-primary/10 px-4 py-2.5 shadow-lg">
            <Icon name="task_alt" size={16} className="shrink-0 text-primary" />
            <span className="min-w-0 flex-1 text-sm">Глава прочитана. Разобрать её с нейронкой?</span>
            <Button
              size="sm"
              onClick={() => {
                onDiscuss("Разбери эту главу: главное, ключевые понятия и 1–2 вопроса на подумать.");
                setReadHint(null);
              }}
            >
              Разобрать
            </Button>
            <Button size="sm" variant="ghost" aria-label="Закрыть подсказку" onClick={() => setReadHint(null)}>
              <Icon name="close" size={16} />
            </Button>
          </div>
        </div>
      )}

      {/* оглавление-шторка */}
      {tocOpen && (
        <>
          <button
            type="button"
            aria-label="Закрыть оглавление"
            className="fixed inset-0 z-30 bg-black/30"
            onClick={() => setTocOpen(false)}
          />
          <aside className="fixed top-0 left-0 z-40 flex h-full w-72 max-w-[85vw] flex-col border-r bg-background shadow-lg">
            <div className="flex items-center justify-between border-b px-3 py-2">
              <span className="text-sm font-medium">Оглавление</span>
              <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Закрыть" onClick={() => setTocOpen(false)}>
                <Icon name="close" size={16} />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {chapters.map((c) => {
                const s = starts[String(c.idx)];
                const active = c.idx === currentChapter;
                const secs = sections[String(c.idx)] ?? [];
                return (
                  <div key={c.idx} className="mb-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        goToChapter(c.idx);
                        setTocOpen(false);
                      }}
                      className={cn(
                        "flex w-full items-baseline gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-accent",
                        active && "bg-accent/60 font-medium",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">{chapterName(c)}</span>
                      {s !== null && <span className="shrink-0 text-xs text-muted-foreground">с. {s}</span>}
                    </button>
                    {secs.length > 0 && (
                      <ul className="mb-1 ml-4 border-l pl-1">
                        {secs.map((sec, i) => (
                          <li key={i}>
                            <button
                              type="button"
                              onClick={() => {
                                if (sec.page) goToPage(sec.page);
                                setTocOpen(false);
                              }}
                              className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                              title={sec.title}
                            >
                              <span className="min-w-0 flex-1 truncate">{sec.title}</span>
                              <span className="shrink-0">{sec.page || ""}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
              {chapters.length === 0 && <p className="p-3 text-sm text-muted-foreground">Главы не обработаны</p>}
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
