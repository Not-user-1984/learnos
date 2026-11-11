"use client";

/** Композер чата: вложение PDF, ввод, отправка/стоп, кот (B-009: вынесено из chat-view). */

import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CatToggle } from "@/components/chat/chat-cat";

export type ComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  uploading: boolean;
  onPickPdf: (file: File | undefined) => void;
  attachment: { uid: string; title: string } | null;
  onRemoveAttachment: () => void;
  fileRef: React.RefObject<HTMLInputElement | null>;
  showCat?: boolean;
};

export function ChatComposer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  uploading,
  onPickPdf,
  attachment,
  onRemoveAttachment,
  fileRef,
  showCat = true,
}: ComposerProps) {
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
                    onClick={onRemoveAttachment}
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
              {showCat && (
                <CatToggle className="inline-flex shrink-0 items-center justify-center rounded-lg p-2 text-muted-foreground transition hover:bg-accent hover:text-foreground" />
              )}
              <Textarea
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSend();
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
                <Button size="icon" aria-label="Отправить" disabled={!value.trim()} onClick={onSend}>
                  <Icon name="send" size={16} />
                </Button>
              )}
            </div>
          </div>
        </div>
  );
}
