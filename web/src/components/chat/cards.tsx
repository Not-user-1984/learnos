"use client";

/** Карточки UI в чате: команда, вопрос, оценка, блок, превью конспекта, предложение действия, кнопки-ответы, разбор главы. */

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import type { Card, NoteDraft } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Mermaid } from "@/components/markdown/Mermaid";

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-500",
  medium: "bg-amber-500/15 text-amber-500",
  high: "bg-rose-500/15 text-rose-500",
};

export function CardView({
  card,
  onInsert,
  onSend,
}: {
  card: Card;
  onInsert?: (text: string) => void;
  onSend?: (text: string) => void;
}) {
  switch (card.type) {
    case "command":
      return <CommandCardView card={card} onInsert={onInsert} />;
    case "question":
      return <QuestionCardView card={card} />;
    case "evaluation":
      return <EvaluationCardView card={card} />;
    case "block_saved":
    case "block_updated":
      return <BlockCardView card={card} />;
    case "prompt_change":
      return <PromptChangeCardView card={card} />;
    case "git_change":
      return <GitChangeCardView card={card} />;
    case "note_draft":
      return <NoteDraftCardView card={card} onInsert={onInsert} onSend={onSend} />;
    case "action_offer":
      return <ActionOfferCardView card={card} onSend={onSend} />;
    case "quick_replies":
      return <QuickRepliesCardView card={card} onSend={onSend} />;
    case "chapter_review":
      return <ChapterReviewCardView card={card} />;
    default:
      return null;
  }
}

/** Предложение действия (T-036): заголовок + описание, решение — обычным сообщением.
 *  После клика кнопки блокируются (BUG-001): повторное «Да» не плодит сообщения. */
function ActionOfferCardView({ card, onSend }: { card: Card; onSend?: (t: string) => void }) {
  const [sent, setSent] = useState(false);
  const answer = (text: string) => {
    if (sent) return;
    setSent(true);
    onSend?.(text);
  };
  return (
    <div className="rounded-xl border border-primary/40 bg-primary/5 p-4">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-primary">
        <Icon name="task_alt" size={14} /> Предложение
      </p>
      <p className="font-medium">{card.title}</p>
      {card.description && <p className="mt-1 text-sm text-muted-foreground">{card.description}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {onSend ? (
          sent ? (
            <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
              <Icon name="progress_activity" size={14} className="animate-spin" /> отправлено — агент работает…
            </span>
          ) : (
            <>
              <Button size="sm" onClick={() => answer(`Да — делай: «${card.title}»`)}>
                <Icon name="check" size={16} className="mr-1" /> Да
              </Button>
              <Button size="sm" variant="outline" onClick={() => answer(`Нет, не надо: «${card.title}»`)}>
                <Icon name="close" size={16} className="mr-1" /> Нет
              </Button>
            </>
          )
        ) : (
          <span className="text-xs text-muted-foreground">агент предлагает — кнопки появятся после ответа</span>
        )}
      </div>
    </div>
  );
}

/** Кнопки-ответы (T-045): короткие варианты на вопрос агента; клик = обычное сообщение.
 *  После клика блокируются (как action_offer, T-044): повторный клик не плодит сообщения. */
function QuickRepliesCardView({ card, onSend }: { card: Card; onSend?: (t: string) => void }) {
  const [sent, setSent] = useState(false);
  const answer = (text: string) => {
    if (sent) return;
    setSent(true);
    onSend?.(text);
  };
  const replies = card.replies ?? [];
  if (sent) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
        <Icon name="progress_activity" size={14} className="animate-spin" /> отправлено — агент работает…
      </span>
    );
  }
  if (!onSend) {
    return (
      <div className="flex flex-wrap gap-2">
        {replies.map((r) => (
          <span key={r} className="rounded-full border bg-muted px-3 py-1 text-sm text-muted-foreground">
            {r}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {replies.map((r) => (
        <Button key={r} size="sm" variant="outline" className="rounded-full" onClick={() => answer(r)}>
          {r}
        </Button>
      ))}
    </div>
  );
}

/** Разбор главы/видео (T-046 Э2): структурированный итог быстрого разбора — секции вместо текстовой простыни. */
function ChapterReviewCardView({ card }: { card: Card }) {
  const isVideo = card.media === "video";
  const section = "text-xs font-medium uppercase tracking-wide text-muted-foreground";
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-primary">
        <Icon name={isVideo ? "play_circle" : "menu_book"} size={14} /> {isVideo ? "Разбор видео" : "Разбор главы"}
      </p>
      <p className="font-medium">{card.title}</p>

      {(card.key_points?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className={section}>Главное</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(card.key_points ?? []).map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {(card.concepts?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className={section}>Ключевые понятия</p>
          <ul className="mt-1 space-y-1 text-sm">
            {(card.concepts ?? []).map((c, i) => (
              <li key={i}>
                <b>{c.term}</b> — {c.definition}
              </li>
            ))}
          </ul>
        </div>
      )}

      {(card.applicable?.length ?? 0) > 0 && (
        <div className="mt-3">
          <p className={section}>Что применимо</p>
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {(card.applicable ?? []).map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      {(card.questions?.length ?? 0) > 0 && (
        <div className="mt-3 rounded-md bg-muted px-3 py-2">
          <p className={section}>Вопросы на подумать</p>
          <ul className="mt-1 space-y-1 text-sm">
            {(card.questions ?? []).map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CommandCardView({ card, onInsert }: { card: Card; onInsert?: (t: string) => void }) {
  const [output, setOutput] = useState("");
  const risk = (card.risk ?? "low") as keyof typeof RISK_COLORS;
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge className="gap-1 bg-primary/15 text-primary hover:bg-primary/25">
          <Icon name="terminal" size={12} /> {card.machine_name ?? card.machine ?? ""}
        </Badge>
        <Badge className={RISK_COLORS[risk] ?? RISK_COLORS.low}>риск: {card.risk ?? "low"}</Badge>
        {card.step !== undefined && <span className="text-xs text-muted-foreground">шаг {card.step}</span>}
      </div>
      <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-3 font-mono text-sm text-emerald-400">{card.command}</pre>
      <div className="mt-2 flex items-start gap-2">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            navigator.clipboard.writeText(card.command ?? "").then(() => toast.success("Команда скопирована"));
          }}
        >
          <Icon name="content_copy" size={16} /> Копировать
        </Button>
        {onInsert && (
          <Button size="sm" variant="outline" onClick={() => onInsert("```\n(вставь сюда вывод команды)\n```")}>
            Вставить вывод
          </Button>
        )}
      </div>
      <ul className="mt-2 space-y-1 text-sm">
        {(card.explanation ?? []).map((p, i) => (
          <li key={i}>
            <code className="rounded bg-muted px-1">{p.part || "команда"}</code> — {p.text}
          </li>
        ))}
      </ul>
      {card.expected && <p className="mt-2 text-sm text-muted-foreground">Ожидаем: {card.expected}</p>}
      {onInsert && (
        <div className="mt-3 flex gap-2">
          <textarea
            className="min-h-16 flex-1 rounded-md border bg-background p-2 font-mono text-xs"
            placeholder="Вывод команды — отправится сообщением"
            value={output}
            onChange={(e) => setOutput(e.target.value)}
          />
          <Button size="sm" disabled={!output.trim()} onClick={() => onInsert(`\`\`\`\n${output}\n\`\`\``)}>
            Отправить вывод
          </Button>
        </div>
      )}
    </div>
  );
}

function QuestionCardView({ card }: { card: Card }) {
  return (
    <div className="rounded-xl border-2 border-primary/50 bg-primary/5 p-4 shadow-sm">
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-primary">
        Фейнман-вопрос {card.index ?? ""}
        {card.total ? ` / ${card.total}` : ""} {card.concept && `· ${card.concept}`}
      </p>
      <p className="font-medium">{card.question}</p>
      <p className="mt-2 text-xs text-muted-foreground">ответь своими словами прямо в чат</p>
    </div>
  );
}

function EvaluationCardView({ card }: { card: Card }) {
  const icon = card.verdict === "understood" ? "check_circle" : card.verdict === "partial" ? "contrast" : "cancel";
  const label = card.verdict === "understood" ? "понял" : card.verdict === "partial" ? "частично" : "мимо";
  return (
    <div className="rounded-xl border p-4">
      <p className="mb-1 flex items-center gap-1.5 font-medium">
        <Icon name={icon} size={18} filled /> {label}
      </p>
      <p className="text-sm text-muted-foreground">{card.comment}</p>
      {card.weak_spot && (
        <p className="mt-2 rounded-md bg-amber-500/10 px-2 py-1 text-sm text-amber-600 dark:text-amber-400">
          Дозакрепить: {card.weak_spot}
        </p>
      )}
    </div>
  );
}

function BlockCardView({ card }: { card: Card }) {
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


function NoteDraftCardView({
  card,
  onInsert,
  onSend,
}: {
  card: Card;
  onInsert?: (t: string) => void;
  onSend?: (t: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const d: NoteDraft | undefined = card.draft;
  if (!d) return null;

  const approve = () => {
    if (!onSend || busy) return;
    setBusy(true);
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

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {onSend ? (
          <Button size="sm" disabled={busy} onClick={approve}>
            {busy ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="check" size={16} className="mr-1" />}
            Записать в базу
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">агент записывает…</span>
        )}
        {onInsert && !busy && (
          <Button size="sm" variant="outline" onClick={() => onInsert(`Поправим конспект (превью #${card.preview_id}): `)}>
            <Icon name="edit" size={16} className="mr-1" /> Поправить
          </Button>
        )}
        <span className="text-xs text-muted-foreground">
          правки можно писать словами — «это уберём», «это дополним», соберу новое превью
        </span>
      </div>
    </div>
  );
}

/** Ветка агента (T-038): просмотр диффа и отклонение; применение — за человеком. */
function GitChangeCardView({ card }: { card: Card }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rejected, setRejected] = useState(false);

  const reject = async () => {
    if (!card.branch || busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/revision/branch/reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch: card.branch }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setRejected(true);
      toast.success(`Ветка ${card.branch} удалена`);
    } catch {
      toast.error("Не удалось удалить ветку");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-violet-500/40 bg-violet-500/5 p-4">
      <p className="mb-1 flex items-center gap-2 text-sm font-medium">
        <Icon name="fork_right" size={16} className="text-violet-500" /> Ветка агента:{" "}
        <code className="font-mono">{card.branch}</code>
        {card.commit && <span className="text-muted-foreground">· {card.commit}</span>}
      </p>
      {card.summary && <p className="mb-2 text-sm text-muted-foreground">{card.summary}</p>}
      {(card.files ?? []).length > 0 && (
        <ul className="mb-2 space-y-0.5 font-mono text-xs text-muted-foreground">
          {(card.files ?? []).map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
      {card.diffstat && <pre className="overflow-x-auto rounded-lg border bg-card p-2 text-xs">{card.diffstat}</pre>}
      {open && (card.diff ?? []).length > 0 && (
        <div className="mt-2 max-h-64 overflow-auto rounded-lg border bg-zinc-950 font-mono text-xs leading-5">
          {(card.diff ?? []).slice(0, 300).map((d, i) => (
            <div
              key={i}
              className={
                d.op === "+"
                  ? "bg-emerald-500/15 px-2 text-emerald-300"
                  : d.op === "-"
                    ? "bg-rose-500/15 px-2 text-rose-300"
                    : "px-2 text-zinc-500"
              }
            >
              {d.op === "@" ? d.line : `${d.op} ${d.line}`}
            </div>
          ))}
        </div>
      )}
      {rejected ? (
        <p className="mt-2 text-sm text-muted-foreground">отклонено — ветка и worktree удалены</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen(!open)}>
            <Icon name={open ? "visibility_off" : "visibility"} size={16} className="mr-1" />
            {open ? "Скрыть дифф" : "Посмотреть"}
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void reject()}>
            {busy ? (
              <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
            ) : (
              <Icon name="close" size={16} className="mr-1" />
            )}
            Отклонить
          </Button>
          <span className="text-xs text-muted-foreground">
            применение и пуш — за человеком (git merge в рабочей копии)
          </span>
        </div>
      )}
    </div>
  );
}

function PromptChangeCardView({ card }: { card: Card }) {
  const [status, setStatus] = useState<string>(card.status ?? "pending");
  const [busy, setBusy] = useState(false);
  const isSkill = card.kind === "skill";
  const what = isSkill ? `скилла ${card.agent}${card.file ? ` · ${card.file}` : ""}` : `промпта: ${card.agent}`;

  const act = async (action: "approve" | "reject") => {
    setBusy(true);
    try {
      const res = await fetch(`/api/tuning/changes/${card.change_id}/${action}`, { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      setStatus(action === "approve" ? "applied" : "rejected");
      toast.success(
        action === "approve"
          ? isSkill
            ? "Скилл обновлён — применится к новым вызовам"
            : "Промпт обновлён — применится к новым ответам"
          : "Правка отклонена"
      );
    } catch {
      toast.error("Не удалось — попробуй ещё раз");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-sky-500/40 bg-sky-500/5 p-4">
      <p className="mb-1 flex items-center gap-2 text-sm font-medium">
        <Icon name="tune" size={16} className="text-sky-500" />
        Правка {what}
      </p>
      <p className="mb-2 text-sm text-muted-foreground">{card.summary}</p>
      <div className="max-h-64 overflow-auto rounded-lg border bg-zinc-950 font-mono text-xs leading-5">
        {(card.diff ?? []).slice(0, 60).map((d, i) => (
          <div
            key={i}
            className={
              d.op === "+"
                ? "bg-emerald-500/15 px-2 text-emerald-300"
                : d.op === "-"
                  ? "bg-rose-500/15 px-2 text-rose-300"
                  : "px-2 text-zinc-500"
            }
          >
            {d.op === "@" ? d.line : `${d.op} ${d.line}`}
          </div>
        ))}
      </div>
      {status === "pending" ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => void act("approve")}>
            {busy ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : <Icon name="check" size={16} className="mr-1" />}
            Применить
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("reject")}>
            <Icon name="close" size={16} className="mr-1" /> Отклонить
          </Button>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">
          {status === "applied" ? (<><Icon name="check_circle" size={16} className="mr-1 inline align-[-2px]" filled /> применено — поведение агента обновлено</>) : "отклонено"}
        </p>
      )}
    </div>
  );
}
