"use client";

/** Стартовый экран чата — единый вход: приветствие + крупный инпут по центру,
 *  сценарные кнопки LearnOS под инпутом и история разговоров ниже. При фокусе/вводе
 *  кнопки и история плавно сворачиваются — экран становится «чистый диалог ждёт начала».
 *  Новый разговор всегда root-агент; сценарий уходит серверу параметром (intent). */

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { modeIcon, modeLabel } from "@/lib/format";
import type { ConversationItem } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { StudyFlowDialog } from "@/components/chat/study-flow";
import { CatToggle, ChatCat } from "@/components/chat/chat-cat";
import { cn } from "@/lib/utils";
import { CHAT_SCENARIOS } from "@/lib/scenarios";

/** Фразы приветствия: одна на заход, случайная. Пополняется без логики. */
const TAGLINES = [
  "Тут скиллы прокачивают человеческие скиллы",
  "Учимся всерьёз, но не по-взрослому",
  "Твой личный Harness для прокачки мозга",
  "Знания приживаются здесь",
  "Сессия 30 минут — блок в базе навсегда",
];

/** Логотип-маскот: линейный силуэт сидящего кота, красится темой через currentColor. */
function CatMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 54c0-18 4-28 12-34l-3-11 9 5.5c2-.5 4-.5 6 0l9-5.5-3 11c8 6 12 16 12 34Z" />
      <path d="M13 50C4 48 2 39 9 36c5-2 9 1 9 5" />
      <circle cx="27" cy="24" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="37" cy="24" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Плавное сворачивание секции: высота через grid-template-rows + прозрачность. */
function Collapse({ collapsed, children }: { collapsed: boolean; children: React.ReactNode }) {
  return (
    <div
      aria-hidden={collapsed}
      className={cn(
        "grid overflow-hidden transition-all duration-300 motion-reduce:transition-none",
        collapsed ? "pointer-events-none grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100",
      )}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

/** Сценарная кнопка стартового экрана. */
function ScenarioButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3.5 py-2 text-sm text-foreground transition hover:border-primary/50 hover:bg-accent"
    >
      <Icon name={icon} size={16} className="text-primary" />
      {label}
    </button>
  );
}

/** Строка истории: иконка, заголовок, сценарий, дата; удаление по ховеру. */
function HistoryRow({ conv }: { conv: ConversationItem }) {
  return (
    <div className="group relative flex items-center gap-3 rounded-xl border bg-card px-4 py-2.5 transition hover:border-primary/50">
      <Link href={`/chat/${conv.uid}`} className="flex min-w-0 flex-1 items-center gap-3">
        <Icon name={modeIcon(conv.mode)} size={18} className="shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{conv.title}</p>
          <p className="truncate text-xs text-muted-foreground">{conv.scenario || modeLabel(conv.mode)}</p>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {new Date(conv.updated_at).toLocaleDateString("ru-RU")}
        </span>
      </Link>
      <ConfirmDeleteButton
        endpoint={`/conversations/${conv.uid}`}
        title="Удалить разговор?"
        name={conv.title}
        description="Сообщения разговора удалятся безвозвратно. Блоки базы знаний, созданные по нему, останутся."
        successMessage="Разговор удалён"
        className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 transition group-hover:opacity-100"
        buttonClassName="rounded-lg bg-background/60 p-1.5 text-muted-foreground backdrop-blur transition hover:text-rose-500"
      />
    </div>
  );
}

export function ChatStart({ conversations }: { conversations: ConversationItem[] }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [research, setResearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flow, setFlow] = useState<"book" | "video" | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // одна случайная фраза на заход; сервер выберет другую — suppressHydrationWarning
  // оставит клиентскую без предупреждения
  const [tagline] = useState(() => TAGLINES[Math.floor(Math.random() * TAGLINES.length)]);

  const collapsed = focused || text.trim().length > 0;

  /** Первый вопрос создаёт root-разговор; интент и ресэрч уходят параметрами. */
  const start = async (content: string, opts?: { intent?: string; research?: boolean }) => {
    if (!content.trim() || busy) return;
    setBusy(true);
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {});
      const params = new URLSearchParams({ initial: content.trim() });
      if (opts?.research) params.set("research", "1");
      if (opts?.intent) params.set("intent", opts.intent);
      router.push(`/chat/${conv.uid}?${params.toString()}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать разговор");
      setBusy(false);
    }
  };

  /** Кнопка-подсказка: подставляет заготовку в инпут, пользователь дописывает тему. */
  const prefill = (lead: string) => {
    setText((t) => (t.trim() ? t : lead));
    inputRef.current?.focus();
  };

  /** Один сценарий — одно поведение и здесь, и в NextSteps разговора (B-003). */
  const runScenario = (id: string) => {
    const s = CHAT_SCENARIOS.find((x) => x.id === id);
    if (!s) return;
    if (s.action.kind === "prefill") prefill(s.action.text);
    else void start(s.action.initial, { intent: s.action.intent });
  };

  return (
    <div className="relative h-full">
      <div className="h-full overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center px-4 py-10">
          <div className="mb-6 flex flex-col items-center gap-3">
            <div className="flex items-center gap-3">
              <CatMark className="h-14 w-14 text-primary" />
              <span className="text-4xl font-medium tracking-tight" style={{ fontFamily: "var(--font-serif)" }}>
                LearnOS
              </span>
            </div>
            <h1 className="text-2xl font-semibold">Привет! Что изучаем?</h1>
            <p suppressHydrationWarning className="min-h-6 text-sm text-muted-foreground">
              {tagline}
            </p>
          </div>

          {research && (
            <div className="mx-auto mb-3 flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-sm text-primary">
              <Icon name="public" size={14} />
              ресёрч-режим: тема уйдёт в поиск по сети
              <button
                type="button"
                aria-label="Выключить ресэрч-режим"
                className="rounded-full p-0.5 transition hover:bg-primary/20"
                onClick={() => setResearch(false)}
              >
                <Icon name="close" size={14} />
              </button>
            </div>
          )}

          <div className="rounded-2xl border bg-card p-2 shadow-sm">
            <Textarea
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void start(text, { research });
                }
              }}
              placeholder={
                research
                  ? "Тема для ресёрча — например: observability в Kubernetes…"
                  : "Спроси что угодно, кинь ссылку или начни сценарий…"
              }
              className="min-h-16 resize-none border-0 bg-transparent px-3 py-2 text-base focus-visible:ring-0"
              rows={2}
            />
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-xs text-muted-foreground">Enter — отправить · Shift+Enter — перенос</span>
              <Button
                size="icon"
                aria-label="Начать разговор"
                disabled={busy || !text.trim()}
                onClick={() => void start(text, { research })}
              >
                {busy ? (
                  <Icon name="progress_activity" size={16} className="animate-spin" />
                ) : (
                  <Icon name="send" size={16} />
                )}
              </Button>
            </div>
          </div>

          <Collapse collapsed={collapsed}>
            <div className="flex flex-wrap items-center justify-center gap-2 pt-5">
              {CHAT_SCENARIOS.map((s) => (
                <ScenarioButton key={s.id} icon={s.icon} label={s.label} onClick={() => runScenario(s.id)} />
              ))}
              <ScenarioButton
                icon="public"
                label="Ресёрч темы"
                onClick={() => {
                  setResearch(true);
                  inputRef.current?.focus();
                }}
              />
              <ScenarioButton icon="auto_stories" label="Изучить книгу" onClick={() => setFlow("book")} />
              <ScenarioButton icon="movie" label="Обсудить видео" onClick={() => setFlow("video")} />
              <CatToggle className="inline-flex h-9 w-9 items-center justify-center rounded-full border text-muted-foreground transition hover:bg-accent hover:text-foreground" />
            </div>
          </Collapse>
        </div>

        <Collapse collapsed={collapsed}>
          {conversations.length > 0 && (
            <section className="mx-auto w-full max-w-3xl px-4 pb-8">
              <h2 className="mb-2 text-sm font-medium text-muted-foreground">Недавние разговоры</h2>
              <div className="flex flex-col gap-1.5">
                {conversations.map((c) => (
                  <HistoryRow key={c.uid} conv={c} />
                ))}
              </div>
            </section>
          )}
        </Collapse>

        <StudyFlowDialog open={flow !== null} onOpenChange={(v) => !v && setFlow(null)} defaultTab={flow ?? "book"} />
      </div>
      <ChatCat />
    </div>
  );
}
