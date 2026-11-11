"use client";

/** Карточки-решения (B-003): action_offer и quick_replies — один компонент.
 *  Варианты приходят слитыми с сервера (одна группа решений на ход); клик =
 *  resolve на сервере + обычное сообщение. Статус переживает перезагрузку. */

import { Icon } from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import type { CardProps } from "./shared";
import { decisionOptions, resolveCard, useCardState } from "./shared";

export function DecisionCard({ card, onSend, conversationUid }: CardProps) {
  const [state, setState] = useCardState(card);
  const isOffer = card.type === "action_offer";
  const options = decisionOptions(card);

  const pick = (label: string, text: string) => {
    if (state.status === "resolved") return;
    setState({ status: "resolved", choice: label });
    void resolveCard(conversationUid, card.card_id, label);
    onSend?.(text);
  };

  const head = isOffer ? (
    <>
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-primary">
        <Icon name="task_alt" size={14} /> Предложение
      </p>
      <p className="font-medium">{card.title}</p>
      {card.description && <p className="mt-1 text-sm text-muted-foreground">{card.description}</p>}
    </>
  ) : null;

  if (state.status === "resolved") {
    return (
      <div className={isOffer ? "rounded-xl border border-primary/40 bg-primary/5 p-4" : "px-1"}>
        {head}
        <p className="mt-2 flex items-center gap-1.5 text-sm text-muted-foreground">
          <Icon name="check" size={14} className="text-emerald-500" /> выбор: {state.choice}
        </p>
      </div>
    );
  }

  return (
    <div className={isOffer ? "rounded-xl border border-primary/40 bg-primary/5 p-4" : "px-1"}>
      {head}
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((o) => (
          <Button
            key={o.label}
            size="sm"
            variant={isOffer && o.label === "Да" ? "default" : "outline"}
            className={isOffer ? "" : "rounded-full"}
            disabled={!onSend}
            onClick={() => pick(o.label, o.text)}
          >
            {o.label === "Да" && <Icon name="check" size={16} className="mr-1" />}
            {o.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
