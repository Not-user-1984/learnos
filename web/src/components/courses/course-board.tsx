"use client";

/** Курс как доска задач (B-005): группы по статусу todo/doing/read/done, действия
 *  элемента (сессия/читать/прочитал сам), порядок стрелками, добавление/удаление. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import type { BlockCard, Course, CourseItem } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { cn } from "@/lib/utils";
import { MarkReadButton, StartItemButton } from "@/components/today/today-actions";

const STATUS_GROUPS: { key: string; label: string; icon: string }[] = [
  { key: "doing", label: "В работе", icon: "pending" },
  { key: "todo", label: "Дальше", icon: "radio_button_unchecked" },
  { key: "read", label: "Прочитано", icon: "menu_book" },
  { key: "done", label: "Готово", icon: "check_circle" },
];

type SourceLite = { uid: string; title: string; chapters_count: number; kind: string };

export function CourseBoard({ course }: { course: Course }) {
  const router = useRouter();
  const items = course.items ?? [];
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);

  const move = async (item: CourseItem, dir: -1 | 1) => {
    const ordered = [...items];
    const idx = ordered.findIndex((i) => i.id === item.id);
    const swapWith = idx + dir;
    if (idx < 0 || swapWith < 0 || swapWith >= ordered.length) return;
    [ordered[idx], ordered[swapWith]] = [ordered[swapWith], ordered[idx]];
    setBusy(true);
    try {
      await apiPost(`/courses/${course.uid}/reorder`, { item_ids: ordered.map((i) => i.id) });
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось переставить");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant="outline">{course.status}</Badge>
        <span className="text-sm text-muted-foreground">
          {course.items_done}/{course.items_count} пройдено
        </span>
        <div className="w-48">
          <Progress value={course.items_count ? (course.items_done / course.items_count) * 100 : 0} />
        </div>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setAdding((v) => !v)}>
          <Icon name="add" size={16} className="mr-1" /> Добавить элемент
        </Button>
      </div>

      {adding && <AddItemCard courseUid={course.uid} onAdded={() => { setAdding(false); router.refresh(); }} />}

      {items.length === 0 && (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Пусто: добавь источники, главы и блоки из библиотеки и базы знаний.
        </p>
      )}

      {STATUS_GROUPS.map((group) => {
        const groupItems = items.filter((i) => i.status === group.key);
        if (!groupItems.length) return null;
        return (
          <section key={group.key}>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <Icon name={group.icon} size={14} className="text-primary" /> {group.label}
              <span className="text-muted-foreground/60">· {groupItems.length}</span>
            </p>
            <ul className="flex flex-col gap-2">
              {groupItems.map((item) => {
                const idx = items.findIndex((i) => i.id === item.id);
                return (
                  <li key={item.id} className="group flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3 sm:gap-3 sm:p-4">
                    <div className="flex flex-col sm:hidden">
                      <button aria-label="Выше" disabled={busy || idx === 0} onClick={() => void move(item, -1)} className="text-muted-foreground disabled:opacity-30">
                        <Icon name="keyboard_arrow_up" size={18} />
                      </button>
                      <button aria-label="Ниже" disabled={busy || idx === items.length - 1} onClick={() => void move(item, 1)} className="text-muted-foreground disabled:opacity-30">
                        <Icon name="keyboard_arrow_down" size={18} />
                      </button>
                    </div>
                    <div className="hidden shrink-0 flex-col sm:flex">
                      <button aria-label="Выше" disabled={busy || idx === 0} onClick={() => void move(item, -1)} className="rounded p-0.5 text-muted-foreground transition hover:text-foreground disabled:opacity-30">
                        <Icon name="keyboard_arrow_up" size={16} />
                      </button>
                      <button aria-label="Ниже" disabled={busy || idx === items.length - 1} onClick={() => void move(item, 1)} className="rounded p-0.5 text-muted-foreground transition hover:text-foreground disabled:opacity-30">
                        <Icon name="keyboard_arrow_down" size={16} />
                      </button>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{item.title}</p>
                      {item.note && <p className="truncate text-xs text-muted-foreground">{item.note}</p>}
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {item.item_type === "source" ? "источник" : item.item_type === "chapter" ? `гл. ${item.chapter_idx}` : "блок"}
                    </Badge>
                    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                      {item.item_type === "block" && item.block_uid && (
                        <Link href={`/kb/${item.block_uid}`} className="rounded-lg border px-2.5 py-1 text-sm transition hover:bg-accent">
                          Открыть
                        </Link>
                      )}
                      {(item.item_type === "chapter" || item.item_type === "source") && item.source_uid && item.status !== "done" && (
                        <>
                          {item.status !== "doing" && <StartItemButton courseUid={course.uid} itemId={item.id} />}
                          <Link
                            href={`/library/${item.source_uid}/read${item.chapter_idx ? `?chapter=${item.chapter_idx}` : ""}`}
                            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm transition hover:bg-accent"
                          >
                            <Icon name="auto_stories" size={15} /> Читать
                          </Link>
                          {item.item_type === "chapter" && item.status === "todo" && (
                            <MarkReadButton sourceUid={item.source_uid} chapter={item.chapter_idx} onDone={() => router.refresh()} />
                          )}
                        </>
                      )}
                      <ConfirmDeleteButton
                        endpoint={`/courses/${course.uid}/items/${item.id}`}
                        title="Удалить элемент курса?"
                        name={item.title}
                        description="Элемент исчезнет из доски курса. Источник и блоки останутся."
                        successMessage="Элемент удалён"
                        className="opacity-0 transition group-hover:opacity-100"
                        buttonClassName="rounded-lg p-1.5 text-muted-foreground transition hover:text-rose-500"
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/** Добавление элемента: источник/глава/блок с поиском по библиотеке и базе. */
function AddItemCard({ courseUid, onAdded }: { courseUid: string; onAdded: () => void }) {
  const [type, setType] = useState<"source" | "chapter" | "block">("chapter");
  const [sources, setSources] = useState<SourceLite[]>([]);
  const [blocks, setBlocks] = useState<BlockCard[]>([]);
  const [sourceUid, setSourceUid] = useState("");
  const [chapter, setChapter] = useState("1");
  const [blockUid, setBlockUid] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const [srcs, blks] = await Promise.all([
          api<SourceLite[]>("/sources"),
          api<BlockCard[]>("/kb/blocks?limit=50"),
        ]);
        setSources(srcs);
        setBlocks(blks);
        if (srcs[0]) setSourceUid(srcs[0].uid);
        if (blks[0]) setBlockUid(blks[0].block_uid);
      } catch {
        toast.error("не удалось загрузить библиотеку");
      }
    })();
  }, []);

  const add = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await apiPost(`/courses/${courseUid}/items`, {
        item_type: type,
        source: type === "block" ? null : sourceUid,
        chapter: type === "chapter" ? Number(chapter) || null : null,
        block_uid: type === "block" ? blockUid : null,
      });
      toast.success("Элемент добавлен");
      onAdded();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось добавить");
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap gap-2">
        {(["chapter", "source", "block"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setType(t)}
            className={cn(
              "rounded-full border px-3 py-1 text-sm transition",
              type === t ? "border-primary/50 bg-primary/10 text-primary" : "hover:bg-accent",
            )}
          >
            {t === "chapter" ? "Глава" : t === "source" ? "Источник целиком" : "Блок"}
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        {type !== "block" && (
          <label className="flex min-w-56 flex-1 flex-col gap-1 text-sm">
            Источник
            <select
              value={sourceUid}
              onChange={(e) => setSourceUid(e.target.value)}
              className="rounded-lg border bg-background px-2 py-1.5 text-sm"
            >
              {sources.map((s) => (
                <option key={s.uid} value={s.uid}>
                  {s.title} ({s.chapters_count} гл.)
                </option>
              ))}
            </select>
          </label>
        )}
        {type === "chapter" && (
          <label className="flex w-24 flex-col gap-1 text-sm">
            Глава
            <Input type="number" min={1} value={chapter} onChange={(e) => setChapter(e.target.value)} />
          </label>
        )}
        {type === "block" && (
          <label className="flex min-w-56 flex-1 flex-col gap-1 text-sm">
            Блок
            <select
              value={blockUid}
              onChange={(e) => setBlockUid(e.target.value)}
              className="rounded-lg border bg-background px-2 py-1.5 text-sm"
            >
              {blocks.map((b) => (
                <option key={b.block_uid} value={b.block_uid}>
                  {b.title}
                </option>
              ))}
            </select>
          </label>
        )}
        <Button size="sm" disabled={busy} onClick={() => void add()}>
          {busy ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="add" size={16} className="mr-1" />}
          Добавить
        </Button>
      </div>
    </div>
  );
}
