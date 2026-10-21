"use client";

/** Дерево категорий: показано по умолчанию на любом экране; кнопка сворачивает
 *  в узкую полоску слева (и разворачивает обратно). Состояние запоминается. */

import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { CategoryNode } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { CategoryTree } from "./category-tree";

const HIDDEN_KEY = "learnos-kb-sidebar-hidden";

export function CategorySidebar({ nodes, active }: { nodes: CategoryNode[]; active: string | null }) {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    setHidden(localStorage.getItem(HIDDEN_KEY) === "1");
  }, []);

  const toggle = () => {
    setHidden((h) => {
      const next = !h;
      localStorage.setItem(HIDDEN_KEY, next ? "1" : "0");
      return next;
    });
  };

  if (hidden) {
    return (
      <div className="flex w-10 shrink-0 justify-center border-r pt-3">
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Показать категории" title="Показать категории" onClick={toggle}>
          <PanelLeftOpen className="h-4 w-4" />
        </Button>
      </div>
    );
  }
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r sm:w-60">
      <div className="flex items-center justify-between px-3 pb-1 pt-3">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Категории</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Скрыть категории" title="Скрыть категории" onClick={toggle}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3 pt-1">
        <CategoryTree nodes={nodes} active={active} />
      </div>
    </aside>
  );
}
