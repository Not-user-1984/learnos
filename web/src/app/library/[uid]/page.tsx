/** Страница источника: обзор, главы, действия. */

import Link from "next/link";
import { notFound } from "next/navigation";
import { BookMarked } from "lucide-react";
import { api } from "@/lib/api";
import type { ChapterCard, SourceDetail } from "@/lib/types";
import { SourceActions } from "@/components/library/source-actions";
import { Badge } from "@/components/ui/badge";

export const dynamic = "force-dynamic";

export default async function SourcePage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let source: SourceDetail;
  try {
    source = await api<SourceDetail>(`/sources/${uid}`);
  } catch {
    notFound();
  }
  const chapters: ChapterCard[] = source.chapters ?? [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-6 flex flex-wrap items-start gap-3">
        <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-3xl">
          {source.kind === "book" ? "📕" : source.kind === "video" ? "🎬" : "🌐"}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-bold">{source.title}</h1>
          <p className="text-sm text-muted-foreground">
            {source.status === "processed" ? `обработан · ${chapters.length} гл.` : source.status}
            {source.url && (
              <>
                {" · "}
                <a className="text-violet-500 hover:underline" href={source.url} target="_blank" rel="noreferrer">
                  источник
                </a>
              </>
            )}
          </p>
          {source.summary && <p className="mt-2 max-w-3xl text-sm">{source.summary}</p>}
        </div>
        <SourceActions sourceUid={source.uid} />
      </header>

      {chapters.length === 0 ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Глав пока нет — запусти обработку или дождись задачи.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {chapters.map((ch) => (
            <section key={ch.idx} className="rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-center gap-2">
                <BookMarked className="h-4 w-4 text-muted-foreground" />
                <h2 className="font-medium">
                  {ch.idx}. {ch.title}
                </h2>
                {ch.has_exercises && <Badge variant="secondary">есть упражнения</Badge>}
                {ch.tokens_est && <span className="text-xs text-muted-foreground">~{ch.tokens_est} ток.</span>}
                <span className="ml-auto flex items-center gap-2">
                  <Link href={`/library/${source.uid}/${ch.idx}`} className="text-sm text-violet-500 hover:underline">
                    Читать
                  </Link>
                  <SourceActions sourceUid={source.uid} chapterIdx={ch.idx} chapterTitle={ch.title} />
                </span>
              </div>
              {ch.summary && <p className="mt-2 text-sm text-muted-foreground">{ch.summary}</p>}
              {ch.key_points?.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {ch.key_points.map((kp, i) => (
                    <li key={i}>{kp}</li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
