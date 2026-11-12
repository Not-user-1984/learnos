"use client";

/** Предложения агентов (B-010): задачи-идеи, ветки agent/*, правки промптов — принять/отклонить. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/icon";
import { toast } from "sonner";
import { api, apiPost } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type Proposals = {
  tasks: {
    id: string;
    title: string;
    from: string;
    path: string;
    source?: "git" | "data";
    text?: string;
  }[];
  branches: { branch?: string; commit?: string; summary?: string; diffstat?: string }[];
  prompt_changes: { id: number; agent?: string; summary?: string }[];
};

export default function ProposalsPage() {
  const [data, setData] = useState<Proposals | null>(null);

  const load = () => api<Proposals>("/proposals").then(setData).catch(() => setData(null));
  useEffect(() => {
    void load();
  }, []);

  const decide = async (
    kind: string,
    ref: string,
    decision: "accepted" | "rejected",
    task?: Proposals["tasks"][number],
  ) => {
    try {
      const out = await apiPost<{ pr_url?: string | null; compare_url?: string | null; task_text?: string }>(
        `/proposals/${kind}/${ref}/decide`,
        { decision },
      );
      if (decision === "accepted") {
        if (kind === "branch") {
          toast.success(out?.pr_url ? `Ветка отправлена, PR: ${out.pr_url}` : "Ветка отправлена");
        } else if (kind === "task") {
          // задача из data (git-дерево прода read-only): текст — в буфер, человек
          // переносит файл в бэклог сам (B-011)
          const text = out?.task_text ?? task?.text;
          if (text) {
            try {
              await navigator.clipboard.writeText(text);
              toast.success("Принято: текст задачи скопирован — вставь файлом в task_ai/tasks");
            } catch {
              toast.success("Принято: скопируй текст задачи из карточки в task_ai/tasks");
            }
          } else {
            toast.success("Принято: файл задачи уже в task_ai/tasks");
          }
        } else {
          toast.success("Принято");
        }
      } else {
        toast.success("Отклонено");
      }
      void load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось");
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <header className="mb-5">
        <h1 className="text-xl font-bold">Предложения агентов</h1>
        <p className="text-sm text-muted-foreground">
          Идеи → задачи, ветки agent/* с зелёными проверками, правки промптов. Мердж в main — всегда за тобой.
        </p>
      </header>

      {data === null ? (
        <p className="text-sm text-muted-foreground">…</p>
      ) : data.tasks.length + data.branches.length + data.prompt_changes.length === 0 ? (
        <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Новых предложений нет. Включи расписания в настройках — auditor и repo_scout будут искать их сами.
        </p>
      ) : (
        <div className="flex max-w-3xl flex-col gap-6">
          {data.tasks.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Задачи-идеи</h2>
              <ul className="flex flex-col gap-2">
                {data.tasks.map((t) => (
                  <li key={t.id} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{t.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {t.id} · {t.from}
                        {t.source === "data" && " · вне git (прод)"}
                      </p>
                    </div>
                    {t.source === "data" && t.text && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          void navigator.clipboard
                            .writeText(t.text ?? "")
                            .then(() => toast.success("Текст задачи скопирован"))
                            .catch(() => toast.error("Не удалось скопировать"));
                        }}
                      >
                        <Icon name="content_copy" size={15} className="mr-1" /> Текст
                      </Button>
                    )}
                    <Button size="sm" onClick={() => void decide("task", t.id, "accepted", t)}>
                      <Icon name="check" size={15} className="mr-1" /> Взять в работу
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void decide("task", t.id, "rejected")}>
                      <Icon name="close" size={15} className="mr-1" /> Отклонить
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.branches.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Ветки агентов</h2>
              <ul className="flex flex-col gap-2">
                {data.branches.map((b) => (
                  <li key={b.branch} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-sm font-medium">{b.branch}</p>
                      {b.summary && <p className="mt-1 text-sm text-muted-foreground">{b.summary}</p>}
                      {b.diffstat && <pre className="mt-1 text-xs text-muted-foreground">{b.diffstat}</pre>}
                    </div>
                    <Badge variant="outline">проверки зелёные</Badge>
                    <Button size="sm" onClick={() => void decide("branch", b.branch ?? "", "accepted")}>
                      <Icon name="check" size={15} className="mr-1" /> Push + PR
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void decide("branch", b.branch ?? "", "rejected")}>
                      <Icon name="close" size={15} className="mr-1" /> Удалить
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.prompt_changes.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted-foreground">Правки промптов</h2>
              <ul className="flex flex-col gap-2">
                {data.prompt_changes.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{c.summary}</p>
                      <p className="text-xs text-muted-foreground">агент: {c.agent}</p>
                    </div>
                    <Link href="/chat" className="text-sm text-primary hover:underline">
                      открыть в чате →
                    </Link>
                    <Button size="sm" onClick={() => void decide("prompt", String(c.id), "accepted")}>
                      <Icon name="check" size={15} className="mr-1" /> Принять
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => void decide("prompt", String(c.id), "rejected")}>
                      <Icon name="close" size={15} className="mr-1" /> Отклонить
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
