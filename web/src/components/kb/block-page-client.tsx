"use client";

/** Страница блока: шапка, тело по секциям, панель (категория, версии, действия).
 *  На широких экранах (lg+) панель справа и сворачивается в узкую полоску,
 *  состояние запоминается; на узких по умолчанию свёрнута (текст на всю ширину),
 *  разворачивается в секцию под текстом. */

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
import { CategorySelect } from "./category-select";
import { apiPost } from "@/lib/api";
import { markKbListDirty } from "@/lib/kb-sync";
import { useStored } from "@/lib/use-stored";
import { useMediaQuery } from "@/lib/use-media";

type Version = { version: number; reason: string | null; conversation_uid: string | null; created_at: string; size: number };

const ASIDE_HIDDEN_KEY = "learnos-kb-block-aside-hidden";
const ASIDE_HIDDEN_EVENT = "learnos-kb-block-aside-hidden-change";

/** Компактная дата для метаданных: «22.10.2026, 16:58». */
const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

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
  const [asideHiddenRaw, setAsideHidden] = useStored(ASIDE_HIDDEN_KEY, ASIDE_HIDDEN_EVENT, "0");
  const asideHidden = asideHiddenRaw === "1";
  // Запомненное состояние относится к боковой панели на широких экранах;
  // на узких панель по умолчанию свёрнута и раскрывается разово, под текст.
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const [narrowOpen, setNarrowOpen] = useState(false);
  const panelVisible = isDesktop ? !asideHidden : narrowOpen;
  const showPanel = () => (isDesktop ? setAsideHidden("0") : setNarrowOpen(true));
  const hidePanel = () => (isDesktop ? setAsideHidden("1") : setNarrowOpen(false));

  const confirmCategory = async () => {
    setConfirming(true);
    try {
      await apiPost(`/kb/blocks/${block.block_uid}/category`, { path: block.category_path, confirm: true });
      markKbListDirty();
      toast.success("Категория подтверждена");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setConfirming(false);
    }
  };

  const moveCategory = async (path: string | null) => {
    setMoving(true);
    try {
      await apiPost(`/kb/blocks/${block.block_uid}/category`, { path, confirm: true });
      markKbListDirty();
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
      markKbListDirty();
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

  const asideBody = (
    <>
      <h2 className="mb-2 font-medium">Категория</h2>
      <CategorySelect
        categories={categories}
        value={block.category_path}
        disabled={moving}
        ariaLabel="Категория блока"
        onSelect={(path) => void moveCategory(path)}
      />
      <p className="mt-1.5 text-xs text-muted-foreground">меняется сразу, история — в версиях</p>

      <h2 className="mb-3 mt-6 font-medium">Действия</h2>
      <div className="flex flex-col gap-2">
        <Button variant="outline" size="sm" className="justify-start whitespace-nowrap" onClick={discussInChat}>
          <>
            <Icon name="chat" size={16} /> Обсудить в чате
          </>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="justify-start whitespace-nowrap"
          onClick={() => {
            navigator.clipboard.writeText(block.content).then(() => toast.success("MD скопирован"));
          }}
        >
          <>
            <Icon name="content_copy" size={16} /> Скопировать MD
          </>
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
          buttonClassName="w-full justify-start whitespace-nowrap border-destructive/40 text-rose-500 hover:text-rose-400"
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
        <div className="whitespace-nowrap">создан: {fmtDate(block.created_at)}</div>
        <div className="whitespace-nowrap">обновлён: {fmtDate(block.updated_at)}</div>
        {block.tags.length > 0 && (
          <div className="truncate" title={block.tags.join(", ")}>
            теги: {block.tags.join(", ")}
          </div>
        )}
        {block.session_uid && (
          <div className="truncate" title={block.session_uid}>
            сессия: {block.session_uid}
          </div>
        )}
      </dl>
    </>
  );

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <article className="min-h-0 min-w-0 flex-1 overflow-y-auto">
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

      {panelVisible ? (
        <aside className="flex max-h-[60vh] w-full shrink-0 flex-col border-t lg:h-full lg:max-h-none lg:w-72 lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between px-4 pb-1 pt-3">
            <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Панель</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="Скрыть панель блока"
              title="Скрыть панель блока"
              onClick={hidePanel}
            >
              <Icon name={isDesktop ? "right_panel_close" : "bottom_panel_close"} size={16} />
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4 pt-2 text-sm">{asideBody}</div>
        </aside>
      ) : (
        <div className="flex h-10 w-full shrink-0 justify-center border-t lg:h-full lg:w-10 lg:border-l lg:border-t-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 self-center"
            aria-label="Показать панель блока"
            title="Показать панель блока"
            onClick={showPanel}
          >
            <Icon name={isDesktop ? "right_panel_open" : "bottom_panel_open"} size={16} />
          </Button>
        </div>
      )}
    </div>
  );
}
