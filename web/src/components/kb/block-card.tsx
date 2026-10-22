"use client";

/** Карточка блока в сетке базы знаний. */

import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import type { BlockCard } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { CATEGORY_COLORS } from "./category-tree";

export function BlockCard({ block }: { block: BlockCard }) {
  const src = block.sources[0];
  return (
    <Link
      href={`/kb/${block.block_uid}`}
      className="group relative flex flex-col gap-2 overflow-hidden rounded-xl border bg-card p-4 transition hover:border-violet-500/50"
    >
      {block.category_path && (
        <span className={`absolute inset-y-0 left-0 w-1 ${CATEGORY_COLORS[_rootColor(block.category_path)]}`} />
      )}
      <div className="flex items-start justify-between gap-2 pl-2">
        <h3 className="line-clamp-2 font-medium leading-tight">{block.title}</h3>
        {block.version > 1 && <Badge variant="secondary" className="shrink-0">v{block.version}</Badge>}
      </div>
      {block.summary && <p className="line-clamp-2 pl-2 text-sm text-muted-foreground">{block.summary}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 pl-2 text-xs text-muted-foreground">
        <Badge variant="outline">{block.kind === "lesson" ? "урок" : "конспект"}</Badge>
        {src && (
          <span className="inline-flex items-center gap-1">
            {src.source.startsWith("src") ? <Icon name="book_2" size={12} /> : <Icon name="movie" size={12} />}
            {src.title || src.source}
          </span>
        )}
        {block.weak_spots_count > 0 && (
          <span className="inline-flex items-center gap-1 text-amber-500">
            <Icon name="warning" size={12} />
            {block.weak_spots_count}
          </span>
        )}
        <span className="ml-auto">{new Date(block.created_at).toLocaleDateString("ru-RU")}</span>
      </div>
    </Link>
  );
}

function _rootColor(path: string): string {
  // цвет наследуется от корня пути; фронт не знает цветов подузлов — используем карту по первому сегменту
  const roots: Record<string, string> = { programming: "sky", infra: "emerald", life: "amber" };
  return roots[path.split("/")[0]] ?? "violet";
}
