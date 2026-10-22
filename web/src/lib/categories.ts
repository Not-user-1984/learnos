/** Хелперы работы с деревом категорий БЗ. */

import type { CategoryNode } from "@/lib/types";

/** Плоский список категорий из дерева (обход в глубину). */
export function flattenCategories(nodes: CategoryNode[]): CategoryNode[] {
  return nodes.flatMap((n) => [n, ...flattenCategories(n.children)]);
}

/** Человекочитаемое название категории по пути: title узла из дерева,
 *  а если узел не найден — последний сегмент пути. */
export function categoryLabel(nodes: CategoryNode[], path: string | null): string | null {
  if (!path) return null;
  const hit = flattenCategories(nodes).find((n) => n.path === path);
  return hit?.title ?? (path.split("/").pop() || path);
}

/** Дерево только из узлов, совпавших с запросом (title или path, регистронезависимо),
 *  вместе с их родительской цепочкой. Пустой запрос возвращает дерево как есть. */
export function filterCategoryTree(nodes: CategoryNode[], query: string): CategoryNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  return nodes
    .map((n) => {
      const children = filterCategoryTree(n.children, query);
      const self = n.title.toLowerCase().includes(q) || n.path.toLowerCase().includes(q);
      if (!self && children.length === 0) return null;
      return { ...n, children };
    })
    .filter((n): n is CategoryNode => n !== null);
}
