"use client";

/** Диалог нового разговора: режим + источник + глава. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import type { SourceDetail } from "@/lib/types";
import { api, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export function NewConversationButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("quick");
  const [sources, setSources] = useState<SourceDetail[]>([]);
  const [source, setSource] = useState<string>("");
  const [chapter, setChapter] = useState<string>("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api<SourceDetail[]>("/sources").then(setSources).catch(() => setSources([]));
  }, [open]);

  const chosen = sources.find((s) => s.uid === source);

  const create = async () => {
    setBusy(true);
    try {
      const activity = await apiPost<{ uid: string }>("/activities", { source }).catch(() => null);
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode,
        activity: activity?.uid ?? null,
        chapter: chapter ? Number(chapter) : null,
      });
      setOpen(false);
      if (source) {
        const first =
          mode === "session"
            ? `Начни сессию${chapter ? ` по главе ${chapter}` : ""}: теория по первым понятиям, коротко.`
            : `Начнём быстрый разбор${chapter ? ` главы ${chapter}` : ""}: главное и ключевые понятия.`;
        router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(first)}`);
      } else {
        router.push(`/chat/${conv.uid}`);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать разговор");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <Plus className="h-4 w-4" /> Новый разговор
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Новый разговор</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <ToggleGroup
            value={[mode]}
            onValueChange={(v: unknown) => {
              const val = Array.isArray(v) && v.length > 0 ? String(v[v.length - 1]) : null;
              if (val) setMode(val);
            }}
            className="justify-start"
          >
            <ToggleGroupItem value="quick">⚡ Быстрый разбор</ToggleGroupItem>
            <ToggleGroupItem value="session">🎓 Сессия</ToggleGroupItem>
            <ToggleGroupItem value="free">💬 Свободный</ToggleGroupItem>
            <ToggleGroupItem value="tuning">⚙️ Настроить агента</ToggleGroupItem>
          </ToggleGroup>

          {mode !== "free" && mode !== "tuning" && (
            <>
              <Select onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) { setSource(val); setChapter(""); } }}>
                <SelectTrigger aria-label="Источник">
                  <SelectValue placeholder={sources.length ? "Выбери источник" : "Нет источников — загрузи в Библиотеке"} />
                </SelectTrigger>
                <SelectContent>
                  {sources.map((s) => (
                    <SelectItem key={s.uid} value={s.uid}>
                      {s.kind === "book" ? "📕" : s.kind === "video" ? "🎬" : "🌐"} {s.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {chosen && (chosen.chapters?.length ?? 0) > 0 && (
                <Select onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) setChapter(val); }}>
                  <SelectTrigger aria-label="Глава">
                    <SelectValue placeholder="Глава (по умолчанию — с курсора)" />
                  </SelectTrigger>
                  <SelectContent>
                    {chosen.chapters.map((c) => (
                      <SelectItem key={c.idx} value={String(c.idx)}>
                        {c.idx}. {c.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </>
          )}

          <Button disabled={busy || (mode !== "free" && !source)} onClick={create}>
            Начать
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
