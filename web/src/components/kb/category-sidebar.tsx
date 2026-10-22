"use client";

/** Дерево категорий: показано по умолчанию на любом экране; кнопка сворачивает
 *  в узкую полоску слева (и разворачивает обратно). Состояние запоминается. */

import { Icon } from "@/components/ui/icon";
import type { CategoryNode } from "@/lib/types";
import { useStored } from "@/lib/use-stored";
import { Button } from "@/components/ui/button";
import { CategoryTree } from "./category-tree";

const HIDDEN_KEY = "learnos-kb-sidebar-hidden";
const HIDDEN_EVENT = "learnos-kb-sidebar-hidden-change";

export function CategorySidebar({ nodes, active }: { nodes: CategoryNode[]; active: string | null }) {
  const [hiddenRaw, setHidden] = useStored(HIDDEN_KEY, HIDDEN_EVENT, "0");
  const hidden = hiddenRaw === "1";

  const toggle = () => setHidden(hidden ? "0" : "1");

  if (hidden) {
    return (
      <div className="flex w-10 shrink-0 justify-center border-r pt-3">
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Показать категории" title="Показать категории" onClick={toggle}>
          <Icon name="left_panel_open" size={16} />
        </Button>
      </div>
    );
  }
  return (
    <aside className="flex w-52 shrink-0 flex-col border-r sm:w-60">
      <div className="flex items-center justify-between px-3 pb-1 pt-3">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Категории</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Скрыть категории" title="Скрыть категории" onClick={toggle}>
          <Icon name="left_panel_close" size={16} />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3 pt-1">
        <CategoryTree nodes={nodes} active={active} />
      </div>
    </aside>
  );
}
