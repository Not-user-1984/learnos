"use client";

/** Общие пропсы и хелперы карточек чата (B-003: статус решений — на сервере). */

import { useState } from "react";
import { toast } from "sonner";
import { apiPost } from "@/lib/api";
import type { Card } from "@/lib/types";

export type CardProps = {
  card: Card;
  onInsert?: (text: string) => void;
  onSend?: (text: string) => void;
  /** Разговор, в котором живёт карточка — нужен для resolve по card_id. */
  conversationUid?: string;
  /** note_draft: uid блока, записанного после этого превью (если уже записан). */
  noteSavedBlockUid?: string;
};

/** Статус карточки с решением: сервер — истина, локальное значение — оптимистичное
 *  покрытие между кликом и завершением запроса. */
export function useCardState(card: Card): [{ status?: string; choice?: string }, (s: { status?: string; choice?: string }) => void] {
  const [state, setState] = useState<{ status?: string; choice?: string }>({
    status: card.status,
    choice: card.choice,
  });
  return [state, setState];
}

/** Зафиксировать выбор на сервере (идемпотентно); сбоя не боимся — кнопка уже нажата. */
export async function resolveCard(conversationUid: string | undefined, cardId: string | undefined, choice: string) {
  if (!conversationUid || !cardId) return;
  try {
    await apiPost(`/conversations/${conversationUid}/cards/${cardId}/resolve`, { choice });
  } catch {
    toast.error("Не удалось зафиксировать выбор — кнопка может вернуться после перезагрузки");
  }
}

/** Универсальные варианты карточки-решения: сервер присылает options (со слиянием),
 *  старым карточкам дефолты собираем здесь — по тем же правилам, что и сервер. */
export function decisionOptions(card: Card): { label: string; text: string }[] {
  if (card.options?.length) return card.options;
  if (card.type === "action_offer") {
    return [
      { label: "Да", text: `Да — делай: «${card.title ?? ""}»` },
      { label: "Нет", text: `Нет, не надо: «${card.title ?? ""}»` },
    ];
  }
  return (card.replies ?? []).map((r) => ({ label: r, text: r }));
}
