/** Единственный ридер книги (B-013): PDF + text-layer + чат главы справа.
 *  Место чтения (глава+страница) живёт в активности — «Сегодня» и повторный
 *  вход открывают его; URL ?ch=&page= всё перекрывает (ссылкой можно поделиться). */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { ActivityCard, SourceDetail } from "@/lib/types";
import { PdfStudy } from "@/components/library/pdf-study";

export const dynamic = "force-dynamic";

export default async function PdfReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ uid: string }>;
  searchParams?: Promise<{ ch?: string; page?: string; discuss?: string }>;
}) {
  const { uid } = await params;
  const sp = searchParams ? await searchParams : undefined;
  let source: SourceDetail;
  let activity: ActivityCard | undefined;
  try {
    source = await api<SourceDetail>(`/sources/${uid}`);
    activity = (
      await api<ActivityCard[]>("/activities?status=active").catch(() => [] as ActivityCard[])
    ).find((a) => a.source_uid === source.uid);
  } catch {
    notFound();
  }
  if (source.kind !== "book") notFound();

  // приоритет места: URL > сохранённое место активности > глава 1
  const urlCh = Number(sp?.ch);
  const urlPage = Number(sp?.page);
  const initialChapter =
    Number.isFinite(urlCh) && urlCh > 0 ? urlCh : activity?.position_chapter ?? activity?.cursor_chapter ?? 1;
  const initialPage =
    Number.isFinite(urlPage) && urlPage > 0 ? urlPage : (sp?.ch === undefined ? activity?.position_page ?? null : null);

  return (
    <PdfStudy
      sourceUid={source.uid}
      sourceTitle={source.title}
      chapters={(source.chapters ?? []).map((c) => ({
        idx: c.idx,
        title: c.title,
        number: c.number ?? null,
      }))}
      initialChapter={initialChapter}
      initialPage={initialPage}
      activityUid={activity?.uid ?? null}
      initialCursor={activity?.cursor_chapter ?? 1}
      initialDiscuss={sp?.discuss === "review" ? REVIEW_STARTER : null}
    />
  );
}

const REVIEW_STARTER =
  "Разбери эту главу со мной: покажи главное карточкой разбора (3–5 пунктов), ключевые понятия " +
  "и 1–2 вопроса на подумать. Веди по главе сам — я не читал(а) её целиком.";
