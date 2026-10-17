"use client";

/** Кнопки интеграций: настройка агентов словами и тест Telegram-моста. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, MessageCircle, Send, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function TuneAgentButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const open = async () => {
    setBusy(true);
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode: "tuning",
        title: "Настройка агентов",
      });
      router.push(`/chat/${conv.uid}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button onClick={open} disabled={busy}>
      {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Settings2 className="mr-1.5 h-4 w-4" />}
      Настроить агента словами
    </Button>
  );
}

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
        {busy ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}
        Отправить тест
      </Button>
      <Button variant="ghost" size="sm" onClick={check}>
        <MessageCircle className="mr-1.5 h-4 w-4" />
        {state ? (state.configured ? "мост настроен" : "нет токена") : "статус"}
      </Button>
    </div>
  );
}
