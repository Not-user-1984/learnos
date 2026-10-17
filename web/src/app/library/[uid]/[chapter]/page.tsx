/** Читалка главы: полный текст, e-book типографика, обсуждение с агентом. */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { SourceDetail } from "@/lib/types";
import { ChapterReader } from "@/components/library/reader";

export const dynamic = "force-dynamic";

export default async function ChapterReaderPage({ params }: { params: Promise<{ uid: string; chapter: string }> }) {
  const { uid, chapter } = await params;
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

  return (
    <ChapterReader
      sourceUid={uid}
      sourceTitle={source.title}
      chapter={{ idx, title: ch?.title ?? `Глава ${idx}`, summary: ch?.summary ?? null }}
      text={text}
      prevIdx={prev?.idx ?? null}
      nextIdx={next?.idx ?? null}
    />
  );
}
