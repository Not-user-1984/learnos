"use client";

/** Лента чата: сообщения, SSE-стриминг, чипы инструментов, карточки, композер. */

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { AgentState, ChatMessage, ConversationDetail, ReviewProgress, SseEvent } from "@/lib/types";
import { useSearchParams } from "next/navigation";
import { streamChat, streamResume } from "@/lib/chat/stream";
import { apiPost, apiUpload } from "@/lib/api";
import { CatToggle, ChatCat, useCatVisible } from "@/components/chat/chat-cat";
import { Markdown } from "@/components/markdown/Markdown";
import { CardView } from "@/components/chat/cards";
import { EmptyHint, Message, ToolChipView, type ToolChip } from "@/components/chat/message";
import { AgentStateBanner, ReviewProgressBar, SessionAside, SessionPanelDialog, StreamErrorBar } from "@/components/chat/status-bars";
import { NextSteps } from "@/components/chat/next-steps";
import { TuningEmptyState } from "@/components/chat/tuning-panel";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { agentLabel, modeLabel } from "@/lib/format";
import type { ChatScenario } from "@/lib/scenarios";



/** Вложение композера: PDF уже загружен в Библиотеку, уйдёт с следующим сообщением. */
type PendingAttachment = { uid: string; title: string };

/** Во время стриминга незакрытый ```-блок (недописанная mermaid-схема или код)
 *  не отдаём в рендер — обрубки ломают парсеры и мигают. */
function trimOpenFence(text: string): string {
  const fences = [...text.matchAll(/^```/gm)];
  if (fences.length % 2 === 0) return text;
  return text.slice(0, fences[fences.length - 1].index ?? 0);
}

export type ChatViewProps = {
  conversation: ConversationDetail;
  /** panel — встроенная панель рядом с читалкой (без шапки/сайдбара/кота, B-006). */
  variant?: "page" | "panel";
  /** Вставить текст в композер (цитата/момент видео из читалки, B-006). */
  insert?: { text: string; nonce: number };
  /** Клик по таймкоду [мм:сс] в ответах — seek видео-плеера (B-006). */
  onTimecode?: (seconds: number) => void;
};

export function ChatView({ conversation, variant = "page", insert, onTimecode }: ChatViewProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(conversation.messages);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [chips, setChips] = useState<ToolChip[]>([]);
  const [liveCards, setLiveCards] = useState<ChatMessage["cards"]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [busyHint, setBusyHint] = useState<string | null>(null);
  const [session, setSession] = useState(conversation.session);
  const [reviewProgress, setReviewProgress] = useState<ReviewProgress | null>(conversation.review_progress ?? null);
  const [input, setInput] = useState("");
  const [title, setTitle] = useState(conversation.title);
  // T-050: кого показывает бейдж «ведёт: …» (обновляется событием handoff)
  const [activeAgent, setActiveAgent] = useState<string | null | undefined>(
    conversation.active_agent
  );
  const [reconnecting, setReconnecting] = useState(false);
  const [agentState, setAgentState] = useState<AgentState | null>(conversation.agent_state ?? null);
  const [attachment, setAttachment] = useState<PendingAttachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastSentRef = useRef("");
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialSentRef = useRef(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [messages, streamText, liveCards]);

  // цитата из читалки / момент видео — в композер панели (B-006); вставка как
  // производный state во время рендера (паттерн «adjusting state when props change»)
  const [lastInsertNonce, setLastInsertNonce] = useState(0);
  if (insert?.text && insert.nonce !== lastInsertNonce) {
    setLastInsertNonce(insert.nonce);
    setInput(insert.text);
  }

  const refresh = async (): Promise<ConversationDetail | null> => {
    try {
      return await fetch(`/api/conversations/${conversation.uid}`).then((r) => r.json() as Promise<ConversationDetail>);
    } catch {
      return null; // сеть/прокси недоступны (например, веб перекатывается деплоем)
    }
  };
  const applyFresh = (fresh: ConversationDetail) => {
    setMessages(fresh.messages ?? []);
    if (fresh.title) setTitle(fresh.title);
    if (fresh.session) setSession(fresh.session);
    setReviewProgress(fresh.review_progress ?? null);
  };

  /** Общий прогон SSE-стрима (сообщение и resume): события → состояние ленты.
   *  Возвращает true, если разговор был занят (409/conflict) — сообщение не ушло. */
  const runStream = async (start: (onEvent: (ev: SseEvent) => void, signal: AbortSignal) => Promise<void>): Promise<boolean> => {
    setStreaming(true);
    setStreamText("");
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
          setStreamText(assistantText);
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
          setStreamText((t) => (t && !t.endsWith("\n") ? t + "\n\n" : t));
          break;
        case "tool_end":
          setChips((c) => c.map((chip) => (chip.call_id === ev.data.call_id ? { ...chip, ok: ev.data.ok, summary: ev.data.summary } : chip)));
          break;
        case "card":
          // B-003: index — позиция карточки в сообщении; слитые решения
          // приходят заменой первой карточки, а не новой строкой
          cards[ev.data.index ?? cards.length] = ev.data.card;
          setLiveCards([...cards]);
          break;
        case "session":
          // панель сессии живёт по данным события: в root-разговоре сессия может
          // появиться первым же событием (интент «session»), без GET разговора
          setSession((s) =>
            s
              ? { ...s, state: ev.data.state, allowed_events: ev.data.allowed_events }
              : {
                  session_uid: ev.data.session_uid ?? "",
                  state: ev.data.state,
                  status: "active",
                  allowed_events: ev.data.allowed_events,
                  chapter_idx: ev.data.chapter_idx ?? null,
                  config: {},
                },
          );
          break;
        case "title":
          setTitle(ev.data.title);
          break;
        case "handoff":
          // T-050: разговор передан специалисту — бейдж «ведёт: …» обновится с conversation
          setActiveAgent(ev.data.agent);
          break;
        case "review_progress":
          // mark_chapter_done/finish_session двигают курсор книги — полоса обновляется
          setReviewProgress(ev.data);
          break;
        case "error":
          gotError = true;
          if (ev.data.error === "conflict") {
            // агент уже работает над прошлым сообщением: не ошибка, а подсказка
            busyConflict = true;
            setBusyHint(ev.data.message);
            toast.info(ev.data.message);
          } else {
            setStreamError(ev.data.message);
            toast.error(ev.data.message);
          }
          break;
        case "done":
          gotDone = true;
          if (assistantText || cards.length) {
            setMessages((m) => [...m, { id: ev.data.message_id ?? -Date.now(), role: "assistant", content: assistantText, cards, created_at: new Date().toISOString() }]);
          }
          assistantText = "";
          cards = [];
          setStreamText("");
          setLiveCards([]);
          setChips([]);
          break;
      }
    }, controller.signal).catch((e) => {
      streamFail = e;
    });

    const userStopped = streamFail instanceof DOMException && streamFail.name === "AbortError";
    if (busyConflict) {
      // сообщение не сохранилось на сервере — optimistичный бабл откатываем
    } else if (!gotDone && !gotError && !userStopped) {
      // стрим оборвался без финала (деплой перезапустил веб, сеть моргнула): ядро
      // продолжает писать ответ в БД — поллинг agent_state подхватит его, лимита
      // времени нет (длинные автономные цепочки длятся 10+ минут)
      setReconnecting(true);
    } else {
      // штатное завершение: перечитываем разговор, чтобы подтянуть id и карточки
      const fresh = await refresh();
      if (fresh?.messages?.length) applyFresh(fresh);
    }
    setStreaming(false);
    abortRef.current = null;
    return busyConflict;
  };

  const send = async (content: string, opts?: { research?: boolean; intent?: string }) => {
    if (!content.trim() || streaming) return;
    lastSentRef.current = content;
    setInput("");
    setBusyHint(null);
    const attached = attachment;
    setAttachment(null);
    const optimisticId = -Date.now();
    setMessages((m) => [
      ...m,
      {
        id: optimisticId,
        role: "user",
        content,
        cards: attached ? [{ type: "attachment", title: attached.title, source_uid: attached.uid }] : [],
        created_at: new Date().toISOString(),
      },
    ]);
    setAgentState(null);
    const busy = await runStream((onEvent, signal) =>
      streamChat(conversation.uid, content, onEvent, signal, {
        research: opts?.research,
        intent: opts?.intent,
        attachments: attached ? [attached.uid] : undefined,
      }),
    );
    if (busy) {
      // 409: сервер не сохранил сообщение — убираем бабл, покажем подсказку
      setMessages((m) => m.filter((msg) => msg.id !== optimisticId));
      setAgentState((s) => s ?? { working: true, runs: [], interrupted: false });
    }
  };

  // «Продолжить» после прерывания: генерация заново по последнему user-сообщению
  const resumeGeneration = () => {
    if (streaming) return;
    setAgentState(null);
    setReconnecting(false);
    void runStream((onEvent, signal) => streamResume(conversation.uid, onEvent, signal));
  };

  // Правда о генерации: пока последнее сообщение без ответа (свой стрим оборвался
  // или генерация идёт независимо от вкладки) — опрашиваем detail каждые 5 с без
  // лимита времени: ответ появился — подхватываем; работает — бейдж; прерван — баннер
  const lastMessage = messages[messages.length - 1];
  useEffect(() => {
    if (streaming || !lastMessage || lastMessage.role !== "user") return;
    let cancelled = false;
    const tick = async () => {
      const fresh = await refresh();
      if (cancelled || !fresh) return;
      const list = fresh.messages ?? [];
      if (list.length && list[list.length - 1]?.role === "assistant") {
        applyFresh(fresh);
        setAgentState(null);
        setReconnecting(false);
        return;
      }
      setAgentState(fresh.agent_state ?? null);
      if (fresh.agent_state?.interrupted && !fresh.agent_state.working) setReconnecting(false);
    };
    void tick();
    const id = setInterval(() => void tick(), 5000);
    // R-25: чат не опрашивает вечно, когда отвечать некому (LLМ не настроен и
    // агент не работает) — последняя реплика user, генерации нет
    const staleTicks = { n: 0 };
    const guard = setInterval(() => {
      const last = messages[messages.length - 1];
      if (!streaming && last?.role === "user" && !agentState?.working && !agentState?.interrupted) {
        staleTicks.n += 1;
        if (staleTicks.n > 3) {
          clearInterval(id);
          clearInterval(guard);
        }
      } else {
        staleTicks.n = 0;
      }
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
      clearInterval(guard);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessage?.id, streaming]);

  // ?initial=… — отправляем автоматически один раз (цитата из читалки, тема ресэрча,
  // сценарные входы); ?intent=… — код сценария, ?research=1 — ресэрч-цикл:
  // директивы уйдут агенту через system_extra, в чате виден только текст
  useEffect(() => {
    const initial = searchParams.get("initial");
    const research = searchParams.get("research") === "1";
    const intent = searchParams.get("intent") ?? undefined;
    if (initial && !initialSentRef.current && conversation.messages.length === 0) {
      initialSentRef.current = true;
      void send(initial, { research, intent });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const stop = async () => {
    abortRef.current?.abort();
    try {
      await fetch(`/api/conversations/${conversation.uid}/stop`, { method: "POST" });
    } catch {
      // игнорируем
    }
  };

  // Вложение PDF: грузится в Библиотеку сразу (существующий /sources/upload),
  // уйдёт со следующим сообщением — агент получит готовый source_uid.
  const pickPdf = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    try {
      const src = await apiUpload<{ uid: string; title: string }>("/sources/upload", file);
      setAttachment({ uid: src.uid, title: src.title || file.name });
      toast.success("PDF загружен — уйдёт со следующим сообщением");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось загрузить PDF");
    } finally {
      setUploading(false);
    }
  };

  // Сценарий из NextSteps с поведением стартового экрана (B-003): одна надпись —
  // одно действие. «Закрепить пройденное» всегда начинает новый reinforce-разговор.
  const startScenario = async (scenario: ChatScenario) => {
    if (scenario.action.kind !== "new-conversation") return;
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {});
      const params = new URLSearchParams({ initial: scenario.action.initial });
      if (scenario.action.intent) params.set("intent", scenario.action.intent);
      router.push(`/chat/${conv.uid}?${params.toString()}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать разговор");
    }
  };

  // кот занимает нижнюю полку ленты: когда он видим, лента оставляет ему отступ
  const catVisible = useCatVisible();
  // note_draft → ближайший записанный после него блок (для «Записано → Открыть блок»)
  const noteOutcomes = noteDraftOutcomes(messages);

  return (
    <div className="flex h-full min-w-0">
      <div className="flex min-w-0 flex-1 flex-col">
        {variant === "panel" ? (
          /* панель у читалки: компактная шапка без удаления (B-006) */
          <header className="flex items-center gap-2 border-b px-3 py-2">
            <h1 className="truncate text-sm font-semibold">{title}</h1>
            <span className="ml-auto shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {conversation.scenario || modeLabel(conversation.mode)}
            </span>
          </header>
        ) : (
          <header className="flex items-center gap-2 border-b px-4 py-3">
            <h1 className="truncate font-semibold">{title}</h1>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {conversation.scenario || modeLabel(conversation.mode)}
            </span>
            {activeAgent && activeAgent !== "root" && (
              <span className="rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-xs text-primary">
                ведёт: {agentLabel(activeAgent)}
              </span>
            )}
            {/* прогресс сессии на мобиле — кнопкой в шапке (B-003: fixed-кнопка перекрывала композер) */}
            {session && session.state !== "done" && <SessionPanelDialog session={session} />}
            <ConfirmDeleteButton
              endpoint={`/conversations/${conversation.uid}`}
              title="Удалить разговор?"
              name={title}
              description="Сообщения разговора удалятся безвозвратно. Блоки базы знаний, созданные по нему, останутся."
              successMessage="Разговор удалён"
              redirectTo="/chat"
              className="ml-auto"
              buttonClassName="rounded-lg p-1.5 text-muted-foreground transition hover:text-rose-500"
            />
          </header>
        )}

        {/* статус-бар быстрого разбора: курсор книги по главам (активность разговора);
            видео и материалы без глав (total ≤ 1) полосу не показывают */}
        {reviewProgress && reviewProgress.total_chapters > 1 && <ReviewProgressBar progress={reviewProgress} />}

        {!streaming && (
          <AgentStateBanner
            agentState={agentState}
            reconnecting={reconnecting}
            busyHint={busyHint}
            onStop={() => void stop()}
            onResume={resumeGeneration}
          />
        )}

        {/* лента + кот-питомец на полке у нижней границы: оверлей не мешает кликам,
            а видимой полке оставляем нижний отступ, чтобы кот не накрывал карточки */}
        <div className="relative min-h-0 flex-1">
          <div ref={feedRef} className={cn("h-full overflow-y-auto px-4 py-6", catVisible && "pb-14")}>
            <div className="mx-auto flex max-w-3xl flex-col gap-7 py-2">
              {messages.length === 0 && (conversation.mode === "root" || conversation.mode === "free") && <EmptyHint />}
              {messages.length === 0 && conversation.mode === "tuning" && <TuningEmptyState />}
              {messages.map((m) => (
                <Message
                  key={m.id}
                  message={m}
                  onInsert={streaming ? undefined : setInput}
                  onSend={streaming ? undefined : send}
                  conversationUid={conversation.uid}
                  noteSavedBlockUid={noteOutcomes.get(m.id)}
                  onTimecode={onTimecode}
                />
              ))}
              {streaming && (
                <div>
                  {chips.map((chip) => (
                    <ToolChipView key={chip.call_id} chip={chip} />
                  ))}
                  {liveCards.map((c, i) => (
                    <div key={c.card_id ?? i} className="mb-3">
                      <CardView
                        card={c}
                        onInsert={streaming ? undefined : setInput}
                        onSend={streaming ? undefined : send}
                        conversationUid={conversation.uid}
                      />
                    </div>
                  ))}
                  {streamText ? (
                    <div className="rounded-2xl bg-muted px-4 py-3">
                      <Markdown content={trimOpenFence(streamText)} onTimecode={onTimecode} />
                    </div>
                  ) : (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Icon name="progress_activity" size={16} className="animate-spin" /> агент думает…
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
          {variant === "page" && <ChatCat />}
        </div>

        <StreamErrorBar message={streamError ?? ""} onRetry={() => { setStreamError(null); void send(input || lastSentRef.current); }} />

        {/* B-003: один контекстный ряд «что дальше» вместо двух рядов чипов;
            скрыт при стриме и пока есть неотвеченные решения */}
        <NextSteps
          streaming={streaming}
          messages={messages}
          session={session}
          mode={conversation.mode}
          onSend={(t) => void send(t)}
          onPrefill={setInput}
          onStartScenario={(s) => void startScenario(s)}
        />
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
                    onClick={() => setAttachment(null)}
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
                  void pickPdf(e.target.files?.[0]);
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
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(input);
                  }
                }}
                placeholder="Сообщение… (Enter — отправить, Shift+Enter — перенос)"
                className="max-h-40 min-h-10 resize-none"
                rows={1}
              />
              {streaming ? (
                <Button variant="destructive" size="icon" aria-label="Стоп" onClick={stop}>
                  <Icon name="stop_circle" size={16} />
                </Button>
              ) : (
                <Button size="icon" aria-label="Отправить" disabled={!input.trim()} onClick={() => void send(input)}>
                  <Icon name="send" size={16} />
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {session && variant === "page" && <SessionAside session={session} />}
    </div>
  );
}

/** Статус-бар быстрого разбора книги: сколько глав пройдено / всего, какая текущая.
 *  Прогресс разбора — отдельно от сессии-урока: это курсор книги из активности
 *  разговора, данные из БД — полоса переживает уход из разговора и возврат. */

/** note_draft → uid ближайшего block_saved ПОЗЖЕ этого сообщения: превью,
 *  по которому блок уже записан, показывает ссылку вместо кнопок (B-003). */
function noteDraftOutcomes(messages: ChatMessage[]): Map<number, string | undefined> {
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

export function ChatViewWithInitial(props: { conversation: ConversationDetail }) {
  return (
    <Suspense fallback={null}>
      <ChatView {...props} />
    </Suspense>
  );
}
