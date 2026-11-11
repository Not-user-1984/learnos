"use client";

/** Карточки правок: промпт/скилл (tuning) и ветка агента (revision).
 *  Применение/отклонение помечает карточку на сервере — кнопки не воскресают (B-003). */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import type { CardProps } from "./shared";
import { useCardState } from "./shared";

/** Правка промпта/скилла: дифф + применить/отклонить (эндпоинт tuning помечает карточку). */
export function PromptChangeCard({ card, conversationUid }: CardProps) {
  const [state, setState] = useCardState(card);
  const [busy, setBusy] = useState(false);
  const isSkill = card.kind === "skill";
  const what = isSkill ? `скилла ${card.agent}${card.file ? ` · ${card.file}` : ""}` : `промпта: ${card.agent}`;
  const status = state.status ?? "pending";

  const act = async (action: "approve" | "reject") => {
    setBusy(true);
    try {
      await apiPost(`/tuning/changes/${card.change_id}/${action}`, {
        conversation_uid: conversationUid ?? null,
        card_id: card.card_id ?? null,
      });
      setState({ status: action === "approve" ? "applied" : "rejected" });
      toast.success(
        action === "approve"
          ? isSkill
            ? "Скилл обновлён — применится к новым вызовам"
            : "Промпт обновлён — применится к новым ответам"
          : "Правка отклонена",
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
            {busy ? (
              <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
            ) : (
              <Icon name="check" size={16} className="mr-1" />
            )}
            Применить
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => void act("reject")}>
            <Icon name="close" size={16} className="mr-1" /> Отклонить
          </Button>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">
          {status === "applied" ? (
            <>
              <Icon name="check_circle" size={16} className="mr-1 inline align-[-2px]" filled /> применено — поведение
              агента обновлено
            </>
          ) : (
            "отклонено"
          )}
        </p>
      )}
    </div>
  );
}

/** Ветка агента (T-038): просмотр диффа и отклонение; применение — за человеком. */
export function GitChangeCard({ card, conversationUid }: CardProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [state, setState] = useCardState(card);

  const reject = async () => {
    if (!card.branch || busy) return;
    setBusy(true);
    try {
      await apiPost("/revision/branch/reject", {
        branch: card.branch,
        conversation_uid: conversationUid ?? null,
        card_id: card.card_id ?? null,
      });
      setState({ status: "rejected" });
      toast.success(`Ветка ${card.branch} удалена`);
    } catch {
      toast.error("Не удалось удалить ветку");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-primary/40 bg-primary/5 p-4">
      <p className="mb-1 flex items-center gap-2 text-sm font-medium">
        <Icon name="fork_right" size={16} className="text-primary" /> Ветка агента:{" "}
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
      {state.status === "rejected" ? (
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
          <span className="text-xs text-muted-foreground">применение и пуш — за человеком (git merge в рабочей копии)</span>
        </div>
      )}
    </div>
  );
}
