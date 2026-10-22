"use client";

/** Пустое состояние настройки: список агентов с раскрытием + конструктор (общий с настройками). */

import { Icon } from "@/components/ui/icon";
import { AgentsSettings } from "@/components/settings/agents-settings";

export function TuningEmptyState() {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
        <Icon name="tune" size={16} className="mb-1 text-sky-500" />
        Скажи словами, как должен вести себя агент — например: «пусть учитель задаёт больше
        вопросов и шутит», «разбор делай короче», «практику всегда на маке». Настройщик
        покажет правку промпта диффом — применишь кнопкой.
      </div>
      <AgentsSettings />
    </div>
  );
}
