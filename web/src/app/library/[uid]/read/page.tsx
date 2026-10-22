/** Полноэкранный PDF-ридер книги: server-light — данные книги отдаёт API,
 *  вся механика (страницы, оглавление, яркость, клавиатура) — клиентская. */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { SourceDetail } from "@/lib/types";
import { PdfReader } from "@/components/library/pdf-reader";

export const dynamic = "force-dynamic";

export default async function PdfReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ uid: string }>;
  searchParams?: Promise<{ ch?: string; page?: string }>;
}) {
  const { uid } = await params;
  const sp = searchParams ? await searchParams : undefined;
  let source: SourceDetail;
  try {
    source = await api<SourceDetail>(`/sources/${uid}`);
  } catch {
    notFound();
  }
  if (source.kind !== "book") notFound();

  const ch = Number(sp?.ch) || 1;
  const page = Number(sp?.page);

  return (
    <PdfReader
      sourceUid={source.uid}
      sourceTitle={source.title}
      chapters={(source.chapters ?? []).map((c) => ({ idx: c.idx, title: c.title }))}
      initialChapter={ch}
      initialPage={Number.isFinite(page) && page > 0 ? page : null}
    />
  );
}
