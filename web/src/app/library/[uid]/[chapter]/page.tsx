/** Читалка главы с split-view: материал слева, обсуждение справа (B-006). */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { ActivityCard, SourceDetail } from "@/lib/types";
import { ChapterSplit } from "@/components/library/chapter-split";

export const dynamic = "force-dynamic";

export default async function ChapterReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ uid: string; chapter: string }>;
  searchParams?: Promise<{ mode?: string }>;
}) {
  const { uid, chapter } = await params;
  const sp = searchParams ? await searchParams : undefined;
  const idx = Number(chapter);
  let source: SourceDetail;
  let text: string;
  try {
    source = await api<SourceDetail>(`/sources/${uid}`);
    // полный текст главы (лимит с запасом; читалка — единственное место, где нужен весь)
    const part = await api<{ text: string }>(`/sources/${uid}/chapters/${idx}?limit=1000000`);
    text = part.text;
  } catch {
    notFound();
  }
  const ch = (source.chapters ?? []).find((c) => c.idx === idx);
  const prev = (source.chapters ?? []).find((c) => c.idx === idx - 1);
  const next = (source.chapters ?? []).find((c) => c.idx === idx + 1);
  // курсор активной активности — для «Прочитал»; одноглавые материалы (видео/статьи) кнопку не получают
  const activity = (
    await api<ActivityCard[]>("/activities?status=active").catch(() => [] as ActivityCard[])
  ).find((a) => a.source_uid === source.uid);
  const progress =
    activity && (source.chapters ?? []).length > 1
      ? { cursor: activity.cursor_chapter, total: activity.total_chapters }
      : null;

  return (
    <ChapterSplit
      source={source}
      chapterIdx={idx}
      chapterTitle={ch?.title ?? `Глава ${idx}`}
      chapterSummary={ch?.summary ?? null}
      chapterNumber={ch?.number ?? null}
      text={text}
      prevIdx={prev?.idx ?? null}
      nextIdx={next?.idx ?? null}
      initialMode={sp?.mode ?? null}
      progress={progress}
    />
  );
}
