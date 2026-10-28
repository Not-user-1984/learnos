"use client";

/** Приём «Поделиться → LearnOS»: ссылка становится источником в Библиотеке. */

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";

function ShareForm() {
  const sp = useSearchParams();
  const router = useRouter();
  // Android часто кладёт ссылку в text; достаём первый URL из text или url
  const sharedUrl = (sp.get("url") ?? "") || (sp.get("text") ?? "").match(/https?:\/\/\S+/)?.[0] || "";
  const sharedTitle =
    sp.get("title") || (sharedUrl.includes("youtu") ? "YouTube-видео" : sharedUrl ? "Ссылка" : "");
  // state — только пользовательская правка поля; изначальное значение производное от URL
  const [urlDraft, setUrlDraft] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [result, setResult] = useState<{ uid: string; kind: string; processed: boolean } | null>(null);

  const url = urlDraft ?? sharedUrl;
  const title = sharedTitle;
  const isYoutube = /youtu\.?be/i.test(url);
  const kind = isYoutube ? "video" : "web";

  const save = async () => {
    setStatus("saving");
    try {
      const src = await apiPost<{ uid: string; id: number }>("/sources", { kind, title: title || url, url });
      let processed = false;
      if (isYoutube) {
        await apiPost(`/sources/${src.id}/process`, {}).then(() => {
          processed = true;
        });
      }
      setResult({ uid: src.uid, kind, processed });
      setStatus("done");
    } catch {
      setStatus("error");
    }
  };

  /** Root-разговор с распознанным контентом: ссылка уйдёт первым сообщением,
   *  агент сам предложит разбор (претрекер контента — T-036). */
  const discuss = async () => {
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {});
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(url)}`);
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col gap-4 p-8">
      <h1 className="text-lg font-semibold">Поделиться с LearnOS</h1>
      {!url ? (
        <p className="text-sm text-muted-foreground">Ссылка не найдена. Вставь её вручную:</p>
      ) : (
        <p className="break-all rounded-lg border bg-card p-3 text-sm">{url}</p>
      )}
      <input
        className="rounded-md border bg-background px-3 py-2 text-sm"
        placeholder={url ? url : "https://…"}
        value={url}
        onChange={(e) => setUrlDraft(e.target.value)}
        aria-label="Ссылка"
      />
      {status === "done" && result ? (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          Источник добавлен{result.processed ? " и обрабатывается" : ""} ({result.kind === "video" ? "видео" : "веб"}).
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => router.push(`/library/${result.uid}`)}>
              Открыть в Библиотеке
            </Button>
            <Button size="sm" onClick={() => void discuss()}>
              Обсудить в чате
            </Button>
          </div>
        </div>
      ) : (
        <Button disabled={!url || status === "saving"} onClick={save}>
          {status === "saving" ? "Добавляю…" : isYoutube ? "Добавить видео и обработать" : "Добавить в Библиотеку"}
        </Button>
      )}
      {status === "error" && <p className="text-sm text-rose-500">Не удалось добавить — попробуй ещё раз.</p>}
    </div>
  );
}

export default function SharePage() {
  return (
    <Suspense fallback={<p className="p-8 text-sm text-muted-foreground">Читаю ссылку…</p>}>
      <ShareForm />
    </Suspense>
  );
}
