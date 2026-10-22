"use client";

/** ⌘K: навигация + поиск блоков и источников. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Icon } from "@/components/ui/icon";
import { kindIcon } from "@/lib/format";
import { api } from "@/lib/api";
import type { BlockCard, SourceCard } from "@/lib/types";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [blocks, setBlocks] = useState<BlockCard[]>([]);
  const [sources, setSources] = useState<SourceCard[]>([]);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    api<BlockCard[]>("/kb/blocks?limit=8").then(setBlocks).catch(() => setBlocks([]));
    api<SourceCard[]>("/sources").then(setSources).catch(() => setSources([]));
  }, [open]);

  const go = (path: string) => {
    setOpen(false);
    router.push(path);
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Поиск: блоки, источники, разделы…" />
      <CommandList>
        <CommandEmpty>Ничего не найдено</CommandEmpty>
        <CommandGroup heading="Переход">
          <CommandItem onSelect={() => go("/chat")}><Icon name="chat" size={18} /> Чат</CommandItem>
          <CommandItem onSelect={() => go("/kb")}><Icon name="psychology" size={18} /> База знаний</CommandItem>
          <CommandItem onSelect={() => go("/library")}><Icon name="collections_bookmark" size={18} /> Библиотека</CommandItem>
          <CommandItem onSelect={() => go("/courses")}><Icon name="school" size={18} /> Курсы</CommandItem>
          <CommandItem onSelect={() => go("/settings")}><Icon name="settings" size={18} /> Настройки</CommandItem>
        </CommandGroup>
        {blocks.length > 0 && (
          <CommandGroup heading="Блоки знаний">
            {blocks.map((b) => (
              <CommandItem key={b.block_uid} onSelect={() => go(`/kb/${b.block_uid}`)}>
                <Icon name="description" size={18} /> {b.title}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {sources.length > 0 && (
          <CommandGroup heading="Источники">
            {sources.map((s) => (
              <CommandItem key={s.uid} onSelect={() => go(`/library/${s.uid}`)}>
                <Icon name={kindIcon(s.kind)} size={18} /> {s.title}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
