"use client";

/** Дерево категорий со счётчиками (включая подкатегории). */

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Inbox } from "lucide-react";
import type { CategoryNode } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CATEGORY_COLORS: Record<string, string> = {
  sky: "bg-sky-500",
  violet: "bg-violet-500",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  zinc: "bg-zinc-500",
};

export function CategoryTree({ nodes, active }: { nodes: CategoryNode[]; active: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <Link
        href="/kb"
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent",
          !active && "bg-accent/60",
        )}
      >
        <Inbox className="h-3.5 w-3.5 text-muted-foreground" />
        Все блоки
      </Link>
      {nodes.map((n) => (
        <Node key={n.path} node={n} active={active} depth={0} />
      ))}
    </div>
  );
}

function Node({ node, active, depth }: { node: CategoryNode; active: string | null; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const isActive = active === node.path;
  return (
    <div>
      <div className="flex items-center gap-1" style={{ paddingLeft: depth * 12 }}>
        {node.children.length > 0 ? (
          <button aria-label="Раскрыть" onClick={() => setOpen((v) => !v)} className="rounded p-0.5 hover:bg-accent">
            {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
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
      {open && node.children.map((ch) => <Node key={ch.path} node={ch} active={active} depth={depth + 1} />)}
    </div>
  );
}
