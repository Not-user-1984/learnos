/** Страница курса: доска статусов с действиями по элементам (B-005). */

import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import type { Course } from "@/lib/types";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { CourseBoard } from "@/components/courses/course-board";

export const dynamic = "force-dynamic";

export default async function CoursePage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  let course: Course;
  try {
    course = await api<Course>(`/courses/${uid}`);
  } catch {
    notFound();
  }
  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold">{course.title}</h1>
          {course.description && <p className="mt-1 text-sm text-muted-foreground">{course.description}</p>}
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
      </header>
      <CourseBoard course={course} />
    </div>
  );
}
