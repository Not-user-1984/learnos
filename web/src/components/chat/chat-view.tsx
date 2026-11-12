"use client";

/** Лента чата: сообщения, SSE-стриминг (хук useChatStream), карточки, композер. */

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { AgentState, ChatMessage, ConversationDetail, ReviewProgress } from "@/lib/types";
import { useSearchParams } from "next/navigation";
import { apiPost, apiUpload } from "@/lib/api";
import { ChatCat, useCatVisible } from "@/components/chat/chat-cat";
import { Markdown } from "@/components/markdown/Markdown";
import { CardView } from "@/components/chat/cards";
import { EmptyHint, Message, ToolChipView, noteDraftOutcomes } from "@/components/chat/message";
import { AgentStateBanner, ReviewProgressBar, SessionAside, SessionPanelDialog, StreamErrorBar } from "@/components/chat/status-bars";
import { NextSteps } from "@/components/chat/next-steps";
import { TuningEmptyState } from "@/components/chat/tuning-panel";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { cn } from "@/lib/utils";
import { agentLabel, modeLabel } from "@/lib/format";
import type { ChatScenario } from "@/lib/scenarios";
import { useChatStream, type SessionEvent } from "@/components/chat/use-chat-stream";
import { ChatComposer, type PendingAttachment } from "@/components/chat/composer";

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
  const lastSentRef = useRef("");
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialSentRef = useRef(false);
  const feedRef = useRef<HTMLDivElement>(null);

  // событие session: панель урока может появиться первым же событием (интент
  // «session» в root-разговоре), без GET разговора
  const applySession = (data: SessionEvent) => {
    setSession((s) =>
      s
        ? { ...s, state: data.state, allowed_events: data.allowed_events }
        : {
            session_uid: data.session_uid ?? "",
            state: data.state,
            status: "active",
            allowed_events: data.allowed_events,
            chapter_idx: data.chapter_idx ?? null,
            config: {},
          },
    );
  };

  const stream = useChatStream({
    conversationUid: conversation.uid,
    onSession: applySession,
    onTitle: setTitle,
    onActiveAgent: setActiveAgent,
    onReviewProgress: setReviewProgress,
    onAssistantMessage: (msg) => setMessages((m) => [...m, msg]),
    onBusy: setBusyHint,
    onStreamError: () => undefined, // текст ошибки хранит хук (StreamErrorBar)
    onFinish: async (outcome) => {
      if (outcome === "reconnecting") setReconnecting(true);
      else if (outcome === "settled") {
        // штатное завершение: перечитываем разговор, чтобы подтянуть id и карточки
        const fresh = await refresh();
        if (fresh?.messages?.length) applyFresh(fresh);
      }
    },
  });
  const { send: sendStream, streaming } = stream;

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [messages, stream.liveText, stream.liveCards]);

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
    const busy = await sendStream(content, {
      research: opts?.research,
      intent: opts?.intent,
      attachments: attached ? [attached.uid] : undefined,
    });
    if (busy) {
      // 409: сервер не сохранил сообщение — убираем бабл, покажем подсказку
      setMessages((m) => m.filter((msg) => msg.id !== optimisticId));
      setAgentState((s) => s ?? { working: true, runs: [], interrupted: false });
    }
  };

  // «Продолжить» после прерывания: генерация заново по последнему user-сообщению
  const resumeGeneration = () => {
    setAgentState(null);
    setReconnecting(false);
    stream.resume();
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
    void stream.stop();
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
        {/* шапка: page — с бейджами и удалением, panel у читалки — компактная (B-006) */}
        <header className={cn("flex items-center gap-2 border-b", variant === "panel" ? "px-3 py-2" : "px-4 py-3")}>
          <h1 className={cn("truncate", variant === "panel" ? "text-sm font-semibold" : "font-semibold")}>{title}</h1>
          <span
            className={cn(
              "rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground",
              variant === "panel" && "ml-auto shrink-0",
            )}
          >
            {conversation.scenario || modeLabel(conversation.mode)}
          </span>
          {variant === "page" && activeAgent && activeAgent !== "root" && (
            <span className="rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-xs text-primary">
              ведёт: {agentLabel(activeAgent)}
            </span>
          )}
          {/* прогресс сессии на мобиле — кнопкой в шапке (B-003: fixed-кнопка перекрывала композер) */}
          {variant === "page" && session && session.state !== "done" && <SessionPanelDialog session={session} />}
          {variant === "page" && (
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
          )}
        </header>
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
                  {stream.chips.map((chip) => (
                    <ToolChipView key={chip.call_id} chip={chip} />
                  ))}
                  {stream.liveCards.map((c, i) => (
                    <div key={c.card_id ?? i} className="mb-3">
                      <CardView
                        card={c}
                        onInsert={streaming ? undefined : setInput}
                        onSend={streaming ? undefined : send}
                        conversationUid={conversation.uid}
                      />
                    </div>
                  ))}
                  {stream.liveText ? (
                    <div className="rounded-2xl bg-muted px-4 py-3">
                      <Markdown content={trimOpenFence(stream.liveText)} onTimecode={onTimecode} />
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

        <StreamErrorBar message={stream.streamError ?? ""} onRetry={() => { stream.setStreamError(null); void send(input || lastSentRef.current); }} />

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
        <ChatComposer
          value={input}
          onChange={setInput}
          onSend={(t) => void send(t)}
          onStop={() => void stop()}
          streaming={streaming}
          variant={variant}
          attachment={attachment}
          onClearAttachment={() => setAttachment(null)}
          onPickPdf={(f) => void pickPdf(f)}
          uploading={uploading}
        />
      </div>

      {session && variant === "page" && <SessionAside session={session} />}
    </div>
  );
}

export function ChatViewWithInitial(props: { conversation: ConversationDetail }) {
  return (
    <Suspense fallback={null}>
      <ChatView {...props} />
    </Suspense>
  );
}
