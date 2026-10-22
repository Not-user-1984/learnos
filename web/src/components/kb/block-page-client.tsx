"use client";

/** Страница блока: шапка, тело по секциям, правая колонка (категория, версии, действия). */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import type { BlockDetail, CategoryNode } from "@/lib/types";
import { Markdown } from "@/components/markdown/Markdown";
import { Icon } from "@/components/ui/icon";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiPost } from "@/lib/api";

type Version = { version: number; reason: string | null; conversation_uid: string | null; created_at: string; size: number };

export function BlockPageClient({
  block,
  versions,
  categories = [],
}: {
  block: BlockDetail;
  versions: Version[];
  categories?: CategoryNode[];
}) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [moving, setMoving] = useState(false);
  const [viewVersion, setViewVersion] = useState<number | null>(null);
  const [versionContent, setVersionContent] = useState<string | null>(null);

  const confirmCategory = async () => {
    setConfirming(true);
    try {
      await apiPost(`/kb/blocks/${block.block_uid}/category`, { path: block.category_path, confirm: true });
      toast.success("Категория подтверждена");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setConfirming(false);
    }
  };

  const moveCategory = async (value: string) => {
    const path = value === "__none__" ? null : value;
    setMoving(true);
    try {
      await apiPost(`/kb/blocks/${block.block_uid}/category`, { path, confirm: true });
      toast.success(path ? `Категория: ${path}` : "Категория убрана");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setMoving(false);
    }
  };

  const showVersion = async (v: number) => {
    if (viewVersion === v) {
      setViewVersion(null);
      return;
    }
    try {
      const res = await fetch(`/api/kb/blocks/${block.block_uid}/versions/${v}`);
      const body = (await res.json()) as { content: string };
      setVersionContent(body.content);
      setViewVersion(v);
    } catch {
      toast.error("Не удалось загрузить версию");
    }
  };

  const restore = async (v: number) => {
    try {
      await apiPost(`/kb/blocks/${block.block_uid}/restore/${v}`, {});
      toast.success(`Откат к версии ${v}`);
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    }
  };

  const discussInChat = async () => {
    try {
      const res = await fetch(`/api/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "free", focus_block: block.block_uid, title: `Обсуждение: ${block.title}` }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const conv = (await res.json()) as { uid: string };
      router.push(`/chat/${conv.uid}`);
    } catch {
      toast.error("API недоступен из браузера — используйте прокси");
    }
  };

  return (
    <div className="flex h-full">
      <article className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-10 sm:px-10">
        <header className="mb-10">
          {block.category_path && (
            <p className="mb-2 text-sm text-muted-foreground">
              {block.category_path.split("/").map((seg, i, arr) => (
                <span key={seg}>
                  {seg}
                  {i < arr.length - 1 && " / "}
                </span>
              ))}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold">{block.title}</h1>
            <Badge variant="outline">{block.kind === "lesson" ? "урок" : "конспект"}</Badge>
            {block.version > 1 && <Badge variant="secondary">v{block.version}</Badge>}
            {block.category_status === "suggested" && (
              <Badge className="gap-1 bg-primary/15 text-primary hover:bg-primary/25">
                категория не подтверждена
              </Badge>
            )}
          </div>
          {block.summary && <p className="mt-2 text-muted-foreground">{block.summary}</p>}
          {block.category_status === "suggested" && block.category_path && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
              Агент предлагает категорию: <b>{block.category_path}</b>
              <Button size="sm" className="ml-auto" onClick={confirmCategory} disabled={confirming}>
                Принять
              </Button>
            </div>
          )}
        </header>

        {viewVersion !== null && (
          <section className="mb-6 rounded-lg border border-amber-500/40 bg-amber-500/5 p-4">
            <h2 className="mb-2 text-sm font-medium">Версия {viewVersion} (просмотр)</h2>
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">{versionContent}</pre>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => restore(viewVersion)}>
              Откатить к этой версии
            </Button>
          </section>
        )}

        <Markdown content={block.content} linkTitles={Object.fromEntries(block.links.map((l) => [l, l]))} />

        {block.back_links.length > 0 && (
          <section className="mt-12">
            <h2 className="mb-2 text-sm font-medium text-muted-foreground">Ссылается на этот блок</h2>
            <div className="flex flex-wrap gap-2">
              {block.back_links.map((uid) => (
                <Link key={uid} href={`/kb/${uid}`}>
                  <Badge variant="outline">{uid}</Badge>
                </Link>
              ))}
            </div>
          </section>
        )}
        </div>
      </article>

      <aside className="w-72 shrink-0 overflow-y-auto border-l p-4 text-sm">
        <h2 className="mb-2 font-medium">Категория</h2>
        <Select
          disabled={moving}
          onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) void moveCategory(val); }}
        >
          <SelectTrigger className="h-9 w-full text-xs" aria-label="Категория блока">
            <SelectValue placeholder={block.category_path ?? "Без категории"} />
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
        <p className="mt-1.5 text-xs text-muted-foreground">меняется сразу, история — в версиях</p>

        <h2 className="mb-3 mt-6 font-medium">Действия</h2>
        <div className="flex flex-col gap-2">
          <Button variant="outline" size="sm" onClick={discussInChat}>
            <><Icon name="chat" size={16} /> Обсудить в чате</>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              navigator.clipboard.writeText(block.content).then(() => toast.success("MD скопирован"));
            }}
          >
            📋 Скопировать MD
          </Button>
          <a href={`/api/kb/blocks/${block.block_uid}/raw`} className="text-primary hover:underline">
            Скачать .md
          </a>
          <ConfirmDeleteButton
            endpoint={`/kb/blocks/${block.block_uid}`}
            title="Удалить блок?"
            name={block.title}
            description="Блок исчезнет из базы знаний вместе с версиями и поисковым индексом — знания пропадут. Если блок входит в курс, удаление будет запрещено."
            successMessage="Блок удалён"
            redirectTo="/kb"
            appearance="button"
            label="Удалить блок"
            buttonClassName="w-full justify-start border-destructive/40 text-rose-500 hover:text-rose-400"
          />
        </div>

        <h2 className="mb-3 mt-6 font-medium">Версии ({versions.length})</h2>
        <div className="flex flex-col gap-1">
          <p className="rounded-md border bg-card px-2 py-1.5">v{block.version} — текущая</p>
          {versions.map((v) => (
            <div key={v.version} className="flex items-center gap-1 rounded-md border px-2 py-1.5">
              <span className="flex-1 truncate" title={v.reason ?? ""}>
                v{v.version} · {v.reason ?? "правка"}
              </span>
              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => showVersion(v.version)}>
                смотреть
              </Button>
            </div>
          ))}
          {versions.length === 0 && <p className="text-muted-foreground">правок ещё не было</p>}
        </div>

        <h2 className="mb-3 mt-6 font-medium">Метаданные</h2>
        <dl className="space-y-1 text-xs text-muted-foreground">
          <div>создан: {new Date(block.created_at).toLocaleString("ru-RU")}</div>
          <div>обновлён: {new Date(block.updated_at).toLocaleString("ru-RU")}</div>
          {block.tags.length > 0 && <div>теги: {block.tags.join(", ")}</div>}
          {block.session_uid && <div>сессия: {block.session_uid}</div>}
        </dl>
      </aside>
    </div>
  );
}

function flatten(nodes: CategoryNode[]): CategoryNode[] {
  return nodes.flatMap((n) => [n, ...flatten(n.children)]);
}
