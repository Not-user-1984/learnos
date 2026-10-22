"use client";

/** Встроенный PDF-просмотрщик на pdf.js — единственный компонент рендера документа.
 *  Чёткость: canvas в физическом разрешении (devicePixelRatio), css-размер задаётся
 *  явно; перерендер с дебаунсом при любом изменении масштаба (зум/resize).
 *  Навигация: детерминированный переход к странице — очередь последнего намерения
 *  (переживает загрузку документа), прыжок = рендер коридора вокруг цели →
 *  уточнение высот холдеров по факту → скролл; после — обычный ленивый режим. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  /** URL документа (проксируется через /api → ядро). */
  url: string;
  /** Целевая страница (1-based); каждое изменение — детерминированный переход. */
  page: number;
  onPageChange?: (page: number) => void;
  /** Слот слева в тулбаре (кнопка возврата к книге и т.п.). */
  toolbarStart?: ReactNode;
  /** Слот справа в тулбаре (оглавление, яркость, внешние ссылки). */
  toolbarExtra?: ReactNode;
  /** Листание с клавиатуры: ← → и PgUp/PgDn (полноэкранный ридер). */
  keyboard?: boolean;
  /** CSS-фильтр контейнера страниц (яркость читалки), без тулбара. */
  canvasFilter?: string;
  /** Ссылка «открыть отдельно» (полноэкранный ридер с текущего места); без неё — сам файл. */
  openHref?: string;
  className?: string;
};

const RENDER_MARGIN = "700px"; // коридор ленивого рендера вокруг видимой части
const RERENDER_DEBOUNCE = 250; // мс после смены масштаба до перерисовки

const clampPage = (n: number, total: number) => Math.min(Math.max(1, n), Math.max(1, total));

/** Физическое разрешение канваса: не ниже CSS-пикселей, на retina — ×DPR. */
function outputScale(): number {
  return Math.min(Math.max(window.devicePixelRatio || 1, 1), 3);
}

export function PdfViewer({
  url,
  page,
  onPageChange,
  toolbarStart,
  toolbarExtra,
  keyboard = false,
  canvasFilter,
  openHref,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const numPagesRef = useRef(0);
  const renderedRef = useRef<Set<number>>(new Set());
  const tasksRef = useRef<Map<number, { cancel: () => void }>>(new Map());
  const scaleRef = useRef(1);
  const loadGuard = useRef(0);
  const renderEpoch = useRef(0);
  const intentRef = useRef(page); // последнее намерение перехода

  const [containerW, setContainerW] = useState(0);
  const [numPages, setNumPages] = useState(0);
  const [baseSize, setBaseSize] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [current, setCurrent] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const scale = baseSize && containerW > 0 ? ((containerW - 24) / baseSize.w) * zoom : 1;

  // актуальный масштаб для колбэков (не читаем ref во время рендера)
  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  // --- страница: canvas в физическом разрешении, css-размер и высота холдера — по факту ---
  const renderPage = useCallback(async (n: number, epoch: number) => {
    const doc = docRef.current;
    const holder = pageRefs.current[n - 1];
    if (!doc || !holder || renderedRef.current.has(n)) return;
    renderedRef.current.add(n);
    try {
      const p: PDFPageProxy = await doc.getPage(n);
      const cssViewport = p.getViewport({ scale: scaleRef.current });
      const dpr = outputScale();
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(cssViewport.width * dpr);
      canvas.height = Math.floor(cssViewport.height * dpr);
      const cssW = `${Math.floor(cssViewport.width)}px`;
      const cssH = `${Math.floor(cssViewport.height)}px`;
      canvas.style.width = cssW;
      canvas.style.height = cssH;
      canvas.className = "mx-auto block";
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const task = p.render({
        canvas,
        canvasContext: ctx,
        viewport: cssViewport,
        transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0],
      });
      tasksRef.current.set(n, task);
      await task.promise;
      tasksRef.current.delete(n);
      if (epoch === renderEpoch.current && holder.isConnected) {
        // высота холдера — по факту страницы: геометрия скролла не «паршится»
        holder.style.width = cssW;
        holder.style.height = cssH;
        holder.replaceChildren(canvas);
      }
    } catch {
      renderedRef.current.delete(n); // отмена или сбой — можно повторить
    }
  }, []);

  const clearRendered = useCallback(() => {
    tasksRef.current.forEach((t) => t.cancel());
    tasksRef.current = new Map();
    renderedRef.current = new Set();
    pageRefs.current.forEach((el) => el && el.replaceChildren());
  }, []);

  // --- детерминированный переход к странице: рендер цели → точные высоты → скролл ---
  const jump = useCallback(
    async (n: number) => {
      const doc = docRef.current;
      if (!doc) return; // намерение останется в intentRef, применится после загрузки
      const target = clampPage(n, numPagesRef.current);
      const epoch = renderEpoch.current;
      // коридор вокруг цели отрисовать до скролла — цель не «проскочит» после рендера
      const around = [target - 1, target, target + 1].filter((p) => p >= 1 && p <= numPagesRef.current);
      await Promise.all(around.map((p) => renderPage(p, epoch)));
      const holder = pageRefs.current[target - 1];
      holder?.scrollIntoView({ block: "start", behavior: "instant" as ScrollBehavior });
      setCurrent(target);
    },
    [renderPage],
  );

  useEffect(() => {
    intentRef.current = page;
    void jump(page);
  }, [page, jump]);

  // --- документ: динамический импорт pdfjs (только в браузере), один на url ---
  useEffect(() => {
    const guard = ++loadGuard.current;
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";
        const loadingTask = pdfjs.getDocument({
          url,
          cMapUrl: "/pdfjs/cmaps/",
          cMapPacked: true,
          standardFontDataUrl: "/pdfjs/standard_fonts/",
        });
        const doc = await loadingTask.promise;
        if (cancelled || guard !== loadGuard.current) {
          void loadingTask.destroy();
          return;
        }
        docRef.current = doc;
        const first = await doc.getPage(1);
        if (cancelled || guard !== loadGuard.current) return;
        numPagesRef.current = doc.numPages;
        setNumPages(doc.numPages);
        const vp = first.getViewport({ scale: 1 });
        setBaseSize({ w: vp.width, h: vp.height });
        // применить накопленное намерение, если переход просили во время загрузки
        if (intentRef.current > 1) void jump(intentRef.current);
      } catch (e) {
        if (!cancelled && guard === loadGuard.current) {
          setError(e instanceof Error ? e.message : "не удалось открыть PDF");
        }
      }
    })();
    return () => {
      cancelled = true;
      docRef.current = null;
      numPagesRef.current = 0;
      clearRendered();
    };
  }, [url, clearRendered, jump]);

  // --- ширина контейнера (fit-width реагирует на resize окна) ---
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setContainerW(el.clientWidth));
    ro.observe(el);
    setContainerW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // --- ленивый рендер: видимый коридор → canvas, вне коридора → снимаем ---
  useEffect(() => {
    const root = containerRef.current;
    if (!root || numPages === 0) return;
    const visible = new Set<number>();
    const apply = () => {
      const epoch = renderEpoch.current;
      visible.forEach((n) => void renderPage(n, epoch));
      renderedRef.current.forEach((n) => {
        if (visible.has(n)) return;
        const task = tasksRef.current.get(n);
        if (task) {
          task.cancel();
          tasksRef.current.delete(n);
        }
        renderedRef.current.delete(n);
        const holder = pageRefs.current[n - 1];
        if (holder) holder.replaceChildren(); // высота холдера уже уточнена рендером
      });
    };
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const n = Number((e.target as HTMLElement).dataset.page);
          if (e.isIntersecting) visible.add(n);
          else visible.delete(n);
        }
        apply();
      },
      { root, rootMargin: RENDER_MARGIN },
    );
    pageRefs.current.slice(0, numPages).forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [numPages, renderPage]);

  // --- масштаб изменился (зум/resize): перерисовать видимое с дебаунсом ---
  useEffect(() => {
    if (!baseSize) return;
    const t = setTimeout(() => {
      renderEpoch.current += 1;
      clearRendered();
      const root = containerRef.current;
      if (!root) return;
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (!e.isIntersecting) return;
            const n = Number((e.target as HTMLElement).dataset.page);
            void renderPage(n, renderEpoch.current);
          });
        },
        { root, rootMargin: RENDER_MARGIN },
      );
      pageRefs.current.forEach((el) => el && io.observe(el));
      const ioRef = io;
      setTimeout(() => ioRef.disconnect(), 1200); // разовый проход по видимым
    }, RERENDER_DEBOUNCE);
    return () => clearTimeout(t);
  }, [scale, baseSize, clearRendered, renderPage]);

  // --- текущая страница: ближайшая к верху контейнера (для индикатора) ---
  useEffect(() => {
    const root = containerRef.current;
    if (!root || numPages === 0) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const onScroll = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        const top = root.getBoundingClientRect().top + 12;
        let best = 1;
        for (let i = 0; i < numPages; i++) {
          const el = pageRefs.current[i];
          if (!el) continue;
          if (el.getBoundingClientRect().top <= top) best = i + 1;
          else break;
        }
        setCurrent(best);
        onPageChange?.(best);
      }, 120);
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (timer) clearTimeout(timer);
    };
  }, [numPages, onPageChange]);

  const scrollToPage = useCallback(
    (n: number) => {
      intentRef.current = n;
      void jump(n);
    },
    [jump],
  );

  // --- клавиатура (полноэкранный ридер): ← → и PgUp/PgDn ---
  useEffect(() => {
    if (!keyboard) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowRight" || e.key === "PageDown") {
        e.preventDefault();
        scrollToPage(current + 1);
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        scrollToPage(current - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyboard, current, scrollToPage]);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        <p>
          PDF не открылся ({error}).{" "}
          <a href={openHref ?? url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
            Открыть отдельно
          </a>
        </p>
      </div>
    );
  }

  const pageW = baseSize ? Math.round(baseSize.w * scale) : 0;
  const pageH = baseSize ? Math.round(baseSize.h * scale) : 0;

  return (
    <div className={cn("flex min-h-0 min-w-0 flex-1 flex-col", className)}>
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b bg-background/95 px-3 py-1.5">
        {toolbarStart}
        <span className="mr-1 text-xs whitespace-nowrap text-muted-foreground" aria-live="polite">
          стр. {current} / {numPages || "…"}
        </span>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Предыдущая страница" disabled={current <= 1} onClick={() => scrollToPage(current - 1)}>
          <Icon name="chevron_left" size={16} />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Следующая страница" disabled={current >= numPages} onClick={() => scrollToPage(current + 1)}>
          <Icon name="chevron_right" size={16} />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Уменьшить" disabled={zoom <= 0.5} onClick={() => setZoom((z) => Math.round((z - 0.1) * 10) / 10)}>
          <Icon name="zoom_out" size={16} />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Увеличить" onClick={() => setZoom((z) => Math.round((z + 0.1) * 10) / 10)}>
          <Icon name="zoom_in" size={16} />
        </Button>
        {zoom !== 1 && (
          <Button variant="ghost" className="h-7 px-2 text-xs whitespace-nowrap" aria-label="По ширине окна" onClick={() => setZoom(1)}>
            <Icon name="width" size={14} className="mr-1" /> по ширине
          </Button>
        )}
        {toolbarExtra}
        <a
          href={openHref ?? url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs whitespace-nowrap text-muted-foreground hover:bg-accent hover:text-foreground"
          title={openHref ? "Полноэкранный ридер в новой вкладке" : "Нативный просмотрщик браузера"}
        >
          <Icon name="open_in_new" size={14} />
          <span className="hidden sm:inline">Отдельно</span>
        </a>
      </div>
      <div
        ref={containerRef}
        className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3"
        style={canvasFilter ? { filter: canvasFilter } : undefined}
      >
        {numPages > 0 &&
          Array.from({ length: numPages }, (_, i) => i + 1).map((n) => (
            <div
              key={n}
              data-page={n}
              ref={(el) => {
                pageRefs.current[n - 1] = el;
              }}
              style={{ width: pageW || undefined, height: pageH || undefined }}
              className={cn(
                "mx-auto mb-3 flex items-center justify-center overflow-hidden rounded bg-white shadow-sm last:mb-0 dark:bg-zinc-100",
                !pageH && "min-h-40",
              )}
            >
              {!pageH && <span className="text-xs text-zinc-400">стр. {n}</span>}
            </div>
          ))}
      </div>
    </div>
  );
}
