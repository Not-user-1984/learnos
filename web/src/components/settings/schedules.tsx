"use client";

/** Расписания самоулучшения (B-010): включить/выключить/запустить сейчас, last_status. */

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Schedule = {
  name: string;
  cron: string;
  action: string;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string;
};

const LABELS: Record<string, string> = {
  auditor: "Аудитор кода",
  repo_scout: "Скаут идей (GitHub)",
  review_digest: "Напоминание о повторениях",
};

export function SchedulesSettings() {
  const [items, setItems] = useState<Schedule[] | null>(null);

  const load = () => api<Schedule[]>("/schedules").then(setItems).catch(() => setItems([]));
  useEffect(() => {
    void load();
  }, []);

  const toggle = async (s: Schedule) => {
    try {
      await apiPost(`/schedules/${s.name}/enable`, { enabled: !s.enabled });
      toast.success(`${LABELS[s.name] ?? s.name}: ${!s.enabled ? "включено" : "выключено"}`);
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось");
    }
  };

  const runNow = async (s: Schedule) => {
    toast.info(`${LABELS[s.name] ?? s.name}: запускаю…`);
    try {
      await apiPost(`/schedules/${s.name}/run`, {});
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось");
    }
  };

  return (
    <section className="rounded-2xl border bg-card p-6">
      <h2 className="font-medium">Расписания самоулучшения</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Агенты по расписанию ищут проблемы и идеи (квота GLM — включай осознанно); напоминания о повторениях приходят в Telegram.
      </p>
      {items === null ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Icon name="progress_activity" size={15} className="animate-spin" /> загрузка…
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-2">
          {items.map((s) => (
            <li key={s.name} className="flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{LABELS[s.name] ?? s.name}</p>
                <p className="text-xs text-muted-foreground">
                  <code className="font-mono">{s.cron}</code> · {s.action} ·{" "}
                  {s.last_run_at ? `последний: ${new Date(s.last_run_at).toLocaleString("ru-RU")}` : "ещё не запускалось"}
                  {s.last_status !== "never" && ` · ${s.last_status}`}
                </p>
              </div>
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs",
                  s.enabled ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground",
                )}
              >
                {s.enabled ? "вкл" : "выкл"}
              </span>
              <Button size="sm" variant="outline" onClick={() => void toggle(s)}>
                {s.enabled ? "Выключить" : "Включить"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => void runNow(s)}>
                <Icon name="play_arrow" size={16} /> Сейчас
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
