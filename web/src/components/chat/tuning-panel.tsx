"use client";

/** Пустое состояние настройки: список агентов с раскрытием + конструктор (общий с настройками). */

import { Settings2 } from "lucide-react";
import { AgentsSettings } from "@/components/settings/agents-settings";

export function TuningEmptyState() {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
        <Settings2 className="mb-1 h-4 w-4 text-sky-500" />
        Скажи словами, как должен вести себя агент — например: «пусть учитель задаёт больше
        вопросов и шутит», «разбор делай короче», «практику всегда на маке». Настройщик
        покажет правку промпта диффом — применишь кнопкой.
      </div>
      <AgentsSettings />
    </div>
  );
}
