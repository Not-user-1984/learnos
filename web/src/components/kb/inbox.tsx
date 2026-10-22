"use client";

/** Входящие: блоки с предложенной агентом категорией — принять или выбрать другую. */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { BlockCard, CategoryNode } from "@/lib/types";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CategorySelect } from "./category-select";

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
            <CategorySelect
              categories={categories}
              placeholder="Выбрать другую…"
              ariaLabel="Другая категория"
              className="w-52"
              onSelect={(path) => confirm(b.block_uid, path)}
            />
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
