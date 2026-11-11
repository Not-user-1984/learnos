"use client";

/** Простые карточки без решений: фейнман-вопрос, оценка ответа, разбор главы/видео. */

import { Icon } from "@/components/ui/icon";
import type { CardProps } from "./shared";

/** Фейнман-вопрос: ответ — своим текстом в чат. */
export function QuestionCard({ card }: CardProps) {
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

/** Оценка фейнман-ответа: понял / частично / мимо. */
export function EvaluationCard({ card }: CardProps) {
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

/** Разбор главы/видео (T-046 Э2): структурированный итог быстрого разбора. */
export function ChapterReviewCard({ card }: CardProps) {
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
