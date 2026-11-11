"use client";

/** Карточки блоков: сохранён/обновлён + превью конспекта с апрувом (B-003: статус на сервере). */

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { NoteDraft } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Mermaid } from "@/components/markdown/Mermaid";
import type { CardProps } from "./shared";
import { resolveCard, useCardState } from "./shared";

/** Блок записан (урок/конспект) или обновлён — ссылкой в базу, откат версии. */
export function BlockCard({ card }: CardProps) {
  const [restoring, setRestoring] = useState(false);
  if (card.type === "block_saved") {
    return (
      <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
        <p className="mb-1 flex items-center gap-2 text-sm font-medium">
          <Icon name="check" size={16} className="text-emerald-500" /> Блок сохранён ({card.kind === "lesson" ? "урок" : "конспект"})
        </p>
        <p className="font-medium">{card.title}</p>
        {card.summary && <p className="mt-1 text-sm text-muted-foreground">{card.summary}</p>}
        {(card.category || card.category_suggested) && (
          <p className="mt-2 text-sm">
            Категория: <b>{card.category ?? card.category_suggested}</b> — поменять можно на{" "}
            <Link className="text-primary hover:underline" href={`/kb/${card.block_uid}`}>
              странице блока
            </Link>
          </p>
        )}
        <Link href={`/kb/${card.block_uid}`} className="mt-2 inline-block text-sm text-primary hover:underline">
          Открыть блок →
        </Link>
      </div>
    );
  }
  return (
    <div className="rounded-xl border p-4">
      <p className="mb-1 text-sm font-medium">
        Блок обновлён: {card.title} (v{card.from_version} → v{card.to_version})
      </p>
      {card.reason && <p className="text-sm text-muted-foreground">{card.reason}</p>}
      <div className="mt-2 flex gap-2">
        <Link href={`/kb/${card.block_uid}`} className="text-sm text-primary hover:underline">
          Посмотреть
        </Link>
        <button
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
          disabled={restoring}
          onClick={async () => {
            setRestoring(true);
            try {
              const res = await fetch(`/api/kb/blocks/${card.block_uid}/restore/${card.from_version}`, { method: "POST" });
              if (!res.ok) throw new Error(String(res.status));
              toast.success(`Откат к v${card.from_version}`);
            } catch {
              toast.error("Откат не удался");
            } finally {
              setRestoring(false);
            }
          }}
        >
          {restoring && <Icon name="progress_activity" size={12} className="animate-spin" />}
          Откатить к v{card.from_version}
        </button>
      </div>
    </div>
  );
}

/** Превью конспекта: апрув → resolve + сообщение; записанный блок открывает ссылку. */
export function NoteDraftCard({ card, onInsert, onSend, conversationUid, noteSavedBlockUid }: CardProps) {
  const [state, setState] = useCardState(card);
  const [busy, setBusy] = useState(false);
  const d: NoteDraft | undefined = card.draft;
  if (!d) return null;

  const approve = () => {
    if (!onSend || busy || state.status === "resolved") return;
    setBusy(true);
    setState({ status: "resolved", choice: "approved" });
    void resolveCard(conversationUid, card.card_id, "approved");
    onSend(`Апрув: записывай этот блок в базу как есть (превью #${card.preview_id}).`);
  };

  return (
    <div className="rounded-xl border border-sky-500/40 bg-sky-500/5 p-4">
      <p className="mb-1 flex items-center gap-2 text-sm font-medium">
        <Icon name="edit_note" size={16} className="text-sky-500" /> Превью конспекта
        {card.preview_id ? ` #${card.preview_id}` : ""} · ничего не записано
      </p>
      <p className="font-medium">{d.title}</p>
      {d.summary && <p className="mt-1 text-sm text-muted-foreground">{d.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {d.category_suggestion && (
          <Badge className="bg-primary/15 text-primary">категория: {d.category_suggestion}</Badge>
        )}
        {(d.tags ?? []).map((t) => (
          <Badge key={t} variant="outline">
            {t}
          </Badge>
        ))}
      </div>

      {(d.concepts?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Ключевые понятия</p>
          <ul className="mt-1 space-y-1 text-sm">
            {(d.concepts ?? []).map((c, i) => (
              <li key={i}>
                <b>{c.term}</b> — {c.definition}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(d.theses?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Тезисы</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(d.theses ?? []).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {(d.my_examples?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Мои примеры</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(d.my_examples ?? []).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {(d.weak_spots?.length ?? 0) > 0 && (
        <div className="mt-3 rounded-md bg-amber-500/10 px-3 py-2">
          <p className="text-xs font-medium uppercase tracking-wide text-amber-600 dark:text-amber-400">
            Дозакрепить
          </p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(d.weak_spots ?? []).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {(d.open_questions?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Вопросы на потом</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(d.open_questions ?? []).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
      {d.mermaid && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Схема</p>
          <Mermaid code={d.mermaid} />
        </div>
      )}

      {state.status === "resolved" ? (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Icon name="check" size={14} className="text-emerald-500" />
          {noteSavedBlockUid ? (
            <>
              записано —{" "}
              <Link href={`/kb/${noteSavedBlockUid}`} className="text-primary hover:underline">
                открыть блок →
              </Link>
            </>
          ) : (
            "записываем — блок появится следом"
          )}
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {onSend ? (
            <Button size="sm" disabled={busy} onClick={approve}>
              {busy ? (
                <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
              ) : (
                <Icon name="check" size={16} className="mr-1" />
              )}
              Записать в базу
            </Button>
          ) : (
            <Button size="sm" disabled>
              <Icon name="check" size={16} className="mr-1" /> Записать в базу
            </Button>
          )}
          {onInsert && (
            <Button size="sm" variant="outline" onClick={() => onInsert(`Поправим конспект (превью #${card.preview_id}): `)}>
              <Icon name="edit" size={16} className="mr-1" /> Поправить
            </Button>
          )}
          <span className="text-xs text-muted-foreground">
            правки можно писать словами — «это уберём», «это дополним», соберу новое превью
          </span>
        </div>
      )}
    </div>
  );
}
