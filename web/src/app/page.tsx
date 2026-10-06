import Link from "next/link";
import { api } from "@/lib/api";
import { parseSources, parseTags, type BlockRow, type Course } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [blocks, courses] = await Promise.all([
    api<BlockRow[]>("/api/blocks"),
    api<Course[]>("/api/courses"),
  ]);
  const courseById = new Map(courses.map((c) => [c.id, c]));

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">
          LearnOS <span className="text-zinc-500">· база знаний</span>
        </h1>
        <span className="text-sm text-zinc-500">
          {blocks.length > 0 ? `${blocks.length} блок(ов)` : "пока пусто"}
        </span>
      </header>

      {blocks.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 p-12 text-center">
          <p className="text-lg font-medium">База знаний пуста</p>
          <p className="mt-2 text-sm text-zinc-400">
            Блок рождается только через завершённую учебную сессию.
            <br />
            Запусти петлю: курс → сессия → проговор → блок.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {blocks.map((b) => {
            const course = courseById.get(b.course_id);
            const tags = parseTags(b);
            const sources = parseSources(b);
            return (
              <Link
                key={b.block_uid}
                href={`/blocks/${b.block_uid}`}
                className="group rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-white/25 hover:bg-white/[0.06]"
              >
                <div className="mb-2 flex items-center gap-2 text-xs text-zinc-500">
                  <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-sky-300">
                    {course?.topic ?? `курс #${b.course_id}`}
                  </span>
                  <span>{new Date(b.created_at).toLocaleDateString("ru-RU")}</span>
                </div>
                <h2 className="mb-2 text-lg font-semibold group-hover:text-white">{b.title}</h2>
                {tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {tags.map((t) => (
                      <span key={t} className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-xs text-zinc-400">
                        #{t}
                      </span>
                    ))}
                  </div>
                )}
                {sources.length > 0 && (
                  <div className="mt-2 text-xs text-zinc-600">{sources.join(", ")}</div>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}
