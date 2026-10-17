"use client";

/** Обслуживание: рабочая переиндексация и экспорт. */

import { useState } from "react";
import { Check, Database, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function MaintenanceActions() {
  const [reindexing, setReindexing] = useState(false);
  const [done, setDone] = useState(false);

  const reindex = async () => {
    setReindexing(true);
    setDone(false);
    try {
      const r = await apiPost<{ created: number; updated: number }>("/kb/reindex", {});
      toast.success(`Индекс пересобран: +${r.created} новых, ~${r.updated} обновлено`);
      setDone(true);
      setTimeout(() => setDone(false), 2500);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "переиндексация не удалась");
    } finally {
      setReindexing(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={reindex} disabled={reindexing}>
          {reindexing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : done ? <Check className="mr-1.5 h-4 w-4 text-emerald-500" /> : <Database className="mr-1.5 h-4 w-4" />}
          Переиндексировать базу знаний
        </Button>
        <p className="text-xs text-muted-foreground">после ручной правки MD-файлов в kb/</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {/* API-роут скачивания (не Next-страница) — Link тут не подходит */}
        <a
          href="/api/export?scope=all&format=zip"
          download
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          <Download className="h-3.5 w-3.5" /> Экспорт всего (ZIP)
        </a>
        <a
          href="/api/export?scope=all&format=md"
          download
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm hover:bg-accent"
        >
          <Download className="h-3.5 w-3.5" /> Экспорт всего (MD)
        </a>
      </div>
    </div>
  );
}
