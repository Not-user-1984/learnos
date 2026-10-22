/** Страница курса: элементы с прогрессом, следующий шаг. */

import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { Course } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { ConfirmDeleteButton } from "@/components/confirm-delete";

export const dynamic = "force-dynamic";

export default async function CoursePage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let course: Course;
  try {
    course = await api<Course>(`/courses/${uid}`);
  } catch {
    notFound();
  }
  const items = course.items ?? [];
  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-bold">{course.title}</h1>
            <p className="text-sm text-muted-foreground">
              {course.topic} · {course.items_done}/{course.items_count} пройдено
            </p>
          </div>
          <ConfirmDeleteButton
            endpoint={`/courses/${course.uid}`}
            title="Удалить курс?"
            name={course.title}
            description="Курс и его элементы удалятся. Источники и блоки базы знаний останутся в библиотеке и базе знаний."
            successMessage="Курс удалён"
            redirectTo="/courses"
            appearance="button"
            label="Удалить курс"
          />
        </div>
        <div className="mt-3 h-2 max-w-md overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-violet-500" style={{ width: `${course.items_count ? (course.items_done / course.items_count) * 100 : 0}%` }} />
        </div>
      </header>

      {course.next_step && (
        <div className="mb-6 rounded-xl border border-violet-500/40 bg-violet-500/5 p-4">
          <p className="text-sm font-medium">Следующий шаг</p>
          <p className="mt-1">
            {course.next_step.title} <span className="text-muted-foreground">— {course.next_step.hint}</span>
          </p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <div key={item.id} className="flex items-center gap-3 rounded-xl border bg-card p-4">
            <span className={item.done ? "text-emerald-500" : "text-muted-foreground"}>{item.done ? "✓" : "○"}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{item.title}</p>
              {item.note && <p className="truncate text-xs text-muted-foreground">{item.note}</p>}
            </div>
            <Badge variant="outline">
              {item.item_type === "source" ? "источник" : item.item_type === "chapter" ? "глава" : "блок"}
            </Badge>
            {item.item_type === "block" && item.block_uid && (
              <Link href={`/kb/${item.block_uid}`} className="text-sm text-violet-500 hover:underline">
                открыть
              </Link>
            )}
          </div>
        ))}
        {items.length === 0 && (
          <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
            Пусто: добавь источники, главы и блоки из библиотеки и базы знаний.
          </p>
        )}
      </div>
    </div>
  );
}
