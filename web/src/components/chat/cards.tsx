"use client";

/** Карточки UI в чате: команда, вопрос, оценка, блок, job, превью конспекта. */

import { useState } from "react";
import Link from "next/link";
import { Check, ClipboardCopy, Loader2, NotebookPen, Pencil, Settings2, Terminal, X } from "lucide-react";
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
    case "job":
      return <JobCardView card={card} />;
    case "prompt_change":
      return <PromptChangeCardView card={card} />;
    case "note_draft":
      return <NoteDraftCardView card={card} onInsert={onInsert} onSend={onSend} />;
    default:
      return null;
  }
}

function CommandCardView({ card, onInsert }: { card: Card; onInsert?: (t: string) => void }) {
  const [output, setOutput] = useState("");
  const risk = (card.risk ?? "low") as keyof typeof RISK_COLORS;
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge className="gap-1 bg-violet-500/15 text-violet-500 hover:bg-violet-500/25">
          <Terminal className="h-3 w-3" /> {card.machine_name ?? card.machine ?? ""}
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
          <ClipboardCopy className="h-4 w-4" /> Копировать
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
    <div className="rounded-xl border border-violet-500/40 bg-violet-500/5 p-4">
      <p className="mb-1 text-xs text-muted-foreground">
        Фейнман-вопрос {card.index ?? ""}
        {card.total ? ` / ${card.total}` : ""} {card.concept && `· ${card.concept}`}
      </p>
      <p className="font-medium">{card.question}</p>
    </div>
  );
}

function EvaluationCardView({ card }: { card: Card }) {
  const icon = card.verdict === "understood" ? "✅" : card.verdict === "partial" ? "◐" : "❌";
  const label = card.verdict === "understood" ? "понял" : card.verdict === "partial" ? "частично" : "мимо";
  return (
    <div className="rounded-xl border p-4">
      <p className="mb-1 font-medium">
        {icon} {label}
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
          <Check className="h-4 w-4 text-emerald-500" /> Блок сохранён ({card.kind === "lesson" ? "урок" : "конспект"})
        </p>
        <p className="font-medium">{card.title}</p>
        {card.summary && <p className="mt-1 text-sm text-muted-foreground">{card.summary}</p>}
        {card.category_suggested && (
          <p className="mt-2 text-sm">
            Категория: <b>{card.category_suggested}</b> — подтвердите во{" "}
            <Link className="text-violet-500 hover:underline" href="/kb?view=inbox">
              Входящих
            </Link>
          </p>
        )}
        <Link href={`/kb/${card.block_uid}`} className="mt-2 inline-block text-sm text-violet-500 hover:underline">
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
        <Link href={`/kb/${card.block_uid}`} className="text-sm text-violet-500 hover:underline">
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
          {restoring && <Loader2 className="h-3 w-3 animate-spin" />}
          Откатить к v{card.from_version}
        </button>
      </div>
    </div>
  );
}

function JobCardView({ card }: { card: Card }) {
  const total = card.total ?? 0;
  const pct = total > 0 ? Math.round(((card.progress ?? 0) / total) * 100) : 0;
  return (
    <div className="rounded-xl border p-4">
      <p className="mb-2 text-sm font-medium">
        Задача {card.kind === "process_source" ? "обработки источника" : card.kind === "summarize_chapters" ? "summary глав" : card.kind}
      </p>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-violet-500 transition-all" style={{ width: `${card.status === "done" ? 100 : pct}%` }} />
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {card.status === "done" ? "готово" : card.status === "failed" ? "ошибка" : `${card.progress ?? 0}/${total}`}
      </p>
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
        <NotebookPen className="h-4 w-4 text-sky-500" /> Превью конспекта
        {card.preview_id ? ` #${card.preview_id}` : ""} · ничего не записано
      </p>
      <p className="font-medium">{d.title}</p>
      {d.summary && <p className="mt-1 text-sm text-muted-foreground">{d.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {d.category_suggestion && (
          <Badge className="bg-violet-500/15 text-violet-500">категория: {d.category_suggestion}</Badge>
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
            {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
            Записать в базу
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">агент записывает…</span>
        )}
        {onInsert && !busy && (
          <Button size="sm" variant="outline" onClick={() => onInsert(`Поправим конспект (превью #${card.preview_id}): `)}>
            <Pencil className="mr-1 h-4 w-4" /> Поправить
          </Button>
        )}
        <span className="text-xs text-muted-foreground">
          правки можно писать словами — «это уберём», «это дополним», соберу новое превью
        </span>
      </div>
    </div>
  );
}

function PromptChangeCardView({ card }: { card: Card }) {
  const [status, setStatus] = useState<string>(card.status ?? "pending");
  const [busy, setBusy] = useState(false);

  const act = async (action: "approve" | "reject") => {
    setBusy(true);
    try {
      const res = await fetch(`/api/tuning/changes/${card.change_id}/${action}`, { method: "POST" });
      if (!res.ok) throw new Error(String(res.status));
      setStatus(action === "approve" ? "applied" : "rejected");
      toast.success(action === "approve" ? "Промпт обновлён — применится к новым ответам" : "Правка отклонена");
    } catch {
      toast.error("Не удалось — попробуй ещё раз");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-sky-500/40 bg-sky-500/5 p-4">
      <p className="mb-1 flex items-center gap-2 text-sm font-medium">
        <Settings2 className="h-4 w-4 text-sky-500" />
        Правка промпта: <b>{card.agent}</b>
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
            {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
            Применить
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("reject")}>
            <X className="mr-1 h-4 w-4" /> Отклонить
          </Button>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">
          {status === "applied" ? "✅ применено — поведение агента обновлено" : "отклонено"}
        </p>
      )}
    </div>
  );
}
