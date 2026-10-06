import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { stripFrontmatter, type Block, type Course } from "@/lib/types";
import { Markdown } from "@/components/Markdown";

export const dynamic = "force-dynamic";

export default async function BlockPage({ params }: { params: Promise<{ uid: string }> }) {
  const { uid } = await params;
  const block = await api<Block>(`/api/blocks/${encodeURIComponent(uid)}`).catch(() => null);
  if (!block || !("block_uid" in block) || !block.block_uid) notFound();

  const course = await api<Course[]>("/api/courses").then(
    (courses) => courses.find((c) => c.id === block.course_id) ?? null,
  );

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <nav className="mb-6 text-sm text-zinc-500">
        <Link href="/" className="hover:text-zinc-300">
          ← база знаний
        </Link>
      </nav>

      <header className="mb-8">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          {course && (
            <span className="rounded-full bg-sky-500/15 px-2.5 py-1 text-sky-300">{course.topic}</span>
          )}
          <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-emerald-300">
            пройден {new Date(block.created_at).toLocaleDateString("ru-RU")}
          </span>
          {block.tags.map((t) => (
            <span key={t} className="rounded bg-white/5 px-2 py-1 font-mono text-zinc-400">
              #{t}
            </span>
          ))}
        </div>
        <h1 className="text-3xl font-bold">{block.title}</h1>
        {block.sources.length > 0 && (
          <p className="mt-2 text-xs text-zinc-600">
            источники: {block.sources.join(" · ")}
          </p>
        )}
      </header>

      <article className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <Markdown text={stripFrontmatter(block.content)} />
      </article>

      <footer className="mt-6 flex items-center justify-between text-xs text-zinc-600">
        <span className="font-mono">{block.block_uid}</span>
        <span>
          сессия #{block.session_id} · курс #{block.course_id}
        </span>
      </footer>
    </main>
  );
}
