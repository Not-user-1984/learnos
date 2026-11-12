"use client";

/** Хук SSE-стрима чата (B-011): цикл событий → live-состояние ленты + колбэки страницы.
 *
 * Хук владеет стримом (стримящийся текст, чипы инструментов, живые карточки,
 * стоп/ошибки); состояние страницы (сессия, review-progress, title, лента
 * сообщений) обновляется через колбэки — компонент решает, что с ними делать. */

import { useRef, useState } from "react";
import { toast } from "sonner";
import type { ChatMessage, ReviewProgress, SseEvent } from "@/lib/types";
import { streamChat, streamResume } from "@/lib/chat/stream";
import type { ToolChip } from "@/components/chat/message";

/** Патч события session — панель сессии живёт по данным события. */
export type SessionEvent = {
  session_uid?: string;
  state: string;
  allowed_events: string[];
  chapter_idx?: number | null;
};

/** Итог стрима: busy — 409 (сообщение не ушло), reconnecting — оборвался без
 *  финала (продолжит опрос статуса), settled — штатно/ошибка/стоп (перечитать). */
export type StreamOutcome = "busy" | "reconnecting" | "settled";

export type UseChatStreamOptions = {
  conversationUid: string;
  /** событие session: панель урока может появиться первым же событием */
  onSession: (data: SessionEvent) => void;
  onTitle: (title: string) => void;
  /** handoff: бейдж «ведёт: …» */
  onActiveAgent: (agent: string) => void;
  onReviewProgress: (progress: ReviewProgress) => void;
  /** done с содержимым: готовое сообщение ассистента в ленту страницы */
  onAssistantMessage: (message: ChatMessage) => void;
  /** 409-конфликт: агент уже отвечает — сообщение не сохранилось */
  onBusy: (message: string) => void;
  onStreamError: (message: string) => void;
  onFinish: (outcome: StreamOutcome) => void;
};

export function useChatStream(opts: UseChatStreamOptions) {
  const [streaming, setStreaming] = useState(false);
  const [liveText, setLiveText] = useState("");
  const [chips, setChips] = useState<ToolChip[]>([]);
  const [liveCards, setLiveCards] = useState<ChatMessage["cards"]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /** Общий прогон SSE-стрима (сообщение и resume): события → колбэки. */
  const runStream = async (
    start: (onEvent: (ev: SseEvent) => void, signal: AbortSignal) => Promise<void>,
  ): Promise<boolean> => {
    setStreaming(true);
    setLiveText("");
    setChips([]);
    setLiveCards([]);
    setStreamError(null);
    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = "";
    let cards: ChatMessage["cards"] = [];
    let gotDone = false;
    let gotError = false;
    let busyConflict = false;
    let streamFail: unknown = null;
    await start((ev: SseEvent) => {
      switch (ev.event) {
        case "delta":
          assistantText += ev.data.text;
          setLiveText(assistantText);
          break;
        case "tool_start":
          setChips((c) => {
            // серия однотипных вызовов (листание глав/транскрипта) — один чип со счётчиком
            const last = c[c.length - 1];
            if (last && last.name === ev.data.name) {
              return [
                ...c.slice(0, -1),
                {
                  ...last,
                  call_id: ev.data.call_id,
                  label: ev.data.label || last.label,
                  ok: undefined,
                  summary: undefined,
                  count: (last.count ?? 1) + 1,
                },
              ];
            }
            return [...c, { call_id: ev.data.call_id, name: ev.data.name, label: ev.data.label, count: 1 }];
          });
          setLiveText((t) => (t && !t.endsWith("\n") ? t + "\n\n" : t));
          break;
        case "tool_end":
          setChips((c) =>
            c.map((chip) => (chip.call_id === ev.data.call_id ? { ...chip, ok: ev.data.ok, summary: ev.data.summary } : chip)),
          );
          break;
        case "card":
          // B-003: index — позиция карточки в сообщении; слитые решения
          // приходят заменой первой карточки, а не новой строкой
          cards[ev.data.index ?? cards.length] = ev.data.card;
          setLiveCards([...cards]);
          break;
        case "session":
          opts.onSession(ev.data);
          break;
        case "title":
          opts.onTitle(ev.data.title);
          break;
        case "handoff":
          opts.onActiveAgent(ev.data.agent);
          break;
        case "review_progress":
          opts.onReviewProgress(ev.data);
          break;
        case "error":
          gotError = true;
          if (ev.data.error === "conflict") {
            // агент уже работает над прошлым сообщением: не ошибка, а подсказка
            busyConflict = true;
            opts.onBusy(ev.data.message);
            toast.info(ev.data.message);
          } else {
            setStreamError(ev.data.message);
            opts.onStreamError(ev.data.message);
            toast.error(ev.data.message);
          }
          break;
        case "done":
          gotDone = true;
          if (assistantText || cards.length) {
            opts.onAssistantMessage({
              id: ev.data.message_id ?? -Date.now(),
              role: "assistant",
              content: assistantText,
              cards,
              created_at: new Date().toISOString(),
            });
          }
          assistantText = "";
          cards = [];
          setLiveText("");
          setLiveCards([]);
          setChips([]);
          break;
      }
    }, controller.signal).catch((e) => {
      streamFail = e;
    });

    const userStopped = streamFail instanceof DOMException && streamFail.name === "AbortError";
    if (busyConflict) {
      opts.onFinish("busy"); // сообщение не сохранилось на сервере — бабл откатит страница
    } else if (!gotDone && !gotError && !userStopped) {
      // стрим оборвался без финала (деплой перезапустил веб, сеть моргнула): ядро
      // продолжает писать ответ в БД — опрос agent_state подхватит его, лимита нет
      opts.onFinish("reconnecting");
    } else {
      opts.onFinish("settled"); // штатно: страница перечитает разговор (id, карточки)
    }
    setStreaming(false);
    abortRef.current = null;
    return busyConflict;
  };

  /** Отправить сообщение; true — разговор был занят (409), сообщение не ушло. */
  const send = async (content: string, sendOpts?: { research?: boolean; intent?: string; attachments?: string[] }) => {
    if (!content.trim() || streaming) return false;
    const busy = await runStream((onEvent, signal) =>
      streamChat(opts.conversationUid, content, onEvent, signal, sendOpts),
    );
    return busy;
  };

  /** «Продолжить» после прерывания: генерация заново по последнему user-сообщению. */
  const resume = () => {
    if (streaming) return;
    void runStream((onEvent, signal) => streamResume(opts.conversationUid, onEvent, signal));
  };

  const stop = async () => {
    abortRef.current?.abort();
    try {
      await fetch(`/api/conversations/${opts.conversationUid}/stop`, { method: "POST" });
    } catch {
      // игнорируем
    }
  };

  return { send, resume, stop, streaming, liveText, chips, liveCards, streamError, setStreamError };
}
