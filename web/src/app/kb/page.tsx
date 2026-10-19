/** База знаний: дерево категорий, входящие, фильтры, сетка блоков. */

import Link from "next/link";
import { AlertTriangle, Inbox } from "lucide-react";
import { api } from "@/lib/api";
import type { BlockCard, CategoryNode } from "@/lib/types";
import { CategoryTree } from "@/components/kb/category-tree";
import { CategoryDrawer } from "@/components/kb/category-drawer";
import { BlockCard as BlockCardView } from "@/components/kb/block-card";
import { InboxPanel } from "@/components/kb/inbox";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export const dynamic = "force-dynamic";

type Props = {
  searchParams: Promise<{ category?: string; q?: string; kind?: string; status?: string; view?: string }>;
};

export default async function KbPage({ searchParams }: Props) {
  const sp = await searchParams;
  const qs = new URLSearchParams();
  if (sp.category) qs.set("category", sp.category);
  if (sp.q) qs.set("q", sp.q);
  if (sp.kind) qs.set("kind", sp.kind);

  const [blocks, categories, inbox] = await Promise.all([
    api<BlockCard[]>(`/kb/blocks?${qs.toString()}`).catch(() => [] as BlockCard[]),
    api<CategoryNode[]>("/kb/categories").catch(() => [] as CategoryNode[]),
    api<BlockCard[]>("/kb/inbox").catch(() => [] as BlockCard[]),
  ]);

  return (
    <div className="flex h-full">
      {/* на планшете дерево уходит в диалог-кнопку, на широких — колонка слева */}
      <div className="hidden w-60 shrink-0 overflow-y-auto border-r p-3 lg:block">
        <CategoryTree nodes={categories} active={sp.category ?? null} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6">
        <header className="mb-4 flex flex-wrap items-center gap-2 sm:gap-3">
          <CategoryDrawer nodes={categories} active={sp.category ?? null} />
          <h1 className="min-w-0 truncate text-xl font-semibold">
            {sp.category ? `Категория: ${sp.category}` : "База знаний"}
          </h1>
          {inbox.length > 0 && (
            <Link href="/kb?view=inbox">
              <Badge variant="secondary" className="gap-1">
                <Inbox className="h-3 w-3" /> Входящие: {inbox.length}
              </Badge>
            </Link>
          )}
          <form className="ml-auto flex items-center gap-2" action="/kb">
            {sp.category && <input type="hidden" name="category" value={sp.category} />}
            <Input name="q" defaultValue={sp.q ?? ""} placeholder="Поиск…" className="h-9 w-36 sm:w-56" />
            <select
              name="kind"
              defaultValue={sp.kind ?? ""}
              className="h-9 rounded-md border bg-background px-2 text-sm"
              aria-label="Тип блока"
            >
              <option value="">все</option>
              <option value="lesson">уроки</option>
              <option value="note">конспекты</option>
            </select>
          </form>
        </header>

        {sp.view === "inbox" && (
          <section className="mb-6">
            <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Inbox className="h-4 w-4" /> Входящие — подтвердите категорию
            </h2>
            <InboxPanel blocks={inbox} categories={categories} />
          </section>
        )}

        {blocks.length === 0 ? (
          <div className="rounded-xl border border-dashed p-12 text-center text-muted-foreground">
            <AlertTriangle className="mx-auto mb-3 h-8 w-8 opacity-40" />
            <p className="font-medium text-foreground">Здесь пока пусто</p>
            <p className="mt-1 text-sm">
              Блок рождается только через разговор с агентом:{" "}
              <Link href="/chat" className="text-violet-500 hover:underline">
                начни быстрый разбор или сессию
              </Link>
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {blocks.map((b) => (
              <BlockCardView key={b.block_uid} block={b} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
