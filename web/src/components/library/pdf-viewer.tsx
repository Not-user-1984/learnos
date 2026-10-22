"use client";

/** Встроенный PDF-просмотрщик на pdf.js: страницы на canvas с ленивым рендером
 *  (коридор вокруг видимой части), fit-width по умолчанию, зум, переход к странице
 *  (глава → страница) скроллом без перезагрузки документа. Замена iframe: нативный
 *  вьюер не прыгает на #page=N и не работает в Electron webview. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = {
  /** URL документа (проксируется через /api → ядро). */
  url: string;
  /** Куда промотать документ (1-based); меняется при переходе между главами. */
  page: number;
  onPageChange?: (page: number) => void;
};

const RENDER_MARGIN = "700px"; // коридор ленивого рендера вокруг видимой части

export function PdfViewer({ url, page, onPageChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const renderedRef = useRef<Set<number>>(new Set());
  const tasksRef = useRef<Map<number, { cancel: () => void }>>(new Map());
  const scaleRef = useRef(1);
  const loadGuard = useRef(0);
  const zoomEpoch = useRef(0);

  const [containerW, setContainerW] = useState(0);
  const [numPages, setNumPages] = useState(0);
  const [baseSize, setBaseSize] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [current, setCurrent] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const scale = baseSize && containerW > 0 ? ((containerW - 24) / baseSize.w) * zoom : 1;

  // актуальный масштаб для колбэков наблюдателей (не читаем ref во время рендера)
  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

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
        setNumPages(doc.numPages);
        const vp = first.getViewport({ scale: 1 });
        setBaseSize({ w: vp.width, h: vp.height });
      } catch (e) {
        if (!cancelled && guard === loadGuard.current) {
          setError(e instanceof Error ? e.message : "не удалось открыть PDF");
        }
      }
    })();
    return () => {
      cancelled = true;
      docRef.current = null;
      tasksRef.current.forEach((t) => t.cancel());
      tasksRef.current = new Map();
      renderedRef.current = new Set();
    };
  }, [url]);

  // --- ширина контейнера (fit-width реагирует на resize окна) ---
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setContainerW(el.clientWidth));
    ro.observe(el);
    setContainerW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const renderPage = useCallback(async (n: number, epoch: number) => {
    const doc = docRef.current;
    const holder = pageRefs.current[n - 1];
    if (!doc || !holder || renderedRef.current.has(n)) return;
    renderedRef.current.add(n);
    try {
      const p: PDFPageProxy = await doc.getPage(n);
      const viewport = p.getViewport({ scale: scaleRef.current });
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.className = "block";
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const task = p.render({ canvas, canvasContext: ctx, viewport });
      tasksRef.current.set(n, task);
      await task.promise;
      tasksRef.current.delete(n);
      if (epoch === zoomEpoch.current && holder.isConnected) holder.replaceChildren(canvas);
    } catch {
      renderedRef.current.delete(n); // отмена или сбой — можно повторить
    }
  }, []);

  // --- ленивый рендер: видимый коридор → canvas, вне коридора → снимаем ---
  useEffect(() => {
    const root = containerRef.current;
    if (!root || numPages === 0) return;
    const visible = new Set<number>();
    const apply = () => {
      const epoch = zoomEpoch.current;
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
        if (holder) holder.replaceChildren(); // высота холдера задана стилем — сетка не прыгает
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

  // --- зум: масштаб изменился — рендеры устарели, чистим и перерисовываем видимое ---
  useEffect(() => {
    zoomEpoch.current += 1;
    tasksRef.current.forEach((t) => t.cancel());
    tasksRef.current = new Map();
    renderedRef.current = new Set();
    pageRefs.current.forEach((el) => el && el.replaceChildren());
    // повторный рендер видимого коридора (IO сам не проснётся без скролла)
    const root = containerRef.current;
    if (!root) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const n = Number((e.target as HTMLElement).dataset.page);
          void renderPage(n, zoomEpoch.current);
        });
      },
      { root, rootMargin: RENDER_MARGIN },
    );
    pageRefs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [zoom, renderPage]);

  // --- страница главы: скролл к нужной странице, документ не перезагружается;
  // индикатор обновит скролл-событие ---
  useEffect(() => {
    if (numPages === 0) return;
    pageRefs.current[page - 1]?.scrollIntoView({ block: "start", behavior: "instant" as ScrollBehavior });
  }, [page, numPages]);

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

  const scrollToPage = (n: number) => {
    const target = Math.min(Math.max(1, n), numPages || 1);
    pageRefs.current[target - 1]?.scrollIntoView({ block: "start" });
    setCurrent(target);
  };

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        <p>
          PDF не открылся ({error}).{" "}
          <a href={url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
            Открыть в новой вкладке
          </a>
        </p>
      </div>
    );
  }

  const pageW = baseSize ? Math.round(baseSize.w * scale) : 0;
  const pageH = baseSize ? Math.round(baseSize.h * scale) : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b bg-background/95 px-3 py-1.5">
        <span className="mr-2 text-xs text-muted-foreground" aria-live="polite">
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
          <Button variant="ghost" className="h-7 px-2 text-xs" aria-label="По ширине окна" onClick={() => setZoom(1)}>
            <Icon name="width" size={14} className="mr-1" /> по ширине
          </Button>
        )}
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          title="Нативный просмотрщик браузера"
        >
          <Icon name="open_in_new" size={14} />
          <span className="hidden sm:inline">В новой вкладке</span>
        </a>
      </div>
      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3">
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
