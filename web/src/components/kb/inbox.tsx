"use client";

/** Входящие: блоки с предложенной агентом категорией — принять или выбрать другую. */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { BlockCard, CategoryNode } from "@/lib/types";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function InboxPanel({ blocks, categories }: { blocks: BlockCard[]; categories: CategoryNode[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState<string | null>(null);

  const confirm = async (uid: string, path: string | null) => {
    setBusy(uid);
    try {
      await apiPost(`/kb/blocks/${uid}/category`, { path, confirm: true });
      toast.success("Категория подтверждена");
      startTransition(() => router.refresh());
    } catch (e) {
      toast.error(`Не удалось: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  if (blocks.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
        <Icon name="inbox" size={16} /> Входящие пусты: у всех блоков категория подтверждена
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {blocks.map((b) => (
        <div key={b.block_uid} className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3">
          <span className="font-medium">{b.title}</span>
          <span className="text-sm text-muted-foreground">агент предлагает: {b.category_path ?? "—"}</span>
          <span className="ml-auto flex items-center gap-2">
            <Select onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) confirm(b.block_uid, val === "__none__" ? null : val); }}>
              <SelectTrigger className="h-8 w-52 text-xs" aria-label="Другая категория">
                <SelectValue placeholder="Выбрать другую…" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">Без категории</SelectItem>
                {flatten(categories).map((c) => (
                  <SelectItem key={c.path} value={c.path}>
                    {c.title} ({c.path})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              disabled={busy === b.block_uid || pending}
              onClick={() => confirm(b.block_uid, b.category_path)}
            >
              <Icon name="check" size={16} /> Принять
            </Button>
          </span>
        </div>
      ))}
    </div>
  );
}

function flatten(nodes: CategoryNode[]): CategoryNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)]);
}
