"use client";

/** Лента чата: сообщения, SSE-стриминг, чипы инструментов, карточки, композер. */

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { ChatMessage, ConversationDetail, SseEvent } from "@/lib/types";
import { useSearchParams } from "next/navigation";
import { streamChat } from "@/lib/chat/stream";
import { apiPost, apiUpload } from "@/lib/api";
import { Markdown } from "@/components/markdown/Markdown";
import { CardView } from "@/components/chat/cards";
import { TuningEmptyState } from "@/components/chat/tuning-panel";
import { ConfirmDeleteButton } from "@/components/confirm-delete";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { modeLabel } from "@/lib/format";

type ToolChip = {
  call_id: string;
  name: string;
  label: string;
  ok?: boolean;
  summary?: string;
  open?: boolean;
  count?: number;
};

const SESSION_STEPS = ["theory", "check", "practice", "debrief", "done"];
const STEP_LABELS: Record<string, string> = { theory: "Теория", check: "Вопросы", practice: "Практика", debrief: "Разбор", done: "Готово" };

/** Вложение композера: PDF уже загружен в Библиотеку, уйдёт с следующим сообщением. */
type PendingAttachment = { uid: string; title: string };

/** Во время стриминга незакрытый ```-блок (недописанная mermaid-схема или код)
 *  не отдаём в рендер — обрубки ломают парсеры и мигают. */
function trimOpenFence(text: string): string {
  const fences = [...text.matchAll(/^```/gm)];
  if (fences.length % 2 === 0) return text;
  return text.slice(0, fences[fences.length - 1].index ?? 0);
}

export function ChatView({ conversation }: { conversation: ConversationDetail }) {
  const [messages, setMessages] = useState<ChatMessage[]>(conversation.messages);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [chips, setChips] = useState<ToolChip[]>([]);
  const [liveCards, setLiveCards] = useState<ChatMessage["cards"]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [session, setSession] = useState(conversation.session);
  const [input, setInput] = useState("");
  const [title, setTitle] = useState(conversation.title);
  const [reconnecting, setReconnecting] = useState(false);
  const [courseBusy, setCourseBusy] = useState(false);
  const [attachment, setAttachment] = useState<PendingAttachment | null>(null);
  const [uploading, setUploading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastSentRef = useRef("");
  const aliveRef = useRef(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialSentRef = useRef(false);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight });
  }, [messages, streamText, liveCards]);

  const send = async (content: string, opts?: { research?: boolean }) => {
    if (!content.trim() || streaming) return;
    lastSentRef.current = content;
    setInput("");
    const attached = attachment;
    setAttachment(null);
    setMessages((m) => [
      ...m,
      {
        id: -Date.now(),
        role: "user",
        content,
        cards: attached ? [{ type: "attachment", title: attached.title, source_uid: attached.uid }] : [],
        created_at: new Date().toISOString(),
      },
    ]);
    setStreaming(true);
    setStreamText("");
    setChips([]);
    setLiveCards([]);
    setStreamError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const baseCount = messages.length;

    let assistantText = "";
    let cards: ChatMessage["cards"] = [];
    let gotDone = false;
    let gotError = false;
    let streamFail: unknown = null;
    await streamChat(conversation.uid, content, (ev: SseEvent) => {
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
          cards = [...cards, ev.data.card];
          setLiveCards([...cards]);
          break;
        case "session":
          setSession((s) => (s ? { ...s, state: ev.data.state, allowed_events: ev.data.allowed_events } : s));
          break;
        case "title":
          setTitle(ev.data.title);
          break;
        case "error":
          gotError = true;
          setStreamError(ev.data.message);
          toast.error(ev.data.message);
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
    }, controller.signal, { research: opts?.research, attachments: attached ? [attached.uid] : undefined }).catch((e) => {
      streamFail = e;
    });

    const userStopped = streamFail instanceof DOMException && streamFail.name === "AbortError";
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
    };

    if (!gotDone && !gotError && !userStopped) {
      // стрим оборвался без финала (деплой перезапустил веб, сеть моргнула):
      // ядро продолжает писать ответ в БД — догоняем его опросом
      setReconnecting(true);
      const deadline = Date.now() + 180_000;
      let caught = false;
      while (Date.now() < deadline && aliveRef.current && !abortRef.current?.signal.aborted) {
        const fresh = await refresh();
        const list = fresh?.messages;
        const last = list?.[list.length - 1];
        if (list && list.length > baseCount + 1 && last?.role === "assistant") {
          applyFresh(fresh);
          caught = true;
          break;
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
      setReconnecting(false);
      if (!caught && aliveRef.current) {
        setStreamError("Связь прервалась и ответ не был дописан");
      }
    } else {
      // штатное завершение: перечитываем разговор, чтобы подтянуть id и карточки
      const fresh = await refresh();
      if (fresh?.messages?.length) applyFresh(fresh);
    }
    setStreaming(false);
    setReconnecting(false);
    abortRef.current = null;
  };

  // ?initial=… — отправляем автоматически один раз (цитата из читалки, тема ресёрча);
  // ?research=1 — тема запускает ресёрч-цикл: директива уйдёт агенту, в чате видна только тема
  useEffect(() => {
    const initial = searchParams.get("initial");
    const research = searchParams.get("research") === "1";
    if (initial && !initialSentRef.current && conversation.messages.length === 0) {
      initialSentRef.current = true;
      void send(initial, { research });
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

  // «Собрать курс»: план из источников разговора/библиотеки → курс с сессиями и прогрессом
  const buildCourse = async () => {
    if (courseBusy) return;
    setCourseBusy(true);
    const topic = title.replace(/^Ресёрч:\s*/i, "").trim() || "Курс по материалам разговора";
    try {
      const plan = await apiPost<Record<string, unknown>>("/courses/plan", {
        topic,
        constraints: "источники уже в библиотеке (добавлены ресёрчем) — строй курс по ним, сессиями по главам/видео",
      });
      const items = (plan.items as unknown[] | undefined) ?? [];
      if (!items.length) {
        toast.info("Планировщик не нашёл материала — добавь источники и попробуй снова");
        return;
      }
      const course = await apiPost<{ uid: string }>("/courses/from-plan", { plan });
      toast.success("Курс собран");
      router.push(`/courses/${course.uid}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось собрать курс");
    } finally {
      setCourseBusy(false);
    }
  };

  return (
    <div className="flex h-full min-w-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b px-4 py-3">
          <h1 className="truncate font-semibold">{title}</h1>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {modeLabel(conversation.mode)}
          </span>
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

        <div ref={feedRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-7 py-2">
            {messages.length === 0 && conversation.mode === "free" && <EmptyHint mode={conversation.mode} />}
            {messages.length === 0 && conversation.mode === "tuning" && <TuningEmptyState />}
            {messages.map((m) => (
              <Message key={m.id} message={m} onInsert={streaming ? undefined : setInput} onSend={streaming ? undefined : send} />
            ))}
            {streaming && (
              <div>
                {chips.map((chip) => (
                  <ToolChipView key={chip.call_id} chip={chip} />
                ))}
                {liveCards.map((c, i) => (
                  <div key={i} className="mb-3">
                    <CardView card={c} onInsert={streaming ? undefined : setInput} onSend={streaming ? undefined : send} />
                  </div>
                ))}
                {streamText ? (
                  <div className="rounded-2xl bg-muted px-4 py-3">
                    <Markdown content={trimOpenFence(streamText)} />
                  </div>
                ) : (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Icon name="progress_activity" size={16} className="animate-spin" /> агент думает…
                  </p>
                )}
                {reconnecting && (
                  <p className="mt-2 flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
                    <Icon name="progress_activity" size={16} className="animate-spin" /> связь прервалась — догоняю ответ агента…
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {streamError && (
          <div className="mx-auto mb-2 max-w-3xl px-4">
            <div className="flex items-center gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2.5 text-sm">
              <span className="text-rose-500">⚠</span>
              <span className="flex-1">Ошибка агента: {streamError}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setStreamError(null);
                  void send(input || lastSentRef.current);
                }}
              >
                Повторить
              </Button>
            </div>
          </div>
        )}
        {conversation.mode === "session" && !streaming && session && session.state !== "done" && (
          <div className="mx-auto mb-1 flex max-w-3xl flex-wrap gap-2 px-4">
            <button
              onClick={() => void send("Фейнман: запусти проверку — задай следующий вопрос по пройденному (карточкой ask).")}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1.5 text-sm text-primary transition hover:bg-primary/20"
            >
              <Icon name="help" size={16} /> Фейнман-вопросы
            </button>
          </div>
        )}
        {(conversation.mode === "quick" || conversation.mode === "free") && !streaming && (
          <div className="mx-auto mb-1 flex max-w-3xl flex-wrap gap-2 px-4">
            <button
              onClick={() => void send("Закрепим материал нашего разговора: задай вопросы по ключевым понятиям, по одному за раз.")}
              className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-sm text-sky-500 transition hover:bg-sky-500/20"
            >
              <Icon name="track_changes" size={16} /> Закрепить пройденное
            </button>
            <button
              onClick={() =>
                void send("Собери превью конспекта в базу знаний по пройденному: покажи, что запишем, без сохранения.")
              }
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-500 transition hover:bg-emerald-500/20"
            >
              <Icon name="edit_note" size={16} /> Конспект в базу знаний
            </button>
            <button
              onClick={() => void buildCourse()}
              disabled={courseBusy}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1.5 text-sm text-primary transition hover:bg-primary/20 disabled:opacity-60"
            >
              {courseBusy ? <Icon name="progress_activity" size={16} className="animate-spin" /> : <Icon name="school" size={16} />}
              Собрать курс
            </button>
          </div>
        )}
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

      {conversation.mode === "session" && session && (
        <>
          {/* планшет: панель сессии прячется в кнопку с прогрессом в шапке */}
          <SessionPanelDialog session={session} />
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
        </>
      )}
    </div>
  );
}

function SessionPanelDialog({ session }: { session: NonNullable<ConversationDetail["session"]> }) {
  const [open, setOpen] = useState(false);
  const done = SESSION_STEPS.indexOf(session.state) + 1;
  return (
    <div className="lg:hidden">
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-24 right-4 z-20 flex items-center gap-2 rounded-full border bg-card px-3 py-2 text-sm shadow-lg"
        aria-label="Прогресс сессии"
      >
        <span className="flex gap-1">
          {SESSION_STEPS.map((st, i) => (
            <span
              key={st}
              className={cn("h-1.5 w-1.5 rounded-full", i < done ? "bg-emerald-500" : "bg-muted-foreground/30")}
            />
          ))}
        </span>
        {STEP_LABELS[session.state]} · {done}/{SESSION_STEPS.length}
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

const CHAT_PROSE = "prose-headings:mt-5 prose-headings:mb-2 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:my-3";

function Message({
  message,
  onInsert,
  onSend,
}: {
  message: ChatMessage;
  onInsert?: (t: string) => void;
  onSend?: (t: string) => void;
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
  return (
    <div className="flex flex-col gap-2">
      <p className="flex items-center gap-1 px-1 text-xs text-muted-foreground"><Icon name="smart_toy" size={14} /> Агент · {time}</p>
      <div className="rounded-2xl border bg-muted/50 px-5 py-4">
        <Markdown content={message.content} className={CHAT_PROSE} />
      </div>
      {message.cards?.map((c, i) => (
        <CardView key={i} card={c} onInsert={onInsert} onSend={onSend} />
      ))}
    </div>
  );
}

function ToolChipView({ chip }: { chip: ToolChip }) {
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

export function ChatViewWithInitial(props: { conversation: ConversationDetail }) {
  return (
    <Suspense fallback={null}>
      <ChatView {...props} />
    </Suspense>
  );
}

function EmptyHint({ mode }: { mode: string }) {
  if (mode !== "free") return null;
  return (
    <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
      Спроси что угодно. Агент ищет по базе знаний, правит блоки по просьбе («добавь в блок про поды…») и сохраняет конспекты по слову «сохрани».
    </p>
  );
}
