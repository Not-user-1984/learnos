"use client";

/** Реестр карточек чата: type → компонент (B-003: cards.tsx разнесён по файлам). */

import type { Card } from "@/lib/types";
import type { CardProps } from "./shared";
import { CommandCard } from "./command";
export { stripCommandFences } from "./command";
import { ChapterReviewCard, EvaluationCard, QuestionCard } from "./simple";
import { BlockCard, NoteDraftCard } from "./blocks";
import { GitChangeCard, PromptChangeCard } from "./changes";
import { DecisionCard } from "./decisions";

const REGISTRY: Record<string, (props: CardProps) => React.ReactElement | null> = {
  command: CommandCard,
  question: QuestionCard,
  evaluation: EvaluationCard,
  block_saved: BlockCard,
  block_updated: BlockCard,
  prompt_change: PromptChangeCard,
  git_change: GitChangeCard,
  note_draft: NoteDraftCard,
  action_offer: DecisionCard,
  quick_replies: DecisionCard,
  chapter_review: ChapterReviewCard,
};

export function CardView(props: { card: Card } & CardProps) {
  const Component = REGISTRY[props.card.type];
  return Component ? <Component {...props} /> : null;
}
