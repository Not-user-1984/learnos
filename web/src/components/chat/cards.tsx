"use client";

/** Карточки UI в чате: команда, вопрос, оценка, блок, job. */

import { useState } from "react";
import Link from "next/link";
import { Check, ClipboardCopy, Loader2, Terminal } from "lucide-react";
import { toast } from "sonner";
import type { Card } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-500",
  medium: "bg-amber-500/15 text-amber-500",
  high: "bg-rose-500/15 text-rose-500",
};

export function CardView({ card, onInsert }: { card: Card; onInsert?: (text: string) => void }) {
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
