"use client";

/** Сообщение ленты и чипы инструментов (B-009). */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { Markdown } from "@/components/markdown/Markdown";
import { CardView, stripCommandFences } from "@/components/chat/cards";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

export type ToolChip = {
  call_id: string;
  name: string;
  label: string;
  ok?: boolean;
  summary?: string;
  open?: boolean;
  count?: number;
};

const CHAT_PROSE = "prose-headings:mt-5 prose-headings:mb-2 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:my-3";

export function Message({
  message,
  onInsert,
  onSend,
  conversationUid,
  noteSavedBlockUid,
  onTimecode,
}: {
  message: ChatMessage;
  onInsert?: (t: string) => void;
  onSend?: (t: string) => void;
  conversationUid?: string;
  noteSavedBlockUid?: string;
  onTimecode?: (seconds: number) => void;
}) {
  const time = new Date(message.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (message.role === "user") {
    const attached = (message.cards ?? []).filter((c) => c.type === "attachment");
    return (
      <div className="flex flex-col items-end gap-1.5">
        <p className="px-1 text-xs text-muted-foreground">
          Ты · {time}
        </p>
        <div className="user-bubble max-w-[85%] rounded-2xl bg-primary px-4 py-2.5 text-primary-foreground">
          <Markdown content={message.content} className="[&_p]:my-0" />
        </div>
        {attached.map((c, i) => (
          <div key={i} className="flex items-center gap-2 rounded-lg border bg-muted px-3 py-1.5 text-sm">
            <Icon name="picture_as_pdf" size={16} className="shrink-0 text-primary" />
            <span className="max-w-64 truncate">{c.title}</span>
          </div>
        ))}
      </div>
    );
  }
  // команда показывается один раз: fenced-дубль карточки command гасится (B-003)
  const commandTexts = new Set(
    (message.cards ?? [])
      .filter((c) => c.type === "command" && (c.command ?? "").trim())
      .map((c) => (c.command ?? "").trim()),
  );
  return (
    <div className="flex flex-col gap-2">
      <p className="flex items-center gap-1 px-1 text-xs text-muted-foreground"><Icon name="smart_toy" size={14} /> Агент · {time}</p>
      <div className="rounded-2xl border bg-muted/50 px-5 py-4">
        <Markdown
          content={stripCommandFences(message.content, commandTexts)}
          className={CHAT_PROSE}
          onTimecode={onTimecode}
        />
      </div>
      {message.cards?.map((c, i) => (
        <CardView
          key={c.card_id ?? i}
          card={c}
          onInsert={onInsert}
          onSend={onSend}
          conversationUid={conversationUid}
          noteSavedBlockUid={noteSavedBlockUid}
        />
      ))}
    </div>
  );
}

export function ToolChipView({ chip }: { chip: ToolChip }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
          chip.ok === false
            ? "border-rose-500/40 text-rose-500"
            : chip.ok
              ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
              : "text-muted-foreground",
        )}
      >
        <Icon name="terminal" size={12} />
        {chip.label || chip.name}
        {(chip.count ?? 1) > 1 && (
          <span
            key={chip.count}
            className="rounded-full bg-muted px-1.5 py-px text-[10px] font-medium tabular-nums animate-in fade-in zoom-in duration-300"
          >
            ×{chip.count}
          </span>
        )}
        {chip.ok === undefined && <Icon name="progress_activity" size={12} className="animate-spin" />}
      </button>
      {open && chip.summary && <p className="mt-1 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">{chip.summary}</p>}
    </div>
  );
}

export function EmptyHint() {
  return (
    <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
      Спроси что угодно. Агент ищет по базе знаний, правит блоки по просьбе («добавь в блок про поды…») и сохраняет конспекты по слову «сохрани».
    </p>
  );
}

/** note_draft → uid ближайшего block_saved ПОЗЖЕ этого сообщения: превью,
 *  по которому блок уже записан, показывает ссылку вместо кнопок (B-003). */
export function noteDraftOutcomes(messages: ChatMessage[]): Map<number, string | undefined> {
  const out = new Map<number, string | undefined>();
  let saved: string | undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "assistant") continue;
    const bs = (m.cards ?? []).find((c) => c.type === "block_saved" && c.block_uid);
    if (bs?.block_uid) saved = bs.block_uid;
    if ((m.cards ?? []).some((c) => c.type === "note_draft")) out.set(m.id, saved);
  }
  return out;
}
