"use client";

/** Диалог добавления источника: PDF (файл) или YouTube (ссылка). */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function AddSourceButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const uploadPdf = async (file: File) => {
    setBusy(true);
    try {
      const src = await apiUpload<{ uid: string; job_id: number; title: string }>("/sources/upload", file, title ? { title } : undefined);
      toast.success(`«${src.title}» загружается (задача ${src.job_id})`);
      setOpen(false);
      router.push("/library");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка загрузки");
    } finally {
      setBusy(false);
    }
  };

  const addYoutube = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try {
      let videoTitle = title;
      if (!videoTitle) {
        try {
          const resp = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`);
          if (resp.ok) videoTitle = ((await resp.json()) as { title?: string }).title ?? "";
        } catch {
          videoTitle = "";
        }
      }
      const src = await apiPost<{ uid: string; id: number }>("/sources", { kind: "video", title: videoTitle || url, url });
      await apiPost<{ ok: boolean }>(`/sources/${src.id}/process`, {}).catch(() => undefined);
      toast.success("Видео добавлено, транскрипт обрабатывается");
      setOpen(false);
      setUrl("");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>
        <Icon name="add" size={16} /> Добавить источник
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Добавить источник</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="pdf">
          <TabsList>
            <TabsTrigger value="pdf">PDF</TabsTrigger>
            <TabsTrigger value="youtube">YouTube</TabsTrigger>
            <TabsTrigger value="web" disabled>
              Статья (скоро)
            </TabsTrigger>
          </TabsList>
          <TabsContent value="pdf" className="flex flex-col gap-3 pt-3">
            <Input placeholder="Название (необязательно)" value={title} onChange={(e) => setTitle(e.target.value)} />
            <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-8 text-sm text-muted-foreground hover:border-violet-500/50">
              <Icon name="upload" size={24} />
              Перетащи PDF или кликни для выбора
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void uploadPdf(f);
                }}
              />
            </label>
          </TabsContent>
          <TabsContent value="youtube" className="flex flex-col gap-3 pt-3">
            <Input placeholder="https://youtube.com/watch?v=…" value={url} onChange={(e) => setUrl(e.target.value)} />
            <Input placeholder="Название (необязательно)" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Button disabled={busy || !url.trim()} onClick={addYoutube}>
              Добавить и обработать
            </Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
