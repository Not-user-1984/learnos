"use client";

/** Код-блок в привычном виде: подпись языка, кнопка «копировать», моноширинно. Mermaid — схемой, без рамки кода. */

import { useState } from "react";
import { Icon } from "@/components/ui/icon";
import { Mermaid } from "./Mermaid";

export function CodeBlock({ language, code, children }: { language?: string; code: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  if (language === "mermaid") {
    return <Mermaid code={code.replace(/\n$/, "")} />;
  }

  const copy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <figure className="not-prose group relative my-5">
      <div className="flex items-center justify-between rounded-t-xl border border-b-0 border-border bg-muted px-4 py-1.5 text-xs text-muted-foreground">
        <span className="font-mono">{language ?? "code"}</span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          aria-label="Скопировать код"
        >
          {copied ? <Icon name="check" size={14} className="text-emerald-500" /> : <Icon name="content_copy" size={14} />}
          {copied ? "скопировано" : "копировать"}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-b-xl border border-zinc-200 bg-zinc-950 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 dark:border-zinc-800">
        {children}
      </pre>
    </figure>
  );
}
