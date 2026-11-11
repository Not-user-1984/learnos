"use client";

/** Карточка команды: копирование, вставка вывода; fenced-дубль в тексте гасится (B-003). */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CardProps } from "./shared";

const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/15 text-emerald-500",
  medium: "bg-amber-500/15 text-amber-500",
  high: "bg-rose-500/15 text-rose-500",
};

/** Убрать из markdown fenced-блоки, дублирующие карточку command (команда — один раз). */
export function stripCommandFences(content: string, commands: Set<string>): string {
  if (!commands.size) return content;
  return content.replace(/```[^\n]*\n([\s\S]*?)```/g, (whole, code: string) =>
    commands.has(code.trim()) ? "" : whole,
  );
}

export function CommandCard({ card, onInsert }: CardProps) {
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
