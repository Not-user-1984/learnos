"use client";

/** Статус-бары чата: прогресс книги, панель и aside сессии (B-009). */

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import type { AgentState, ConversationDetail, ReviewProgress } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const SESSION_STEPS = ["theory", "check", "practice", "debrief", "done"];
const STEP_LABELS: Record<string, string> = { theory: "Теория", check: "Вопросы", practice: "Практика", debrief: "Разбор", done: "Готово" };

export function ReviewProgressBar({ progress }: { progress: ReviewProgress }) {
  const { done_chapters: done, total_chapters: total } = progress;
  const finished = progress.status === "done" || done >= total;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  // до ~30 глав — сегменты по главам (видно, какие разобраны и какая сейчас); дальше — полоса
  const segmented = total <= 30;
  return (
    <div className="border-b px-4 py-2">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Icon
            name={finished ? "task_alt" : "auto_stories"}
            size={15}
            className="shrink-0 text-primary"
          />
          <span className="min-w-0 shrink truncate font-medium">{progress.title}</span>
          <span className="shrink-0 tabular-nums">
            {done}/{total} глав
          </span>
          <span
            className={cn(
              "ml-auto min-w-0 shrink truncate",
              finished && "text-emerald-600 dark:text-emerald-400",
            )}
          >
            {finished ? "книга разобрана" : progress.current_title ? `сейчас: ${progress.current_title}` : ""}
          </span>
        </div>
        {segmented ? (
          <div className="mt-1.5 flex gap-0.5" role="img" aria-label={`Пройдено ${done} из ${total} глав`}>
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 flex-1 rounded-full",
                  i < done ? "bg-primary" : i === done && !finished ? "bg-primary/40" : "bg-muted",
                )}
              />
            ))}
          </div>
        ) : (
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function SessionPanelDialog({ session }: { session: NonNullable<ConversationDetail["session"]> }) {
  const [open, setOpen] = useState(false);
  const done = SESSION_STEPS.indexOf(session.state) + 1;
  return (
    <div className="lg:hidden">
      <button
        onClick={() => setOpen(true)}
        className="flex shrink-0 items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground transition hover:text-foreground"
        aria-label="Прогресс сессии"
      >
        <span className="flex gap-0.5">
          {SESSION_STEPS.map((st, i) => (
            <span
              key={st}
              className={cn("h-1.5 w-1.5 rounded-full", i < done ? "bg-emerald-500" : "bg-muted-foreground/30")}
            />
          ))}
        </span>
        {done}/{SESSION_STEPS.length}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xs">
          <DialogHeader>
            <DialogTitle>Сессия</DialogTitle>
          </DialogHeader>
          <ol className="flex flex-col gap-1 text-sm">
            {SESSION_STEPS.map((st) => (
              <li key={st} className={cn("flex items-center gap-2 rounded-md px-2 py-1.5", session.state === st && "bg-accent")}>
                <span className={cn("h-2 w-2 rounded-full", SESSION_STEPS.indexOf(st) <= SESSION_STEPS.indexOf(session.state) ? "bg-emerald-500" : "bg-muted-foreground/30")} />
                {STEP_LABELS[st]}
              </li>
            ))}
          </ol>
          {session.chapter_idx && <p className="mt-2 text-muted-foreground">Глава {session.chapter_idx}</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Aside сессии на десктопе — один источник вместо копии в chat-view (B-009). */
export function SessionAside({ session }: { session: NonNullable<ConversationDetail["session"]> }) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-4 border-l p-4 text-sm lg:flex">
      <div>
        <h2 className="mb-2 font-medium">Сессия</h2>
        <ol className="flex flex-col gap-1">
          {SESSION_STEPS.map((st) => (
            <li key={st} className={cn("flex items-center gap-2 rounded-md px-2 py-1", session.state === st && "bg-accent")}>
              <span className={cn("h-2 w-2 rounded-full", SESSION_STEPS.indexOf(st) <= SESSION_STEPS.indexOf(session.state) ? "bg-emerald-500" : "bg-muted-foreground/30")} />
              {STEP_LABELS[st]}
            </li>
          ))}
        </ol>
      </div>
      {session.chapter_idx && <p className="text-muted-foreground">Глава {session.chapter_idx}</p>}
      <Link href="/kb?view=inbox" className="text-primary hover:underline">
        Входящие блоков →
      </Link>
    </aside>
  );
}

/** Живой статус агента: бейдж работы / баннер прерывания (B-009). */
export function AgentStateBanner({
  agentState,
  reconnecting,
  busyHint,
  onStop,
  onResume,
}: {
  agentState: AgentState | null;
  reconnecting: boolean;
  busyHint: string | null;
  onStop: () => void;
  onResume: () => void;
}) {
  if (!(agentState?.working || agentState?.interrupted || reconnecting || busyHint)) return null;
  return (
    <div className="flex flex-col gap-1.5 border-b px-4 py-2">
      {agentState?.working && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Icon name="progress_activity" size={15} className="animate-spin shrink-0" />
          <span className="min-w-0">
            агент работает:{" "}
            {agentState.runs
              .map((r) => [r.agent, r.steps ? `шаг ${r.steps}` : "", r.current].filter(Boolean).join(" · "))
              .join(" / ") || "…"}
          </span>
          <Button size="sm" variant="outline" className="ml-auto shrink-0" onClick={onStop}>
            <Icon name="stop_circle" size={14} /> Остановить
          </Button>
          {reconnecting && <span className="text-amber-600 dark:text-amber-400">· связь прервалась, догоняю ответ…</span>}
        </p>
      )}
      {busyHint && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="hourglass_top" size={15} className="shrink-0 text-primary" />
          {busyHint}
        </p>
      )}
      {!agentState?.working && reconnecting && (
        <p className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
          <Icon name="progress_activity" size={15} className="animate-spin" /> связь прервалась — догоняю ответ агента…
        </p>
      )}
      {agentState?.interrupted && !agentState.working && (
        <div className="flex items-center gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-sm">
          <Icon name="restart_alt" size={16} className="shrink-0 text-amber-600 dark:text-amber-400" />
          <span className="flex-1">Генерация прервана — сервер перезапускался. Ответ можно дописать.</span>
          <Button size="sm" variant="outline" onClick={onResume}>
            Продолжить
          </Button>
        </div>
      )}
    </div>
  );
}

/** Баннер ошибки агента с «Повторить» (B-009). */
export function StreamErrorBar({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mx-auto mb-2 max-w-3xl px-4">
      <div className="flex items-center gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2.5 text-sm">
        <span className="text-rose-500">⚠</span>
        <span className="flex-1">Ошибка агента: {message}</span>
        <Button size="sm" variant="outline" onClick={onRetry}>
          Повторить
        </Button>
      </div>
    </div>
  );
}
