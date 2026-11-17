"use client";

/** Выжимка книги (B-014): по главам — саммари блока + карточки-суть; экспорт в markdown. */

import { useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import type { BlockCardItemLike } from "@/lib/types";

export type DigestBlock = {
  block_uid: string;
  title: string;
  summary: string | null;
  sources: { source: string; chapter: number | null }[];
  cards?: BlockCardItemLike[];
};

export function BookDigest({
  sourceUid,
  sourceTitle,
  chapters,
  blocks,
}: {
  sourceUid: string;
  sourceTitle: string;
  chapters: { idx: number; title: string }[];
  blocks: DigestBlock[];
}) {
  const [open, setOpen] = useState(false);
  const byChapter = useMemo(() => {
    const map = new Map<number, DigestBlock[]>();
    const loose: DigestBlock[] = [];
    for (const b of blocks) {
      const ch = b.sources.find((s) => s.source === sourceUid)?.chapter ?? null;
      if (ch === null) loose.push(b);
      else map.set(ch, [...(map.get(ch) ?? []), b]);
    }
    return { map, loose };
  }, [blocks, sourceUid]);

  const toMarkdown = () => {
    const lines = [`# Выжимка: ${sourceTitle}`, ""];
    for (const c of chapters) {
      const bs = byChapter.map.get(c.idx) ?? [];
      if (!bs.length) continue;
      lines.push(`## ${c.title}`);
      for (const b of bs) {
        if (b.summary) lines.push("", `**${b.title}** — ${b.summary}`);
        for (const card of b.cards ?? []) lines.push(`- **${card.q}** ${card.a}`);
      }
      lines.push("");
    }
    if (byChapter.loose.length) {
      lines.push("## Без главы");
      for (const b of byChapter.loose) {
        lines.push(`- **${b.title}**${b.summary ? ` — ${b.summary}` : ""}`);
        for (const card of b.cards ?? []) lines.push(`  - **${card.q}** ${card.a}`);
      }
    }
    return lines.join("\n");
  };

  const exportMd = () => {
    const md = toMarkdown();
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `выжимка-${sourceTitle.slice(0, 40).replace(/\s+/g, "-")}.md`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Выжимка сохранена в .md");
  };

  if (blocks.length === 0) return null;

  return (
    <section className="mb-5 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <Icon name="summarize" size={16} className="text-primary" /> Выжимка книги
          <span className="font-normal text-muted-foreground">
            · блоков: {blocks.length} · карточек: {blocks.reduce((n, b) => n + (b.cards?.length ?? 0), 0)}
          </span>
        </h2>
        <div className="ml-auto flex gap-2">
          <Link
            href={`/review?source=${sourceUid}&title=${encodeURIComponent(sourceTitle)}`}
            className="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm transition hover:bg-accent"
            title="Повторения только по этой книге"
          >
            <Icon name="style" size={15} /> Закрепить книгу
          </Link>
          <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
            <Icon name={open ? "expand_less" : "expand_more"} size={15} /> {open ? "Свернуть" : "Показать"}
          </Button>
          <Button size="sm" variant="outline" onClick={exportMd}>
            <Icon name="download" size={15} /> .md
          </Button>
        </div>
      </div>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          {chapters.map((c) => {
            const bs = byChapter.map.get(c.idx) ?? [];
            if (!bs.length) return null;
            return (
              <div key={c.idx} className="rounded-lg border bg-background p-3">
                <p className="mb-1.5 text-sm font-medium">{c.title}</p>
                {bs.map((b) => (
                  <div key={b.block_uid} className="mb-2 last:mb-0">
                    <Link href={`/kb/${b.block_uid}`} className="text-sm text-primary hover:underline">
                      {b.title}
                    </Link>
                    {b.summary && <p className="text-sm text-muted-foreground">{b.summary}</p>}
                    {(b.cards ?? []).length > 0 && (
                      <ul className="mt-1 flex flex-col gap-1">
                        {(b.cards ?? []).map((card) => (
                          <li key={card.id} className="rounded-md bg-muted/60 px-2.5 py-1.5 text-sm">
                            <span className="font-medium">{card.q}</span>{" "}
                            <span className="text-muted-foreground">{card.a}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
          {byChapter.loose.length > 0 && (
            <div className="rounded-lg border bg-background p-3">
              <p className="mb-1.5 text-sm font-medium">Без привязки к главе</p>
              {byChapter.loose.map((b) => (
                <Link key={b.block_uid} href={`/kb/${b.block_uid}`} className="block text-sm text-primary hover:underline">
                  {b.title}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
