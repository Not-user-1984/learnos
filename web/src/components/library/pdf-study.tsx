"use client";

/** Чтение книги с чатом главы (B-013): PdfReader слева, чат текущей главы справа
 *  (≥1024px — колонка, на мобиле — шторка снизу). Ключ чата = глава, поэтому
 *  при перелистывании на следующую главу разговор открывается заново. */

import { useCallback, useState } from "react";
import { ReaderSplit } from "./reader-split";
import { PdfReader } from "./pdf-reader";

type Chapter = { idx: number; title: string; number?: number | null };

type Props = {
  sourceUid: string;
  sourceTitle: string;
  chapters: Chapter[];
  initialChapter: number;
  initialPage: number | null;
  activityUid: string | null;
  initialCursor: number;
  initialDiscuss: string | null;
};

export function PdfStudy({
  sourceUid,
  sourceTitle,
  chapters,
  initialChapter,
  initialPage,
  activityUid,
  initialCursor,
  initialDiscuss,
}: Props) {
  const [chapter, setChapter] = useState(initialChapter);
  const onChapterChange = useCallback((idx: number) => setChapter(idx), []);

  return (
    <ReaderSplit sourceUid={sourceUid} chapterIdx={chapter}>
      {({ openChat }) => (
        <PdfReader
          sourceUid={sourceUid}
          sourceTitle={sourceTitle}
          chapters={chapters}
          initialChapter={initialChapter}
          initialPage={initialPage}
          activityUid={activityUid}
          initialCursor={initialCursor}
          initialDiscuss={initialDiscuss}
          onChapterChange={onChapterChange}
          onDiscuss={(text) => openChat(text ? { text, nonce: Date.now() } : undefined)}
        />
      )}
    </ReaderSplit>
  );
}
