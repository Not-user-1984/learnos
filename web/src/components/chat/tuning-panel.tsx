"use client";

/** Пустое состояние настройки: какие агенты есть и что настроено. */

import { useEffect, useState } from "react";
import { FileCode2, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

type PromptInfo = {
  agent: string;
  description: string;
  module: string;
  has_override: boolean;
};

export function TuningEmptyState() {
  const [agents, setAgents] = useState<PromptInfo[] | null>(null);

  useEffect(() => {
    api<PromptInfo[]>("/tuning/prompts").then(setAgents).catch(() => setAgents([]));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
        <Settings2 className="mb-1 h-4 w-4 text-sky-500" />
        Скажи словами, как должен вести себя агент — например: «пусть учитель задаёт больше
        вопросов и шутит», «разбор делай короче», «практику всегда на маке». Настройщик
        покажет правку промпта диффом — применишь кнопкой.
      </div>
      <div className="flex flex-col gap-2">
        <p className="px-1 text-xs font-medium text-muted-foreground">Агенты и их текущее состояние:</p>
        {agents === null ? (
          <p className="px-1 text-xs text-muted-foreground">загружаю…</p>
        ) : (
          agents.map((a) => (
            <div key={a.agent} className="flex items-start gap-2.5 rounded-xl border bg-card px-4 py-2.5">
              <FileCode2 className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {a.agent}
                  {a.has_override && (
                    <Badge variant="secondary" className="ml-2 text-[10px]">
                      настроен
                    </Badge>
                  )}
                </p>
                <p className="text-xs text-muted-foreground">{a.description}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
