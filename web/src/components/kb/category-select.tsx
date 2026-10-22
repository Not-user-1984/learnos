"use client";

/** Выбор категории с поиском: триггер в стиле Select + выпадающий список
 *  с полем фильтра по названию и пути. Замена обычного Select там, где категорий много. */

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { flattenCategories } from "@/lib/categories";
import type { CategoryNode } from "@/lib/types";
import { cn } from "@/lib/utils";

export function CategorySelect({
  categories,
  value,
  placeholder = "Выбрать категорию…",
  disabled,
  ariaLabel = "Категория",
  className,
  onSelect,
}: {
  categories: CategoryNode[];
  /** Текущий путь: подсвечивается в списке и показывается на триггере. */
  value?: string | null;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
  /** Выбор: полный путь либо null («Без категории»). */
  onSelect: (path: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const q = query.trim().toLowerCase();
  const items = useMemo(
    () =>
      flattenCategories(categories).filter(
        (c) => !q || c.title.toLowerCase().includes(q) || c.path.toLowerCase().includes(q),
      ),
    [categories, q],
  );

  const pick = (path: string | null) => {
    setOpen(false);
    onSelect(path);
  };

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => {
          setQuery("");
          setOpen((v) => !v);
        }}
        className={cn(
          "flex h-8 w-full items-center justify-between gap-1.5 rounded-lg border border-input bg-transparent py-2 pr-2 pl-2.5 text-sm whitespace-nowrap transition-colors outline-none select-none",
          "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30 dark:hover:bg-input/50",
        )}
      >
        <span className={cn("flex-1 truncate text-left", !value && "text-muted-foreground")}>
          {value ?? placeholder}
        </span>
        <Icon name="expand_more" size={16} className="pointer-events-none shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className="absolute top-[calc(100%+4px)] right-0 z-50 flex max-h-80 w-72 flex-col overflow-hidden rounded-lg bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10"
        >
          <div className="border-b p-1.5">
            <Input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Начните вводить…"
              aria-label="Фильтр категорий"
              className="h-8 text-sm"
            />
          </div>
          <div className="flex flex-col gap-0.5 overflow-y-auto p-1">
            <Option selected={value == null} onClick={() => pick(null)}>
              Без категории
            </Option>
            {items.map((c) => (
              <Option key={c.path} selected={value === c.path} onClick={() => pick(c.path)}>
                <span className="truncate">{c.title}</span>
                <span className="shrink-0 truncate text-xs text-muted-foreground">{c.path}</span>
              </Option>
            ))}
            {items.length === 0 && (
              <p className="px-2 py-4 text-center text-xs text-muted-foreground">Ничего не найдено</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Option({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
        selected && "bg-accent/60",
      )}
    >
      <span className="flex min-w-0 flex-1 items-center gap-1.5">{children}</span>
      {selected && <Icon name="check" size={14} className="shrink-0" />}
    </button>
  );
}
