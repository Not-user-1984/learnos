"use client";

/** Код-блок в привычном виде: подпись языка, кнопка «копировать», моноширинно. Mermaid — схемой, без рамки кода. */

import { useState } from "react";
import { Check, ClipboardCopy } from "lucide-react";
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
      <div className="flex items-center justify-between rounded-t-xl border border-b-0 border-zinc-200 bg-zinc-100 px-4 py-1.5 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        <span className="font-mono">{language ?? "code"}</span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          aria-label="Скопировать код"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <ClipboardCopy className="h-3.5 w-3.5" />}
          {copied ? "скопировано" : "копировать"}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-b-xl border border-zinc-200 bg-zinc-950 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 dark:border-zinc-800">
        {children}
      </pre>
    </figure>
  );
}
