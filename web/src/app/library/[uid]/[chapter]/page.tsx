/** Читалка главы: prose-текст с навигацией. */

import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import type { SourceDetail } from "@/lib/types";
import { Markdown } from "@/components/markdown/Markdown";
import { SourceActions } from "@/components/library/source-actions";

export const dynamic = "force-dynamic";

export default async function ChapterReader({ params }: { params: Promise<{ uid: string; chapter: string }> }) {
  const { uid, chapter } = await params;
  const idx = Number(chapter);
  let source: SourceDetail;
  let text: string;
  try {
    source = await api<SourceDetail>(`/sources/${uid}`);
    const part = await api<{ text: string }>(`/sources/${uid}/chapters/${idx}`);
    text = part.text;
  } catch {
    notFound();
  }
  const ch = (source.chapters ?? []).find((c) => c.idx === idx);
  const prev = (source.chapters ?? []).find((c) => c.idx === idx - 1);
  const next = (source.chapters ?? []).find((c) => c.idx === idx + 1);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <Link href={`/library/${uid}`} className="mb-4 inline-flex items-center gap-1 text-sm text-violet-500 hover:underline">
          <ChevronLeft className="h-4 w-4" /> {source.title}
        </Link>
        <h1 className="mb-2 text-2xl font-bold">
          {idx}. {ch?.title ?? `Глава ${idx}`}
        </h1>
        {ch?.summary && <p className="mb-6 text-muted-foreground">{ch.summary}</p>}
        <SourceActions sourceUid={uid} chapterIdx={idx} chapterTitle={ch?.title} />
        <div className="mt-6">
          <Markdown content={text} />
        </div>
        <nav className="mt-10 flex items-center justify-between border-t pt-4">
          {prev ? (
            <Link href={`/library/${uid}/${prev.idx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
              <ChevronLeft className="h-4 w-4" /> Глава {prev.idx}
            </Link>
          ) : (
            <span />
          )}
          {next && (
            <Link href={`/library/${uid}/${next.idx}`} className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm hover:bg-accent">
              Глава {next.idx} <ChevronRight className="h-4 w-4" />
            </Link>
          )}
        </nav>
      </div>
    </div>
  );
}
