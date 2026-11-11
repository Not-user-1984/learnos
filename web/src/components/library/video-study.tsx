"use client";

/** Видео-режим split-view (B-006): YouTube-плеер (IFrame API, без библиотек) +
 *  транскрипт с таймкодами; «спросить про момент» уносит [мм:сс] и фрагмент в чат. */

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type VideoSegment = { start: number; text: string };

declare global {
  interface Window {
    YT?: {
      Player: new (el: HTMLElement, opts: Record<string, unknown>) => YTPlayerLike;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

interface YTPlayerLike {
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getCurrentTime: () => number;
  destroy: () => void;
}

/** Загрузка IFrame API один раз; окно промиса закрывается по таймауту (нет сети → fallback). */
function loadYouTubeApi(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.YT?.Player) return resolve(true);
    const existing = document.getElementById("yt-iframe-api");
    const done = () => resolve(Boolean(window.YT?.Player));
    if (!existing) {
      const script = document.createElement("script");
      script.id = "yt-iframe-api";
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => resolve(false);
      document.head.appendChild(script);
    }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      prev?.();
      done();
    };
    setTimeout(done, 6000); // API не пришёл (прокси?) — транскрипт без плеера
  });
}

export function VideoStudy({
  sourceUid,
  videoId,
  url,
  title,
  seekRef,
  onAsk,
  onDiscuss,
}: {
  sourceUid: string;
  videoId: string | null;
  url: string | null;
  title: string;
  /** seek-функция наружу (таймкоды из ответов чата, B-006). */
  seekRef?: { current: ((seconds: number) => void) | null };
  /** Спросить про момент: текст уйдёт в композер панели. */
  onAsk: (text: string) => void;
  onDiscuss: () => void;
}) {
  const [segments, setSegments] = useState<VideoSegment[] | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [current, setCurrent] = useState(0);
  const holderRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayerLike | null>(null);

  useEffect(() => {
    api<{ segments: VideoSegment[] }>(`/sources/${sourceUid}/segments`)
      .then((s) => setSegments(s.segments ?? []))
      .catch(() => setSegments([]));
  }, [sourceUid]);

  useEffect(() => {
    if (!videoId) return;
    let cancelled = false;
    void loadYouTubeApi().then((ok) => {
      if (cancelled) return;
      setApiOk(ok);
      if (ok && holderRef.current && window.YT?.Player) {
        playerRef.current = new window.YT.Player(holderRef.current, {
          videoId,
          playerVars: { rel: 0, modestbranding: 1 },
        });
      }
    });
    return () => {
      cancelled = true;
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [videoId]);

  // подсветка текущего сегмента — лёгкий опрос плеера
  useEffect(() => {
    if (apiOk === false) return;
    const id = setInterval(() => {
      const t = playerRef.current?.getCurrentTime?.();
      if (typeof t === "number") setCurrent(t);
    }, 500);
    return () => clearInterval(id);
  }, [apiOk]);

  const seek = (s: number) => {
    playerRef.current?.seekTo(s, true);
    setCurrent(s);
  };

  // seek-функция доступна родителю: таймкоды [мм:сс] в ответах чата кликают сюда
  useEffect(() => {
    if (!seekRef) return;
    seekRef.current = seek;
    return () => {
      seekRef.current = null;
    };
  });

  const askAbout = (seg: VideoSegment) => {
    const stamp = formatTimecode(seg.start);
    const window = (segments ?? []).filter((s) => Math.abs(s.start - seg.start) <= 30);
    onAsk(
      `Про момент [${stamp}] видео «${title}»:\n\n${window.map((s) => s.text).join(" ")}\n\n— что здесь имеется в виду?`,
    );
  };

  const activeIdx = (segments ?? []).findIndex((s, i) => {
    const next = segments?.[i + 1]?.start ?? Infinity;
    return current >= s.start && current < next;
  });

  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
        <p className="min-w-0 truncate text-sm font-medium">{title}</p>
        <Button size="sm" variant="outline" className="ml-auto shrink-0" onClick={onDiscuss}>
          <Icon name="chat_bubble" size={15} className="mr-1" /> Обсудить
        </Button>
      </header>

      {/* плеер: если API недоступен (прокси/сеть) — ссылка на YouTube, транскрипт работает */}
      <div className="shrink-0 bg-black/95">
        {videoId && apiOk !== false ? (
          <div className="mx-auto aspect-video max-h-[45vh] w-full max-w-3xl">
            <div ref={holderRef} className="h-full w-full" />
          </div>
        ) : (
          <div className="flex items-center justify-center gap-3 px-4 py-6 text-sm text-muted-foreground">
            <Icon name="movie" size={16} />
            {videoId
              ? "плеер недоступен (нет доступа к YouTube) — транскрипт ниже"
              : "это видео без таймкодов — текст как есть"}
            {url && (
              <a href={url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                открыть на YouTube ↗
              </a>
            )}
          </div>
        )}
      </div>

      {/* транскрипт с таймкодами */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {segments === null ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Icon name="progress_activity" size={15} className="animate-spin" /> транскрипт…
          </p>
        ) : segments.length === 0 ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            Сегментов с таймкодами нет: обнови обработку источника — они появятся.
          </p>
        ) : (
          <ol className="mx-auto flex max-w-3xl flex-col gap-1">
            {segments.map((seg, i) => (
              <li
                key={seg.start}
                className={cn(
                  "flex items-start gap-3 rounded-lg px-2 py-1.5 text-sm transition-colors",
                  i === activeIdx ? "bg-primary/10" : "hover:bg-accent/50",
                )}
              >
                <button
                  type="button"
                  onClick={() => seek(seg.start)}
                  className="shrink-0 rounded-md border border-primary/40 bg-primary/10 px-1.5 py-0.5 font-mono text-xs text-primary transition hover:bg-primary/20"
                  title="Перемотать"
                >
                  {formatTimecode(seg.start)}
                </button>
                <p className="min-w-0 flex-1 leading-relaxed">{seg.text}</p>
                <button
                  type="button"
                  onClick={() => askAbout(seg)}
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition hover:text-primary"
                  title="Спросить про этот момент (±30 с)"
                >
                  <Icon name="chat_bubble" size={14} />
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/** Секунды → [мм:сс] / [ч:мм:сс] — формат таймкодов, кликабельный в чате. */
export function formatTimecode(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}
