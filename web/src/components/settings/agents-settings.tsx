"use client";

/** Управление агентами: список с раскрытием (промпт/инструменты), конструктор новых, удаление кастомных. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, ChevronDown, ChevronRight, Loader2, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, apiDelete, apiPatch, apiPost } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type PromptInfo = {
  agent: string;
  description: string;
  module: string;
  has_override: boolean;
  custom?: boolean;
  tools?: string[] | null;
};

type PromptDetail = PromptInfo & { content: string };

type ToolInfo = { name: string; description: string; module: string };

type Draft = {
  name: string;
  description: string;
  prompt: string;
  tools: string[];
  summary: string;
  available_tools: ToolInfo[];
};

export function AgentsSettings() {
  const router = useRouter();
  const [agents, setAgents] = useState<PromptInfo[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, PromptDetail>>({});
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);

  const [builderOpen, setBuilderOpen] = useState(false);
  const [brief, setBrief] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [creating, setCreating] = useState(false);

  const [removing, setRemoving] = useState<PromptInfo | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [editing, setEditing] = useState<PromptDetail | null>(null);
  const [editPrompt, setEditPrompt] = useState("");
  const [saving, setSaving] = useState(false);

  const reload = useCallback(() => {
    api<PromptInfo[]>("/tuning/prompts").then(setAgents).catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const toggle = async (agent: string) => {
    if (open === agent) {
      setOpen(null);
      return;
    }
    setOpen(agent);
    if (!detail[agent]) {
      setLoadingDetail(agent);
      try {
        const d = await api<PromptDetail>(`/tuning/prompts/${agent}`);
        setDetail((prev) => ({ ...prev, [agent]: d }));
      } catch {
        toast.error("не удалось загрузить промпт");
      } finally {
        setLoadingDetail(null);
      }
    }
  };

  const composeDraft = async () => {
    if (brief.trim().length < 5) {
      toast.error("опиши подробнее, что должен делать агент");
      return;
    }
    setDrafting(true);
    try {
      const d = await apiPost<Draft>("/tuning/agents/draft", { brief });
      setDraft(d);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "конструктор не сработал");
    } finally {
      setDrafting(false);
    }
  };

  const create = async () => {
    if (!draft) return;
    setCreating(true);
    try {
      await apiPost("/tuning/agents", {
        name: draft.name,
        description: draft.description,
        prompt: draft.prompt,
        tools: draft.tools,
      });
      toast.success(`Агент «${draft.name}» создан — уже доступен в новом разговоре`);
      setBuilderOpen(false);
      setDraft(null);
      setBrief("");
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (a: PromptInfo) => {
    setDeleting(true);
    try {
      await apiDelete(`/tuning/agents/${a.agent}`);
      toast.success(`Агент «${a.agent}» удалён`);
      setRemoving(null);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось удалить");
    } finally {
      setDeleting(false);
    }
  };

  const saveEdit = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await apiPatch(`/tuning/agents/${editing.agent}`, {
        name: editing.agent,
        description: editing.description,
        prompt: editPrompt,
        tools: editing.tools ?? [],
      });
      toast.success("Агент обновлён");
      setEditing(null);
      setDetail((prev) => ({ ...prev, [editing.agent]: { ...editing, content: editPrompt } }));
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось сохранить");
    } finally {
      setSaving(false);
    }
  };

  const tuneInChat = async (a: PromptInfo) => {
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {
        mode: "tuning",
        title: `Настройка: ${a.agent}`,
      });
      router.push(
        `/chat/${conv.uid}?initial=${encodeURIComponent(`Настрой агента ${a.agent}: опиши правку — например, «${a.custom ? "сделай тон мягче" : "отвечай короче"}».`)}`,
      );
    } catch {
      toast.error("не удалось открыть настройку");
    }
  };

  const toggleDraftTool = (name: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      tools: draft.tools.includes(name) ? draft.tools.filter((t) => t !== name) : [...draft.tools, name],
    });
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <p className="flex-1 text-xs text-muted-foreground">
          Клик по агенту — его текущее поведение (промпт и инструменты). Правки — словами через настройщик,
          новые агенты — конструктором.
        </p>
        <Button size="sm" variant="outline" onClick={() => { setDraft(null); setBuilderOpen(true); }}>
          <Plus className="mr-1 h-4 w-4" /> Новый агент
        </Button>
      </div>

      {(agents ?? []).map((a) => (
        <div key={a.agent} className="overflow-hidden rounded-xl border bg-card">
          <button
            onClick={() => void toggle(a.agent)}
            className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left transition hover:bg-accent/40"
          >
            {open === a.agent ? (
              <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                <Bot className="h-3.5 w-3.5 text-violet-500" />
                {a.agent}
                {a.custom && (
                  <Badge className="bg-emerald-500/15 text-[10px] text-emerald-500">мой агент</Badge>
                )}
                {a.has_override && (
                  <Badge variant="secondary" className="text-[10px]">
                    настроен
                  </Badge>
                )}
              </p>
              <p className="text-xs text-muted-foreground">{a.description}</p>
            </div>
          </button>
          {open === a.agent && (
            <div className="border-t bg-background/40 px-4 py-3">
              {loadingDetail === a.agent || !detail[a.agent] ? (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> читаю поведение…
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {(detail[a.agent].tools?.length ?? 0) > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {(detail[a.agent].tools ?? []).map((t) => (
                        <Badge key={t} variant="outline" className="text-[10px] font-mono">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted/60 p-3 text-xs leading-relaxed">
                    {detail[a.agent].content}
                  </pre>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => void tuneInChat(a)}>
                      <Wand2 className="mr-1 h-3.5 w-3.5" /> Помочь настроить
                    </Button>
                    {a.custom && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditing(detail[a.agent]);
                            setEditPrompt(detail[a.agent].content);
                          }}
                        >
                          Изменить
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => setRemoving(a)}>
                          <Trash2 className="mr-1 h-3.5 w-3.5" /> Удалить
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}

      {/* конструктор нового агента */}
      <Dialog open={builderOpen} onOpenChange={setBuilderOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Новый агент</DialogTitle>
          </DialogHeader>
          {!draft ? (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                Опиши словами, какого помощника хочешь — нейронка соберёт драфт: имя, поведение и инструменты.
                Созданный агент сразу появится в списке и в «Новом разговоре».
              </p>
              <Textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="Например: агент-ops, который знает мой хомлаб, подсказывает команды и отправляет конспекты в Telegram"
                className="min-h-24"
              />
              <Button disabled={drafting} onClick={() => void composeDraft()}>
                {drafting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Sparkles className="mr-1 h-4 w-4" />}
                Собрать с нейронкой
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {draft.summary && (
                <p className="rounded-lg bg-sky-500/10 px-3 py-2 text-xs text-sky-600 dark:text-sky-400">
                  {draft.summary}
                </p>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs">
                  Имя (латиницей)
                  <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1 text-xs">
                  Описание
                  <Input
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                </label>
              </div>
              <label className="flex flex-col gap-1 text-xs">
                Поведение (системный промпт)
                <Textarea
                  value={draft.prompt}
                  onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
                  className="min-h-40 font-mono text-xs"
                />
              </label>
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">Инструменты</p>
                <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
                  {draft.available_tools.map((t) => (
                    <button
                      key={t.name}
                      onClick={() => toggleDraftTool(t.name)}
                      title={t.description}
                      className={cn(
                        "rounded-full border px-2.5 py-1 font-mono text-[10px] transition",
                        draft.tools.includes(t.name)
                          ? "border-violet-500/60 bg-violet-500/15 text-violet-600 dark:text-violet-300"
                          : "text-muted-foreground hover:bg-accent",
                      )}
                    >
                      {t.name}
                    </button>
                  ))}
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" disabled={creating} onClick={() => setDraft(null)}>
                  ← Заново
                </Button>
                <Button disabled={creating} onClick={() => void create()}>
                  {creating ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Bot className="mr-1 h-4 w-4" />}
                  Создать агента
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* редактор кастомного агента */}
      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Агент «{editing?.agent}»</DialogTitle>
          </DialogHeader>
          <Textarea
            value={editPrompt}
            onChange={(e) => setEditPrompt(e.target.value)}
            className="min-h-60 font-mono text-xs"
          />
          <DialogFooter>
            <Button variant="outline" disabled={saving} onClick={() => setEditing(null)}>
              Отмена
            </Button>
            <Button disabled={saving} onClick={() => void saveEdit()}>
              {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
              Сохранить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* подтверждение удаления */}
      <Dialog open={removing !== null} onOpenChange={(v) => !v && setRemoving(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Удалить агента?</DialogTitle>
          </DialogHeader>
          {removing && (
            <>
              <p className="text-sm font-medium">{removing.agent}</p>
              <p className="text-sm text-muted-foreground">
                Агент исчезнет из системы и «Нового разговора». Встроенные агенты защищены от удаления.
              </p>
              <DialogFooter>
                <Button variant="outline" disabled={deleting} onClick={() => setRemoving(null)}>
                  Отмена
                </Button>
                <Button variant="destructive" disabled={deleting} onClick={() => void remove(removing)}>
                  {deleting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1 h-4 w-4" />}
                  Удалить
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
