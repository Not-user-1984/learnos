"use client";

/** Сторонние MCP-подключения: список со статусами, конструктор (ссылка/конфиг → LLM), проверка, удаление. */

import { useCallback, useEffect, useState } from "react";
import { Cable, Loader2, Plug, PlugZap, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiDelete, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type McpInfo = {
  name: string;
  url: string;
  description: string;
  status: "ok" | "error" | "unchecked" | string;
  last_error: string | null;
  tools_count: number;
  tool_names: string[];
};

type Draft = { name: string; url: string; description: string; headers: Record<string, string>; summary: string };

const STATUS_VIEW: Record<string, { label: string; cls: string }> = {
  ok: { label: "подключён", cls: "text-emerald-500" },
  error: { label: "недоступен", cls: "text-rose-500" },
  unchecked: { label: "не проверен", cls: "text-muted-foreground" },
};

export function McpConnections() {
  const [list, setList] = useState<McpInfo[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<{ ok: boolean; count?: number; error?: string } | null>(null);
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<McpInfo | null>(null);

  const reload = useCallback(() => {
    api<McpInfo[]>("/mcpext").then(setList).catch(() => setList([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const composeDraft = async () => {
    if (raw.trim().length < 4) {
      toast.error("кинь ссылку на MCP или вставь JSON-конфиг");
      return;
    }
    setDrafting(true);
    setDraftError(null);
    setProbeResult(null);
    try {
      const d = await apiPost<Draft>("/mcpext/draft", { brief: raw });
      if (!d.url) {
        // сервер объяснил причину в summary — показываем в модалке, чтобы не потерялось
        setDraftError(d.summary || "не нашёл ссылку — поддерживаются remote MCP по http(s)");
        return;
      }
      setDraft(d);
    } catch (e) {
      setDraftError(e instanceof Error ? e.message : "конструктор не сработал");
    } finally {
      setDrafting(false);
    }
  };

  const probe = async () => {
    if (!draft) return;
    setProbing(true);
    try {
      const r = await apiPost<{ ok: boolean; count?: number; error?: string }>("/mcpext/probe", {
        url: draft.url,
        headers: draft.headers,
      });
      setProbeResult(r);
      if (r.ok) toast.success(`Сервер отвечает: ${r.count} инструментов`);
      else toast.error(r.error?.slice(0, 120) ?? "сервер недоступен");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "проверка не удалась");
    } finally {
      setProbing(false);
    }
  };

  const create = async () => {
    if (!draft) return;
    setCreating(true);
    try {
      const r = await apiPost<{ ok: boolean; connected: boolean; tools: number }>("/mcpext", {
        name: draft.name,
        url: draft.url,
        description: draft.description,
        headers: draft.headers,
      });
      toast.success(
        r.connected
          ? `«${draft.name}» подключён — ${r.tools} инструментов уже доступны агентам`
          : `«${draft.name}» сохранён, но сервер не ответил — инструменты подтянутся по «Обновить»`,
      );
      setOpen(false);
      setDraft(null);
      setRaw("");
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось подключить");
    } finally {
      setCreating(false);
    }
  };

  const refresh = async (name: string) => {
    setBusy(name);
    try {
      const r = await apiPost<{ connected: boolean; tools: number }>(`/mcpext/${name}/refresh`, {});
      if (r.connected) toast.success(`${name}: ${r.tools} инструментов`);
      else toast.error(`${name}: сервер недоступен`);
      reload();
    } finally {
      setBusy(null);
    }
  };

  const remove = async (m: McpInfo) => {
    setBusy(m.name);
    try {
      await apiDelete(`/mcpext/${m.name}`);
      toast.success(`«${m.name}» отключён`);
      setRemoving(null);
      reload();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex-1 text-xs text-muted-foreground">
          Сторонние MCP-серверы (remote, http): кинь ссылку или конфиг — нейронка разберёт, сервер проверит,
          инструменты сразу появятся у агентов.
        </p>
        <Button size="sm" variant="outline" onClick={() => { setDraft(null); setProbeResult(null); setOpen(true); }}>
          <Plus className="mr-1 h-4 w-4" /> Подключить MCP
        </Button>
      </div>

      {(list ?? []).length === 0 && list !== null && (
        <p className="rounded-xl border border-dashed px-4 py-6 text-center text-xs text-muted-foreground">
          Внешних MCP пока нет
        </p>
      )}
      {(list ?? []).map((m) => {
        const st = STATUS_VIEW[m.status] ?? STATUS_VIEW.unchecked;
        return (
          <div key={m.name} className="flex items-start gap-3 rounded-xl border bg-card px-4 py-3">
            <Cable className={cn("mt-0.5 h-4 w-4 shrink-0", m.status === "ok" ? "text-emerald-500" : "text-muted-foreground")} />
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                {m.name}
                <Badge variant="outline" className={cn("text-[10px]", st.cls)}>
                  {st.label}
                </Badge>
                {m.tools_count > 0 && (
                  <Badge variant="secondary" className="text-[10px]">
                    {m.tools_count} инструментов
                  </Badge>
                )}
              </p>
              <p className="truncate text-xs text-muted-foreground" title={m.url}>
                {m.url}
                {m.description ? ` · ${m.description}` : ""}
              </p>
              {m.last_error && (
                <p className="mt-1 truncate text-xs text-rose-500/80" title={m.last_error}>
                  {m.last_error}
                </p>
              )}
            </div>
            <div className="flex shrink-0 gap-1">
              <Button size="sm" variant="ghost" aria-label="Обновить" disabled={busy === m.name} onClick={() => void refresh(m.name)}>
                {busy === m.name ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              </Button>
              <Button size="sm" variant="ghost" aria-label="Отключить" disabled={busy === m.name} onClick={() => setRemoving(m)}>
                <Trash2 className="h-3.5 w-3.5 text-rose-500" />
              </Button>
            </div>
          </div>
        );
      })}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Подключить MCP</DialogTitle>
          </DialogHeader>
          {!draft ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                Кинь ссылку вида https://…/mcp или вставь JSON-конфиг (mcp.json, claude_desktop_config) —
                нейронка вытащит адрес и заголовки, сервер проверит соединение.
              </p>
              <Textarea
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                placeholder={"https://mcp.example.com/mcp\n\nили JSON:\n{\"mcpServers\": {\"github\": {\"url\": \"…\"}}}"}
                className="min-h-28 font-mono text-xs"
              />
              {draftError && (
                <p className="rounded-lg bg-rose-500/10 px-3 py-2 text-xs leading-relaxed text-rose-500">
                  {draftError}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Нейронка разбирает ~10 секунд. Важно: подключаются remote MCP (streamable http) —
                локальные stdio-конфиги (command/npx) не подходят.
              </p>
              <Button disabled={drafting} onClick={() => void composeDraft()}>
                {drafting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Sparkles className="mr-1 h-4 w-4" />}
                Разобрать с нейронкой
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {draft.summary && (
                <p className="rounded-lg bg-sky-500/10 px-3 py-2 text-xs text-sky-600 dark:text-sky-400">{draft.summary}</p>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs">
                  Имя
                  <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  Описание
                  <Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
                </label>
              </div>
              <label className="flex flex-col gap-1 text-xs">
                Адрес (streamable http)
                <Input value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} className="font-mono text-xs" />
              </label>
              {Object.keys(draft.headers).length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Заголовки: {Object.keys(draft.headers).join(", ")}
                </p>
              )}
              {probeResult && (
                <p className={cn("rounded-lg px-3 py-2 text-xs", probeResult.ok ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-rose-500/10 text-rose-500")}>
                  {probeResult.ok ? `Сервер отвечает: ${probeResult.count} инструментов` : probeResult.error?.slice(0, 160)}
                </p>
              )}
              <DialogFooter>
                <Button variant="outline" disabled={creating || probing} onClick={() => setDraft(null)}>
                  ← Заново
                </Button>
                <Button variant="outline" disabled={probing || creating} onClick={() => void probe()}>
                  {probing ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <PlugZap className="mr-1 h-4 w-4" />}
                  Проверить
                </Button>
                <Button disabled={creating} onClick={() => void create()}>
                  {creating ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plug className="mr-1 h-4 w-4" />}
                  Подключить
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={removing !== null} onOpenChange={(v) => !v && setRemoving(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Отключить «{removing?.name}»?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Инструменты сервера исчезнут у агентов; запись можно добавить заново в любой момент.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRemoving(null)}>
              Отмена
            </Button>
            <Button variant="destructive" onClick={() => removing && void remove(removing)}>
              <Trash2 className="mr-1 h-4 w-4" /> Отключить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
