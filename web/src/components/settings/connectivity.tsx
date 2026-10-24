"use client";

/** «Прокси и поиск»: ключи поиска (Tavily/Serper), socks5/http-прокси и vless-ключ
 *  (xray-sidecar превращает его в socks5://xray:1080 для всего стека).
 *  Применяется на лету: провайдер/прокси пересобираются без рестарта сервера. */

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, apiPost } from "@/lib/api";
import type { SearchProvidersView } from "@/lib/types";

type Connectivity = {
  search_provider: string;
  search_api_key: string;
  proxy_url: string;
  vless_key: string;
  has_search_api_key?: boolean;
  has_vless_key?: boolean;
};

type CheckResult = Record<string, string> & { proxy?: string };

const PROVIDERS = [
  { value: "chain", label: "Бесплатная цепочка (DDG → Википедия → HN)" },
  { value: "tavily", label: "Tavily (ключ, 1000/мес free)" },
  { value: "serper", label: "Serper — Google-выдача (ключ, 2500 free)" },
];

type ProviderCategory = "web" | "academic" | "video";

const CATEGORY_META: Record<ProviderCategory, { label: string; icon: string; iconClass: string }> = {
  web: { label: "Веб", icon: "public", iconClass: "text-emerald-500" },
  academic: { label: "Научные статьи", icon: "school", iconClass: "text-sky-500" },
  video: { label: "Видео", icon: "play_circle", iconClass: "text-rose-500" },
};

const MODE_LABEL: Record<string, string> = {
  chain: "цепочка: первый непустый ответ",
  single: "один провайдер",
  aggregate: "агрегат: все сразу, с дедупом",
};

export function ConnectivitySettings() {
  const [state, setState] = useState<Connectivity | null>(null);
  const [provider, setProvider] = useState("chain");
  const [apiKey, setApiKey] = useState("");
  const [proxyUrl, setProxyUrl] = useState("");
  const [vlessKey, setVlessKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [providers, setProviders] = useState<SearchProvidersView | null>(null);

  useEffect(() => {
    api<Connectivity>("/connectivity")
      .then((c) => {
        setState(c);
        setProvider(c.search_provider || "chain");
        setProxyUrl(c.proxy_url || "");
        setApiKey(c.search_api_key || "");
        setVlessKey(c.vless_key || "");
      })
      .catch(() => setState(null));
    api<SearchProvidersView>("/research/providers").then(setProviders).catch(() => setProviders(null));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const res = await apiPost<{ ok: boolean; error?: string; applied?: { provider: string; proxy: string; vless: boolean } }>(
        "/connectivity",
        {
          search_provider: provider,
          search_api_key: apiKey.includes("…") ? "" : apiKey.trim(),
          proxy_url: proxyUrl.trim(),
          vless_key: vlessKey.includes("…") ? "" : vlessKey.trim(),
        },
      );
      if (!res.ok) {
        toast.error(res.error || "не удалось сохранить");
        return;
      }
      toast.success(
        `Применено: поиск «${res.applied?.provider}», прокси ${res.applied?.vless ? "через xray (vless)" : res.applied?.proxy || "не задан"}`,
      );
      const fresh = await api<Connectivity>("/connectivity").catch(() => null);
      if (fresh) {
        setState(fresh);
        setApiKey(fresh.search_api_key || "");
        setVlessKey(fresh.vless_key || "");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "ошибка");
    } finally {
      setBusy(false);
    }
  };

  const runCheck = async () => {
    setChecking(true);
    try {
      const res = await apiPost<CheckResult>("/connectivity/check", {});
      setCheck(res);
    } catch {
      toast.error("проверка не удалась");
    } finally {
      setChecking(false);
    }
  };

  if (state === null) {
    return <p className="text-sm text-muted-foreground">Настройки связи недоступны (ядро не отвечает)</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="flex items-center gap-1.5">
            <Icon name="public" size={16} className="text-emerald-500" /> Поиск
          </span>
          <Select onValueChange={(v: unknown) => { const val = Array.isArray(v) ? String(v[0]) : (v as string | null); if (val) setProvider(val); }}>
            <SelectTrigger aria-label="Провайдер поиска">
              <SelectValue placeholder={PROVIDERS.find((p) => p.value === provider)?.label ?? "Цепочка"} />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span>API-ключ поиска</span>
          <Input
            placeholder={state.has_search_api_key ? state.search_api_key : "tvly-… или ключ serper"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
      </div>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="flex items-center gap-1.5">
          <Icon name="verified_user" size={16} className="text-sky-500" /> Прокси socks5/http (для всего стека)
        </span>
        <Input
          placeholder="socks5://192.168.0.100:7890 или http://…"
          value={proxyUrl}
          onChange={(e) => setProxyUrl(e.target.value)}
        />
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="flex items-center gap-1.5">
          <Icon name="electric_bolt" size={16} className="text-primary" /> VLESS-ключ (внутренний xray → socks5)
        </span>
        <Input
          placeholder={state.has_vless_key ? state.vless_key : "vless://uuid@host:порт?…"}
          value={vlessKey}
          onChange={(e) => setVlessKey(e.target.value)}
        />
        <span className="text-xs text-muted-foreground">
          Вставь ссылку целиком — стек сам превратит её в прокси (применение до ~15 секунд). Приоритет: vless → socks5/http → без прокси.
        </span>
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={busy}>
          {busy ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : null} Сохранить и применить
        </Button>
        <Button variant="outline" onClick={runCheck} disabled={checking}>
          {checking ? <Icon name="progress_activity" size={16} className="mr-1 animate-spin" /> : null} Проверить связь
        </Button>
      </div>

      {providers && (
        <div className="rounded-xl border bg-background/50 p-4 text-sm">
          <p className="mb-3 font-medium">Провайдеры поиска</p>
          <div className="flex flex-col gap-3">
            {(Object.keys(CATEGORY_META) as ProviderCategory[]).map((cat) => {
              const block = providers[cat];
              if (!block) return null;
              const meta = CATEGORY_META[cat];
              return (
                <div key={cat} className="flex flex-col gap-1.5">
                  <p className="flex items-center gap-1.5 text-muted-foreground">
                    <Icon name={meta.icon} size={16} className={meta.iconClass} /> {meta.label}
                    {MODE_LABEL[block.mode] ? <span className="text-xs">· {MODE_LABEL[block.mode]}</span> : null}
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {block.providers.map((p) => (
                      <li
                        key={p.name}
                        className="flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs"
                        title={p.note}
                      >
                        <span className="font-medium">{p.name}</span>
                        <Badge variant={p.enabled ? "secondary" : "outline"}>
                          {p.enabled ? "вкл" : "выкл"}
                        </Badge>
                        <span className="text-muted-foreground">{p.note}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {check && (
        <div className="rounded-xl border bg-background/50 p-4 text-sm">
          <p className="mb-2 font-medium">Диагностика</p>
          <ul className="flex flex-col gap-1 text-muted-foreground">
            {Object.entries(check).map(([k, v]) => (
              <li key={k}>
                {k}: <b className="text-foreground">{v}</b>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
