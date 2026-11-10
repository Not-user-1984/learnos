"use client";

/** Панель LLM (BB-004): карточки ролей (модель/провайдер/params) и цепочка ключей
 *  с состоянием каждого ключа и обратным отсчётом cooldown. Значений ключей
 *  сервер не отдаёт — только номера. Обновление: кнопка + автоматически раз в 30 с. */

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { LlmStatus } from "@/lib/types";

const REFRESH_MS = 30_000;

const ROLE_META: Record<string, { label: string; icon: string }> = {
  chat: { label: "Диалог и разбор", icon: "forum" },
  structured: { label: "Структурированный вывод", icon: "data_object" },
  fast: { label: "Быстрые операции", icon: "bolt" },
  vision: { label: "Зрение", icon: "visibility" },
};

/** Параметр роли компактно: {type: disabled} → "thinking: disabled", остальное — JSON. */
const paramView = (key: string, value: unknown): string => {
  if (value && typeof value === "object" && "type" in (value as Record<string, unknown>)) {
    return `${key}: ${String((value as Record<string, unknown>).type)}`;
  }
  return `${key}: ${JSON.stringify(value)}`;
};

const cooldownView = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

export function LlmSettings() {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [loading, setLoading] = useState(false);
  // now тикает каждую секунду; receivedAt — момент получения статуса: разница = отсчёт cooldown
  const [now, setNow] = useState(0);
  const [receivedAt, setReceivedAt] = useState(0);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const fresh = await api<LlmStatus>("/llm/status");
      if (!alive.current) return;
      const at = Date.now();
      setStatus(fresh);
      setReceivedAt(at);
      setNow(at);
    } catch (e) {
      if (alive.current) toast.error(e instanceof Error ? e.message : "статус LLM недоступен");
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    const first = setTimeout(() => void refresh(), 0);
    const auto = setInterval(() => void refresh(), REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      alive.current = false;
      clearTimeout(first);
      clearInterval(auto);
      clearInterval(tick);
    };
  }, [refresh]);

  const handleRefresh = async () => {
    setLoading(true);
    try {
      await refresh();
    } finally {
      setLoading(false);
    }
  };

  if (status === null) {
    return <p className="text-sm text-muted-foreground">Статус LLM недоступен (ядро не отвечает)</p>;
  }

  const elapsed = receivedAt ? (now - receivedAt) / 1000 : 0;
  const roleNames = Object.keys(status.roles);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={status.configured ? "secondary" : "destructive"}>
          {status.configured ? "LLM подключён" : "LLM не настроен"}
        </Badge>
        {status.reason ? <span className="text-sm text-muted-foreground">{status.reason}</span> : null}
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading} className="ml-auto">
          {loading ? (
            <Icon name="progress_activity" size={16} className="mr-1 animate-spin" />
          ) : (
            <Icon name="refresh" size={16} className="mr-1" />
          )}
          Обновить
        </Button>
      </div>

      {roleNames.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {roleNames.map((role) => {
            const info = status.roles[role];
            const meta = ROLE_META[role];
            return (
              <div key={role} className="flex flex-col gap-1.5 rounded-xl border bg-background/50 p-3 text-sm">
                <p className="flex items-center gap-1.5 font-medium">
                  <Icon name={meta?.icon ?? "smart_toy"} size={16} className="text-primary" />
                  {meta?.label ?? role}
                  <span className="text-xs font-normal text-muted-foreground">({role})</span>
                </p>
                <p className="text-muted-foreground">
                  {info.model} <span className="text-xs">· {info.provider}</span>
                </p>
                {Object.keys(info.params).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(info.params).map(([key, value]) => (
                      <Badge key={key} variant="outline">
                        {paramView(key, value)}
                      </Badge>
                    ))}
                  </div>
                )}
                {!info.configured && (
                  <p className="text-xs text-destructive">{info.reason ?? "роль не настроена"}</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {Object.entries(status.providers).map(([name, prov]) => (
        <div key={name} className="rounded-xl border bg-background/50 p-4 text-sm">
          <p className="mb-2 flex items-center gap-1.5 font-medium">
            <Icon name="key" size={16} className="text-primary" /> {name}
            <span className="text-xs font-normal text-muted-foreground">
              · {prov.type}
              {prov.keyless ? " · без ключей" : ` · ключей: ${prov.keys_total}`}
            </span>
          </p>
          {prov.reason ? <p className="text-xs text-destructive">{prov.reason}</p> : null}
          {prov.keychain ? (
            <ul className="flex flex-wrap gap-1.5">
              {prov.keychain.keys.map((k) => {
                if (k.state === "cooldown" && typeof k.cooldown_seconds === "number") {
                  const left = Math.max(0, k.cooldown_seconds - elapsed);
                  return (
                    <li key={k.index}>
                      <Badge variant="destructive" title="Ключ в cooldown после ошибки квоты">
                        #{k.index} · cooldown {cooldownView(left)}
                      </Badge>
                    </li>
                  );
                }
                return (
                  <li key={k.index}>
                    <Badge
                      variant={k.state === "active" ? "secondary" : "outline"}
                      title={k.state === "active" ? "Рабочий ключ цепочки" : "Свободен — подхватится при ротации"}
                    >
                      #{k.index} · {k.state === "active" ? "рабочий" : "свободен"}
                    </Badge>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">
              Цепочка оживёт после первого запроса к провайдеру
            </p>
          )}
        </div>
      ))}

      <p className="text-xs text-muted-foreground">
        Ключи — ZAI_API_KEY…4 из окружения; роли и модели — правка <code>server/config/llm.yaml</code>.
        Значения ключей не хранятся и не отдаются.
      </p>
    </div>
  );
}
