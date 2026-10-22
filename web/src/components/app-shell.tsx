"use client";

/** Оболочка приложения: сайдбар с разделами (на мобиле — off-canvas), ⌘K-палитра. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { modeIcon } from "@/lib/format";
import { api } from "@/lib/api";
import type { BlockCard, ConversationItem } from "@/lib/types";
import { CommandPalette } from "@/components/command-palette";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/chat", label: "Чат", icon: "chat" },
  { href: "/kb", label: "База знаний", icon: "psychology" },
  { href: "/library", label: "Библиотека", icon: "collections_bookmark" },
  { href: "/courses", label: "Курсы", icon: "school" },
  { href: "/settings", label: "Настройки", icon: "settings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [recent, setRecent] = useState<ConversationItem[]>([]);
  const [inbox, setInbox] = useState<number | null>(null);

  useEffect(() => {
    api<ConversationItem[]>("/conversations").then((c) => setRecent(c.slice(0, 5))).catch(() => setRecent([]));
    api<BlockCard[]>("/kb/inbox").then((b) => setInbox(b.length)).catch(() => setInbox(null));
  }, [pathname]);

  const nav = (
    <nav className="flex flex-col gap-1 p-2">
      {NAV.map(({ href, label, icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            title={label}
            onClick={() => setMobileOpen(false)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/50",
            )}
          >
            <Icon name={icon} size={20} filled={pathname.startsWith(href)} className="shrink-0" />
            {!collapsed && <span>{label}</span>}
            {!collapsed && href === "/kb" && inbox !== null && inbox > 0 && (
              <span className="ml-auto flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">
                <Icon name="inbox" size={12} />
                {inbox}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );

  const recents =
    !collapsed && recent.length > 0 ? (
      <div className="mt-2 flex-1 overflow-y-auto border-t p-2">
        <p className="px-2 pb-1 text-xs text-sidebar-foreground/50">Недавние разговоры</p>
        {recent.map((c) => (
          <Link
            key={c.uid}
            href={`/chat/${c.uid}`}
            onClick={() => setMobileOpen(false)}
            className="block truncate rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent/50"
            title={c.title}
          >
            <Icon name={modeIcon(c.mode)} size={14} className="text-muted-foreground" /> {c.title}
          </Link>
        ))}
      </div>
    ) : null;

  return (
    <div className="flex h-dvh">
      {/* десктопный сайдбар */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-all md:flex",
          collapsed ? "w-14" : "w-60",
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b px-3">
          <Icon name="auto_stories" size={20} className="shrink-0 text-primary" />
          {!collapsed && <span className="font-semibold">LearnOS</span>}
        </div>
        {nav}
        {recents}
        <div className="mt-auto flex items-center justify-between border-t p-2">
          <Button variant="ghost" size="icon" aria-label="Поиск (⌘K)" onClick={() => document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}>
            <Icon name="search" size={16} />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Свернуть меню" onClick={() => setCollapsed((v) => !v)}>
            {collapsed ? <Icon name="keyboard_double_arrow_right" size={16} /> : <Icon name="keyboard_double_arrow_left" size={16} />}
          </Button>
        </div>
      </aside>

      {/* мобильный off-canvas */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button aria-label="Закрыть меню" className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-sidebar text-sidebar-foreground">
            <div className="flex h-14 items-center gap-2 border-b px-3">
              <Icon name="auto_stories" size={20} className="text-primary" />
              <span className="font-semibold">LearnOS</span>
              <Button variant="ghost" size="icon" className="ml-auto" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)}>
                <Icon name="close" size={16} />
              </Button>
            </div>
            {nav}
            {recents}
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-2 border-b px-3 md:justify-end md:px-4">
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Меню" onClick={() => setMobileOpen(true)}>
            <Icon name="menu" size={20} />
          </Button>
          <span className="font-semibold md:hidden">LearnOS</span>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>
        <div className="min-h-0 flex-1">{children}</div>
      </main>
      <CommandPalette />
    </div>
  );
}

