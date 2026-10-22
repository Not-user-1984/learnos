/** Страница источника: компактный обзор, главы с историей разговоров. */

import Link from "next/link";
import { notFound } from "next/navigation";
import { BookMarked } from "lucide-react";
import { kindEmoji } from "@/lib/format";
import { api } from "@/lib/api";
import type { ActivityCard, ChapterCard, SourceDetail } from "@/lib/types";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { SourceActions } from "@/components/library/source-actions";
import { ChapterHistoryButton } from "@/components/library/chapter-history";
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
  const activity: ActivityCard | undefined = (
    await api<ActivityCard[]>("/activities?status=active").catch(() => [] as ActivityCard[])
  ).find((a) => a.source_uid === source.uid);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-5 sm:px-6 sm:py-6">
        <header className="mb-5 flex flex-wrap items-start gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500/20 to-violet-500/20 text-2xl sm:h-14 sm:w-14 sm:text-3xl">
            {kindEmoji(source.kind)}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-bold leading-snug sm:text-xl">{source.title}</h1>
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
          </div>
          <SourceActions sourceUid={source.uid} />
        </header>

        {activity && (
          <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-violet-500/30 bg-violet-500/5 p-3 text-sm">
            <p className="font-medium">
              Изучение идёт: глава {activity.cursor_chapter}
              {activity.total_chapters > 0 && ` из ${activity.total_chapters}`}
            </p>
            <ConfirmDeleteButton
              endpoint={`/activities/${activity.uid}`}
              title="Прекратить изучение?"
              description="Активность и курсор прогресса удалятся, разговоры останутся в истории. Если по активности есть сессии — удаление будет запрещено."
              successMessage="Изучение прекращено"
              appearance="button"
              label="Прекратить"
              className="ml-auto"
            />
          </div>
        )}

        {source.summary && (
          <p className="mb-5 line-clamp-3 rounded-xl border bg-card p-3 text-sm leading-relaxed text-muted-foreground">
            {source.summary}
          </p>
        )}

        {chapters.length === 0 ? (
          <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
            Глав пока нет — запусти обработку или дождись задачи.
          </p>
        ) : (
          <ol className="flex flex-col">
            {chapters.map((ch) => (
              <li key={ch.idx} className="border-b last:border-b-0">
                <div className="flex items-start gap-2 py-3">
                  <BookMarked className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2">
                      <Link href={`/library/${source.uid}/${ch.idx}`} className="font-medium hover:text-violet-500 hover:underline">
                        {ch.idx}. {ch.title}
                      </Link>
                      {ch.has_exercises && <Badge variant="secondary">упражнения</Badge>}
                    </div>
                    {ch.summary && (
                      <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{ch.summary}</p>
                    )}
                  </div>
                  <span className="ml-auto flex shrink-0 items-center gap-1.5">
                    <ChapterHistoryButton sourceUid={source.uid} chapterIdx={ch.idx} chapterTitle={ch.title} size="icon" />
                    <Link
                      href={`/library/${source.uid}/${ch.idx}`}
                      className="rounded-md border px-2.5 py-1.5 text-sm hover:bg-accent"
                    >
                      Читать
                    </Link>
                    <SourceActions sourceUid={source.uid} chapterIdx={ch.idx} chapterTitle={ch.title} />
                  </span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
