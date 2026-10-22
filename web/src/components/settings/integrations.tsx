"use client";

/** Кнопки интеграций: тест Telegram-моста. */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function TelegramTestButton() {
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<{ configured: boolean } | null>(null);

  const check = async () => {
    setState(await api<{ configured: boolean }>("/messenger/status").catch(() => ({ configured: false })));
  };

  const send = async () => {
    setBusy(true);
    try {
      await apiPost<{ ok: boolean; chunks: number }>("/messenger/test", {});
      toast.success("Отправлено в Telegram — проверь личку");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не отправилось");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="outline" onClick={send} disabled={busy}>
        {busy ? <Icon name="progress_activity" size={16} className="mr-1.5 animate-spin" /> : <Icon name="send" size={16} className="mr-1.5" />}
        Отправить тест
      </Button>
      <Button variant="ghost" size="sm" onClick={check}>
        <Icon name="chat_bubble" size={16} className="mr-1.5" />
        {state ? (state.configured ? "мост настроен" : "нет токена") : "статус"}
      </Button>
    </div>
  );
}
