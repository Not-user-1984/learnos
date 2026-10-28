"use client";

/** Мастер изучения: «Изучить книгу» (PDF → карта глав → «разобрать с агентом»)
 *  и «Обсудить видео» (YouTube). Разговор всегда root — формат (разбор или
 *  сессия-урок) выбирает корневой агент по интенту «study». */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { ChapterCard, SourceCard } from "@/lib/types";
import { api, apiPost, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Step = "pick" | "processing" | "ready";
type Job = { id: number; status: string; progress: number; total: number; error?: string | null };

const JOB_LABEL_BOOK: Record<string, string> = {
  process_source: "Разбираю источник на главы",
  summarize_chapters: "Нейронка читает главы и пишет конспекты",
};
const JOB_LABEL_VIDEO: Record<string, string> = {
  process_source: "Скачиваю субтитры и собираю транскрипт",
  summarize_chapters: "Нейронка смотрит видео и пишет конспект",
};

export function StudyFlowDialog({
  open,
  onOpenChange,
  defaultTab = "book",
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaultTab?: "book" | "video";
}) {
  const router = useRouter();
  const [tab, setTab] = useState<"book" | "video">(defaultTab);
  const [step, setStep] = useState<Step>("pick");
  const [sourceUid, setSourceUid] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [chapters, setChapters] = useState<ChapterCard[]>([]);
  const [sourceTitle, setSourceTitle] = useState("");
  const [sourceKind, setSourceKind] = useState<"book" | "video">("book");
  const [videoUrl, setVideoUrl] = useState("");
  const [library, setLibrary] = useState<SourceCard[]>([]);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const summariesRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (open && tab === "book") {
      api<SourceCard[]>("/sources").then(setLibrary).catch(() => setLibrary([]));
    }
  }, [open, tab]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (summariesRef.current) clearInterval(summariesRef.current);
    pollRef.current = null;
    summariesRef.current = null;
  }, []);

  const loadSource = useCallback(async (uid: string) => {
    const src = await api<{ uid: string; title: string; kind: string; chapters: ChapterCard[] }>(`/sources/${uid}`);
    setSourceTitle(src.title);
    setSourceKind(src.kind === "video" ? "video" : "book");
    setChapters(src.chapters ?? []);
    return src;
  }, []);

  const waitForJob = useCallback(
    (jobId: number, uid: string) => {
      setStep("processing");
      setJob({ id: jobId, status: "running", progress: 0, total: 0 });
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const j = await api<Job>(`/jobs/${jobId}`);
          setJob(j);
          if (j.status === "done") {
            stopPolling();
            await loadSource(uid);
            setStep("ready");
            // summary глав подтягиваются вторым job'ом — обновляем карту ещё минуту
            let ticks = 0;
            summariesRef.current = setInterval(async () => {
              ticks += 1;
              if (ticks > 12) stopPolling();
              else await loadSource(uid).catch(() => stopPolling());
            }, 5000);
          } else if (j.status === "failed") {
            stopPolling();
            toast.error(`Обработка не удалась: ${j.error ?? "ошибка"}`);
            setStep("pick");
          }
        } catch {
          // сеть моргнула — продолжаем опрос
        }
      }, 2500);
    },
    [loadSource, stopPolling],
  );

  useEffect(() => stopPolling, [stopPolling]);

  // сброс при закрытии (esc/оверлей/крестик тоже идут через onOpenChange)
  const handleOpenChange = (v: boolean) => {
    if (!v) {
      stopPolling();
      setStep("pick");
      setJob(null);
      setChapters([]);
      setSourceUid(null);
      setSourceTitle("");
      setSourceKind("book");
      setVideoUrl("");
    }
    onOpenChange(v);
  };

  const uploadPdf = async (file: File) => {
    setBusy(true);
    try {
      const src = await apiUpload<{ uid: string; job_id: number; title: string }>("/sources/upload", file);
      setSourceUid(src.uid);
      waitForJob(src.job_id, src.uid);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка загрузки");
    } finally {
      setBusy(false);
    }
  };

  const startVideo = async () => {
    if (!videoUrl.trim()) return;
    setBusy(true);
    try {
      let title = "";
      try {
        const resp = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(videoUrl)}&format=json`);
        if (resp.ok) title = ((await resp.json()) as { title?: string }).title ?? "";
      } catch {
        title = "";
      }
      const src = await apiPost<{ uid: string; id: number }>("/sources", {
        kind: "video",
        title: title || videoUrl,
        url: videoUrl,
      });
      const proc = await apiPost<{ ok: boolean; job_id: number | null }>(`/sources/${src.id}/process`, {});
      setSourceUid(src.uid);
      if (proc.job_id) waitForJob(proc.job_id, src.uid);
      else {
        // уже обработан
        await loadSource(src.uid);
        setStep("ready");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  const pickLibrary = async (uid: string) => {
    const src = await api<{ uid: string; title: string; status: string; chapters: ChapterCard[] }>(`/sources/${uid}`);
    if (src.status === "processed" && (src.chapters?.length ?? 0) > 0) {
      setSourceUid(uid);
      await loadSource(uid);
      setStep("ready");
    } else {
      toast.info("Источник ещё не обработан — запускаю обработку");
      const proc = await apiPost<{ ok: boolean; job_id: number | null }>(`/sources/${uid}/process`, {});
      setSourceUid(uid);
      if (proc.job_id) waitForJob(proc.job_id, uid);
    }
  };

  const startStudying = async () => {
    if (!sourceUid) return;
    setBusy(true);
    try {
      const isVideo = sourceKind === "video";
      const act = await apiPost<{ uid: string }>("/activities", { source: sourceUid });
      const conv = await apiPost<{ uid: string }>("/conversations", {
        activity: act.uid,
        chapter: 1,
        title: `${isVideo ? "Видео" : "Изучение"}: ${sourceTitle}`,
      });
      onOpenChange(false);
      // видимый текст — только намерение пользователя; сценарий «study» сервер
      // превращает в директиву агенту (формат разбора выберет корневой агент)
      const first = isVideo ? "Начнём разбор видео" : "Начнём изучение с главы 1";
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(first)}&intent=study`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось начать");
    } finally {
      setBusy(false);
    }
  };

  const processedBooks = library.filter((s) => s.kind === "book");
  const pct = job && job.total > 0 ? Math.round((job.progress / job.total) * 100) : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{tab === "book" ? "Изучить книгу" : "Обсудить видео"}</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => v && setTab(v as "book" | "video")}>
          <TabsList className="w-full">
            <TabsTrigger value="book" className="flex-1 gap-1.5">
              <Icon name="auto_stories" size={14} /> Книга
            </TabsTrigger>
            <TabsTrigger value="video" className="flex-1 gap-1.5">
              <Icon name="movie" size={14} /> Видео
            </TabsTrigger>
          </TabsList>

          <TabsContent value="book" className="pt-4">
            {step === "pick" && (
              <div className="flex flex-col gap-3">
                <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground transition hover:border-primary/50 hover:text-foreground">
                  {busy ? <Icon name="progress_activity" size={24} className="animate-spin" /> : <Icon name="upload" size={24} />}
                  {busy ? "Загружаю…" : "Выбери или перетащи PDF-книгу"}
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
                {processedBooks.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-xs text-muted-foreground">или продолжи книгу из библиотеки:</p>
                    <Select onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) void pickLibrary(val); }}>
                      <SelectTrigger aria-label="Книга из библиотеки">
                        <SelectValue placeholder="Выбрать из библиотеки…" />
                      </SelectTrigger>
                      <SelectContent>
                        {processedBooks.map((s) => (
                          <SelectItem key={s.uid} value={s.uid}>
                            <><Icon name="menu_book" size={16} /> {s.title} · {s.chapters_count} гл.</>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="video" className="pt-4">
            {step === "pick" && (
              <div className="flex flex-col gap-3">
                <Input
                  placeholder="https://youtube.com/watch?v=…"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && void startVideo()}
                />
                <Button disabled={busy || !videoUrl.trim()} onClick={startVideo}>
                  {busy ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="movie" size={16} className="mr-1" />}
                  Добавить и обработать
                </Button>
              </div>
            )}
          </TabsContent>

          {step === "processing" && job && (
            <div className="flex flex-col gap-3 py-4">
              <p className="flex items-center gap-2 text-sm font-medium">
                <Icon name="progress_activity" size={16} className="animate-spin" />
                {(sourceKind === "video" ? JOB_LABEL_VIDEO : JOB_LABEL_BOOK)[
                  job.status === "done" ? "summarize_chapters" : "process_source"
                ] ?? "Обрабатываю источник"}
              </p>
              <Progress value={pct ?? 8} />
              <p className="text-xs text-muted-foreground">
                {sourceKind === "video"
                  ? "транскрипт и конспект — до пары минут"
                  : job.total > 0
                    ? `${job.progress}/${job.total} глав`
                    : "это займёт до минуты — нейронка читает книгу"}
              </p>
            </div>
          )}

          {step === "ready" && (
            <div className="flex flex-col gap-4 pt-2">
              <div>
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <Icon name="check_circle" size={16} className="text-emerald-500" />
                  {sourceKind === "video" ? "Видео готово к разбору" : "Карта изучения"}: {sourceTitle}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {sourceKind === "video"
                    ? "транскрипт собран — разберём видео целиком: конспект, понятия, вопросы"
                    : `${chapters.length} ${chapters.length === 1 ? "часть" : "глав"} — идём по порядку, после каждой решаем: дальше, подробнее или сессия`}
                </p>
              </div>
              <div className="max-h-64 overflow-y-auto rounded-xl border">
                {chapters.map((ch) => (
                  <div key={ch.idx} className="border-b px-4 py-2.5 last:border-b-0">
                    <p className="text-sm font-medium">
                      {sourceKind === "video" ? "" : `${ch.idx}. `}
                      {ch.title}
                    </p>
                    {ch.summary && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{ch.summary}</p>}
                  </div>
                ))}
              </div>
              <div className="flex justify-end">
                <Button disabled={busy} onClick={startStudying}>
                  {busy ? (
                    <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
                  ) : sourceKind === "video" ? (
                    <Icon name="movie" size={16} className="mr-1" />
                  ) : (
                    <Icon name="auto_stories" size={16} className="mr-1" />
                  )}
                  Разобрать с агентом
                </Button>
              </div>
            </div>
          )}
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
