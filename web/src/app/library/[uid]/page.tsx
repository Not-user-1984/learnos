/** Страница источника: обзор на всю ширину экрана, главы с полными описаниями. */

import Link from "next/link";
import { notFound } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { kindIcon } from "@/lib/format";
import { api } from "@/lib/api";
import type { ActivityCard, ChapterCard, SourceDetail } from "@/lib/types";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { SourceActions } from "@/components/library/source-actions";
import { ChapterHistoryButton } from "@/components/library/chapter-history";
import { Badge } from "@/components/ui/badge";

export const dynamic = "force-dynamic";

/** Имя файла с подчёркиваниями → читаемое название; исходник остаётся в title. */
function prettyTitle(title: string): string {
  return title.replace(/_/g, " ");
}

/** Заголовок главы: позиционный номер + название без собственной нумерации (иначе «3. 1. Приложения»). */
function chapterLabel(idx: number, title: string): string {
  const inner = title.replace(/^\s*\d+[.)]?\s+/, "");
  return `${idx}. ${inner || title}`;
}

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
      <div className="mx-auto w-full max-w-3xl px-4 py-5 sm:px-6 sm:py-6 lg:max-w-4xl xl:max-w-6xl 2xl:max-w-7xl">
        <header className="mb-5 flex flex-wrap items-start gap-x-3 gap-y-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/15 to-primary/25 text-primary-foreground sm:h-14 sm:w-14">
            <Icon name={kindIcon(source.kind)} size={30} />
          </div>
          <div className="min-w-0 flex-1 basis-56">
            <h1
              className="text-lg font-bold leading-snug break-words [overflow-wrap:anywhere] sm:text-xl"
              title={source.title}
            >
              {prettyTitle(source.title)}
            </h1>
            <p className="text-sm text-muted-foreground">
              {source.status === "processed" ? `обработан · ${chapters.length} гл.` : source.status}
              {source.url && (
                <>
                  {" · "}
                  <a className="text-primary hover:underline" href={source.url} target="_blank" rel="noreferrer">
                    источник
                  </a>
                </>
              )}
            </p>
          </div>
          <SourceActions sourceUid={source.uid} className="ml-auto" />
        </header>

        {activity && (
          <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm">
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
          <p className="mb-5 rounded-xl border bg-card p-3 text-sm leading-relaxed text-muted-foreground sm:p-4">
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
                <div className="flex flex-wrap items-start gap-x-2 gap-y-2 py-3">
                  <Icon name="book_2" size={16} className="mt-1 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1 basis-64">
                    <div className="flex flex-wrap items-center gap-x-2">
                      <Link
                        href={`/library/${source.uid}/${ch.idx}`}
                        className="font-medium hover:text-primary hover:underline"
                      >
                        {chapterLabel(ch.idx, ch.title)}
                      </Link>
                      {ch.has_exercises && <Badge variant="secondary">упражнения</Badge>}
                    </div>
                    {ch.summary && (
                      <p className="mt-1 text-sm leading-relaxed text-muted-foreground line-clamp-3 sm:line-clamp-none">
                        {ch.summary}
                      </p>
                    )}
                  </div>
                  <span className="ml-auto flex shrink-0 flex-wrap items-center gap-1.5">
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
