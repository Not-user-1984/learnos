/** Курсы: список с прогрессом + создание (вручную/агентом). */

import Link from "next/link";
import { GraduationCap } from "lucide-react";
import { api } from "@/lib/api";
import type { Course } from "@/lib/types";
import { NewCourseButton } from "@/components/courses/new-course";

export const dynamic = "force-dynamic";

export default async function CoursesPage() {
  const courses = await api<Course[]>("/courses").catch(() => [] as Course[]);
  return (
    <div className="h-full overflow-y-auto p-6">
      <header className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Курсы</h1>
        <NewCourseButton />
      </header>
      {courses.length === 0 ? (
        <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
          <GraduationCap className="mx-auto mb-3 h-8 w-8 opacity-40" />
          <p className="font-medium text-foreground">Курсов нет</p>
          <p className="mt-1 text-sm">Курс — подборка источников и блоков по теме. Можно собрать вручную или поручить агенту.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {courses.map((c) => (
            <Link key={c.uid} href={`/courses/${c.uid}`} className="rounded-xl border bg-card p-4 transition hover:border-violet-500/50">
              <p className="font-medium">{c.title}</p>
              <p className="text-sm text-muted-foreground">{c.topic}</p>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-violet-500" style={{ width: `${c.items_count ? (c.items_done / c.items_count) * 100 : 0}%` }} />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {c.items_done}/{c.items_count} пройдено
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
