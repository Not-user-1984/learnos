"use client";

/** Витрина библиотеки: вкладки по типам источников, поиск, статусы, удаление. */

import { useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { kindIcon } from "@/lib/format";
import type { SourceCard } from "@/lib/types";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const KIND_TABS = [
  { value: "all", label: "Все", icon: null },
  { value: "book", label: "Книги", icon: "auto_stories" },
  { value: "video", label: "Видео", icon: "movie" },
  { value: "web", label: "Статьи", icon: null },
] as const;

const STATUS_VIEW: Record<string, { label: string; cls: string }> = {
  processed: { label: "готова к изучению", cls: "text-emerald-500" },
  processing: { label: "обрабатывается…", cls: "text-amber-500" },
  chosen: { label: "не обработана", cls: "text-muted-foreground" },
  found: { label: "найдена, не обработана", cls: "text-muted-foreground" },
  failed: { label: "ошибка обработки", cls: "text-rose-500" },
};

const STATUS_ORDER: Record<string, number> = { processed: 0, processing: 1, chosen: 2, found: 2, failed: 3 };

export function LibraryBrowser({ sources }: { sources: SourceCard[] }) {
  const [kind, setKind] = useState<(typeof KIND_TABS)[number]["value"]>("all");
  const [q, setQ] = useState("");

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: sources.length };
    for (const s of sources) c[s.kind] = (c[s.kind] ?? 0) + 1;
    return c;
  }, [sources]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return sources
      .filter((s) => (kind === "all" ? true : s.kind === kind))
      .filter((s) => (needle ? s.title.toLowerCase().includes(needle) : true))
      .sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9) || b.id - a.id);
  }, [sources, kind, q]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={kind} onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) setKind(val as typeof kind); }}>
          <TabsList>
            {KIND_TABS.map(({ value, label, icon }) => (
              <TabsTrigger key={value} value={value} className="gap-1.5">
                {icon && <Icon name={icon} size={14} filled={kind === value} />}
                {label}
                <span className="text-xs text-muted-foreground">{counts[value] ?? 0}</span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="relative ml-auto">
          <Icon name="search" size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Поиск по названию…"
            className="h-9 w-56 pl-8"
            aria-label="Поиск по названию"
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">
          {q ? "Ничего не найдено" : "Здесь пока пусто — добавь источник кнопкой сверху"}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((s) => {
            const status = STATUS_VIEW[s.status] ?? { label: s.status, cls: "text-muted-foreground" };
            return (
              <div key={s.uid} className="group relative flex flex-col overflow-hidden rounded-xl border bg-card transition hover:border-violet-500/50">
                <Link href={`/library/${s.uid}`} className="flex flex-1 flex-col">
                  <div
                    className={cn(
                      "flex h-24 items-center justify-center text-4xl",
                      s.kind === "book" && "bg-gradient-to-br from-sky-500/20 to-violet-500/20",
                      s.kind === "video" && "bg-gradient-to-br from-rose-500/20 to-amber-500/20",
                      s.kind === "web" && "bg-gradient-to-br from-emerald-500/15 to-sky-500/20",
                    )}
                  >
                    <Icon name={kindIcon(s.kind)} size={36} filled />
                  </div>
                  <div className="flex flex-1 flex-col gap-1.5 p-4">
                    <p className="line-clamp-2 font-medium leading-snug">{s.title}</p>
                    {s.summary && <p className="line-clamp-2 text-xs text-muted-foreground">{s.summary}</p>}
                    <p className={cn("mt-auto pt-1 text-xs", status.cls)}>
                      {status.label}
                      {s.kind !== "web" && s.status === "processed" && ` · ${s.chapters_count} гл.`}
                      {s.url && (
                        <>
                          {" · "}
                          <span className="underline decoration-dotted">открыть источник</span>
                        </>
                      )}
                    </p>
                  </div>
                </Link>
                <ConfirmDeleteButton
                  endpoint={`/sources/${s.uid}`}
                  title="Удалить источник?"
                  name={s.title}
                  description="Уйдут главы и файлы источника из библиотеки. Разговоры и блоки базы знаний останутся — если по источнику есть блоки, удаление будет запрещено."
                  successMessage="Источник удалён"
                  className="absolute right-2 top-2 opacity-0 transition group-hover:opacity-100"
                  buttonClassName="rounded-lg bg-background/60 p-1.5 text-muted-foreground backdrop-blur transition hover:text-rose-500"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
