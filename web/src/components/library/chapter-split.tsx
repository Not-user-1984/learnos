"use client";

/** Страничный split-view (B-006): книга/видео слева + панель чата справа.
 *  Клиентская обёртка над ReaderSplit: держит seek-функцию видео для таймкодов. */

import { useRef } from "react";
import type { SourceDetail } from "@/lib/types";
import { ChapterReader } from "./reader";
import { ReaderSplit } from "./reader-split";
import { VideoStudy } from "./video-study";

type Props = {
  source: SourceDetail;
  chapterIdx: number;
  chapterTitle: string;
  chapterSummary: string | null;
  chapterNumber: number | null;
  text: string;
  prevIdx: number | null;
  nextIdx: number | null;
  initialMode: string | null;
  progress: { cursor: number; total: number } | null;
};

export function ChapterSplit({
  source,
  chapterIdx,
  chapterTitle,
  chapterSummary,
  chapterNumber,
  text,
  prevIdx,
  nextIdx,
  initialMode,
  progress,
}: Props) {
  const seekRef = useRef<((seconds: number) => void) | null>(null);
  const isVideo = source.kind === "video";

  return (
    <ReaderSplit sourceUid={source.uid} chapterIdx={chapterIdx} seekRef={seekRef}>
      {({ openChat }) =>
        isVideo ? (
          <VideoStudy
            sourceUid={source.uid}
            videoId={(source.meta?.video_id as string | undefined) ?? null}
            url={source.url}
            title={chapterTitle || source.title}
            seekRef={seekRef}
            onAsk={(t) => openChat({ text: t, nonce: Date.now() })}
            onDiscuss={() => openChat()}
          />
        ) : (
          <ChapterReader
            sourceUid={source.uid}
            sourceTitle={source.title}
            chapter={{
              idx: chapterIdx,
              title: chapterTitle,
              summary: chapterSummary,
              number: chapterNumber,
            }}
            text={text}
            prevIdx={prevIdx}
            nextIdx={nextIdx}
            isBook={source.kind === "book"}
            initialMode={initialMode}
            progress={progress}
            onDiscuss={(t) => openChat({ text: t, nonce: Date.now() })}
          />
        )
      }
    </ReaderSplit>
  );
}
