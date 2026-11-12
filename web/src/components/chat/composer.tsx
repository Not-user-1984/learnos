"use client";

/** Композер чата (B-011, вынос из chat-view): вложение PDF, кот-тумблер, ввод,
 *  отправка/стоп. Состояние ввода — у страницы, композер — чистая презентация. */

import { useRef } from "react";
import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CatToggle } from "@/components/chat/chat-cat";

/** Вложение композера: PDF уже загружен в Библиотеку, уйдёт следующим сообщением. */
export type PendingAttachment = { uid: string; title: string };

export type ChatComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSend: (content: string) => void;
  onStop: () => void;
  streaming: boolean;
  /** panel — у читалки, без кота (B-006). */
  variant?: "page" | "panel";
  attachment: PendingAttachment | null;
  onClearAttachment: () => void;
  onPickPdf: (file: File | undefined) => void;
  uploading: boolean;
};

export function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  variant = "page",
  attachment,
  onClearAttachment,
  onPickPdf,
  uploading,
}: ChatComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div className="border-t p-3">
      <div className="mx-auto max-w-3xl">
        {attachment && (
          <div className="mb-2 flex justify-end">
            <div className="flex items-center gap-2 rounded-lg border bg-muted px-3 py-1.5 text-sm">
              <Icon name="picture_as_pdf" size={16} className="shrink-0 text-primary" />
              <span className="max-w-64 truncate">{attachment.title}</span>
              <button
                aria-label="Убрать вложение"
                className="shrink-0 text-muted-foreground transition hover:text-foreground"
                onClick={onClearAttachment}
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            hidden
            onChange={(e) => {
              onPickPdf(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Прикрепить PDF"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? (
              <Icon name="progress_activity" size={16} className="animate-spin" />
            ) : (
              <Icon name="attach_file" size={16} />
            )}
          </Button>
          {variant === "page" && (
            <CatToggle className="inline-flex shrink-0 items-center justify-center rounded-lg p-2 text-muted-foreground transition hover:bg-accent hover:text-foreground" />
          )}
          <Textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend(value);
              }
            }}
            placeholder="Сообщение… (Enter — отправить, Shift+Enter — перенос)"
            className="max-h-40 min-h-10 resize-none"
            rows={1}
          />
          {streaming ? (
            <Button variant="destructive" size="icon" aria-label="Стоп" onClick={onStop}>
              <Icon name="stop_circle" size={16} />
            </Button>
          ) : (
            <Button size="icon" aria-label="Отправить" disabled={!value.trim()} onClick={() => onSend(value)}>
              <Icon name="send" size={16} />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
