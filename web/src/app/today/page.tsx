/** «Сегодня»: что делать дальше — продолжить, повторения, входящие, источники (B-005). */

import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { api } from "@/lib/api";
import type { TodaySnapshot } from "@/lib/types";
import { StartItemButton } from "@/components/today/today-actions";
import { Progress } from "@/components/ui/progress";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  const today = await api<TodaySnapshot>("/today").catch(() => null);

  if (!today) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <h1 className="text-xl font-bold">Сегодня</h1>
        <p className="mt-4 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Ядро недоступно — обнови страницу.
        </p>
      </div>
    );
  }

  const readingProgress = today.reading[0];

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <header className="mb-5">
        <h1 className="text-xl font-bold">Сегодня</h1>
        <p className="text-sm text-muted-foreground">
          {new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Продолжить: активная сессия → следующий элемент курса → незаконченная книга */}
        <section className="rounded-xl border bg-card p-4 sm:col-span-2">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Icon name="play_circle" size={14} className="text-primary" /> Продолжить
          </p>
          {today.active_session ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">Идёт сессия-урок{today.active_session.chapter_idx ? ` · глава ${today.active_session.chapter_idx}` : ""}</p>
                <p className="text-sm text-muted-foreground">
                  начата {new Date(today.active_session.started_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
              {today.active_session.conversation_uid && (
                <Link
                  href={`/chat/${today.active_session.conversation_uid}`}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
                >
                  <Icon name="smart_toy" size={16} /> Вернуться в урок
                </Link>
              )}
            </div>
          ) : today.next_course_items.length > 0 ? (
            <ul className="flex flex-col gap-2">
              {today.next_course_items.map((it) => (
                <li key={`${it.course_uid}:${it.item_id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{it.title}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {it.course_title} · {it.hint}
                    </p>
                  </div>
                  <StartItemButton courseUid={it.course_uid} itemId={it.item_id} />
                </li>
              ))}
            </ul>
          ) : readingProgress ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{readingProgress.title}</p>
                <div className="mt-2 max-w-sm">
                  <Progress value={readingProgress.total_chapters ? (readingProgress.cursor_chapter / (readingProgress.total_chapters + 1)) * 100 : 0} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  глава {readingProgress.cursor_chapter} из {readingProgress.total_chapters}
                </p>
              </div>
              <Link
                href={`/library/${readingProgress.source_uid}/read`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
              >
                <Icon name="auto_stories" size={16} /> Читать дальше
              </Link>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
              Незаконченных дел нет. Начни{" "}
              <Link href="/chat" className="text-primary hover:underline">
                разговор
              </Link>{" "}
              или собери{" "}
              <Link href="/chat" className="text-primary hover:underline">
                курс
              </Link>
              .
            </p>
          )}
        </section>

        {/* Повторения на сегодня */}
        <Link
          href="/review"
          className="group rounded-xl border bg-card p-4 transition hover:border-primary/50"
        >
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Icon name="replay" size={14} className="text-primary" /> Повторения
          </p>
          <p className="text-3xl font-bold">{today.review.due_today}</p>
          <p className="text-sm text-muted-foreground">
            {today.review.due_today > 0 ? "назрело на сегодня — повторить" : "назревших нет — знания отдыхают"}
          </p>
        </Link>

        {/* Входящие KB */}
        <Link
          href="/kb?view=inbox"
          className="group rounded-xl border bg-card p-4 transition hover:border-primary/50"
        >
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Icon name="inbox" size={14} className="text-primary" /> Входящие базы
          </p>
          <p className="text-3xl font-bold">{today.inbox_count}</p>
          <p className="text-sm text-muted-foreground">
            {today.inbox_count > 0 ? "черновики ждут сессии-проговора" : "входящих нет"}
          </p>
        </Link>

        {/* Источники в обработке / с ошибкой */}
        {today.sources_attention.length > 0 && (
          <section className="rounded-xl border bg-card p-4 sm:col-span-2">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <Icon name="error" size={14} className="text-amber-600 dark:text-amber-400" /> Источники требуют внимания
            </p>
            <ul className="flex flex-col gap-1.5">
              {today.sources_attention.map((s) => (
                <li key={s.source_uid} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <Link href={`/library/${s.source_uid}`} className="min-w-0 truncate font-medium hover:underline">
                    {s.title}
                  </Link>
                  <span className={s.status === "failed" ? "text-destructive" : "text-muted-foreground"}>
                    {s.status === "failed" ? `ошибка: ${(s.last_error ?? "").slice(0, 80)}` : "обрабатывается…"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
