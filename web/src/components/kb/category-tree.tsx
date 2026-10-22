"use client";

/** Дерево категорий со счётчиками (включая подкатегории) и живым поиском по названию/пути:
 *  при вводе показываются совпавшие узлы вместе с родителями, всё раскрыто. */

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { filterCategoryTree } from "@/lib/categories";
import type { CategoryNode } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CATEGORY_COLORS: Record<string, string> = {
  sky: "bg-sky-500",
  primary: "bg-primary",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  zinc: "bg-zinc-500",
};

export function CategoryTree({ nodes, active }: { nodes: CategoryNode[]; active: string | null }) {
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
  const filtered = searching ? filterCategoryTree(nodes, query) : nodes;

  return (
    <div className="flex flex-col gap-1">
      <div className="relative">
        <Icon
          name="search"
          size={14}
          className="pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск категорий…"
          aria-label="Поиск по категориям"
          className="h-8 pl-7 text-sm"
        />
      </div>
      <div className="flex flex-col gap-0.5">
        <Link
          href="/kb"
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
            !active && "bg-accent/60",
          )}
        >
          <Icon name="inbox" size={14} className="text-muted-foreground" />
          Все блоки
        </Link>
        {filtered.map((n) => (
          <Node key={n.path} node={n} active={active} depth={0} searching={searching} />
        ))}
        {searching && filtered.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            Ничего не найдено по «{query.trim()}»
          </p>
        )}
      </div>
    </div>
  );
}

function Node({
  node,
  active,
  depth,
  searching,
}: {
  node: CategoryNode;
  active: string | null;
  depth: number;
  searching: boolean;
}) {
  const [open, setOpen] = useState(depth < 1);
  const expanded = searching || open;
  const isActive = active === node.path;
  return (
    <div>
      <div className="flex items-center gap-1" style={{ paddingLeft: depth * 12 }}>
        {!searching && node.children.length > 0 ? (
          <button aria-label="Раскрыть" onClick={() => setOpen((v) => !v)} className="rounded p-0.5 hover:bg-accent">
            {expanded ? <Icon name="expand_more" size={14} className="text-muted-foreground" /> : <Icon name="chevron_right" size={14} className="text-muted-foreground" />}
          </button>
        ) : (
          <span className="w-5" />
        )}
        <Link
          href={`/kb?category=${encodeURIComponent(node.path)}`}
          className={cn(
            "flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
            isActive && "bg-accent/60",
          )}
        >
          <span className={cn("h-2 w-2 rounded-full", CATEGORY_COLORS[node.color ?? "zinc"])} />
          <span className="truncate">{node.title}</span>
          <span className="ml-auto text-xs text-muted-foreground">{node.count}</span>
        </Link>
      </div>
      {expanded && node.children.map((ch) => (
        <Node key={ch.path} node={ch} active={active} depth={depth + 1} searching={searching} />
      ))}
    </div>
  );
}
