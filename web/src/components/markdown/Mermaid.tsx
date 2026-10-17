"use client";

/** Рендер mermaid-схем с темой из next-themes. Битые схемы сначала чиним
 *  (кавычки в подписях, лишний узел после стрелки) и только потом сдаёмся. */

import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

/** Символы, ломающие парсер mermaid 12 (эмодзи, пиктограммы, текстовые стрелки). */
const MERMAID_UNSAFE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}]/gu;

function sanitizeMermaid(code: string): string {
  return code
    .replace(/^```(mermaid)?\s*\n?/, "")
    .replace(/\n?```\s*$/, "")
    .replace(MERMAID_UNSAFE, "")
    .replace(/ {2,}/g, " ");
}

/** Строки, где скобки трогать нельзя (директивы и заголовок диаграммы). */
const MERMAID_SKIP_LINE = /^\s*(classDef|class|style|linkStyle|click|subgraph|end|direction|flowchart|graph)\b/i;

/** Подписи узлов и рёбер — в двойные кавычки: M[Команда C] → M["Команда C"].
 *  Чинит самый частый слом LLM-схем: микс кириллицы/латыни/цифр без кавычек. */
function quoteLabels(line: string): string {
  return line
    .replace(/\[([^\]["]*)\]/g, (m, t: string) => (t.includes('"') ? m : `["${t.trim()}"]`))
    .replace(/\{([^}"]*)\}/g, (m, t: string) => (t.includes('"') ? m : `{"${t.trim()}"}`))
    .replace(/\(([^()"\\]*)\)/g, (m, t: string) => (t.includes('"') || !t.trim() ? m : `("${t.trim()}")`))
    .replace(/\|([^|"]+)\|/g, (m, t: string) => (t.includes('"') ? m : `|"${t.trim()}"|`));
}

/** `A --> M C1[Подпись]` — «прилипший» узел после стрелки выносим на свою строку. */
const NODE_AHEAD = /([^\s>=.-])\s+(?=[A-Za-zА-Яа-яЁё0-9_-]*\s*[\[({])/gu;

/** subgraph: название в кавычки, при пробелах без id — генерируем id. */
function fixSubgraph(line: string, n: number): string {
  const m = /^\s*subgraph\s+(.*?)\s*$/i.exec(line);
  if (!m) return line;
  const bracket = /^([A-Za-z0-9_-]+)\s*[\[({](.*)[\])}]\s*$/.exec(m[1]);
  if (bracket) return `subgraph ${bracket[1]}["${bracket[2].replace(/^"|"$/g, "").trim()}"]`;
  return `subgraph sg${n}["${m[1].replace(/"/g, "").trim()}"]`;
}

function repairLines(code: string, repair: (line: string) => string): string {
  let sg = 0;
  return code
    .split("\n")
    .map((line) => {
      if (/^\s*subgraph\b/i.test(line)) return fixSubgraph(line, ++sg);
      return MERMAID_SKIP_LINE.test(line) ? line : repair(line);
    })
    .join("\n");
}

/** Варианты от простого к агрессивному: оригинал → кавычки → кавычки + разбор строк. */
function mermaidVariants(code: string): string[] {
  const base = sanitizeMermaid(code);
  const head = base.split("\n").find((l) => l.trim());
  const variants = [base];
  // чиним только flowchart/graph: у sequenceDiagram и прочих другая грамматика
  if (head && /^(flowchart|graph)\b/i.test(head.trim())) {
    const quoted = repairLines(base, quoteLabels);
    variants.push(quoted, repairLines(quoted, (l) => l.replace(NODE_AHEAD, "$1\n")));
  }
  return [...new Set(variants)];
}

export function Mermaid({ code }: { code: string }) {
  const { resolvedTheme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  // схема, которую не удалось отрисовать; новый code сбрасывает показ автоматически
  const [failedFor, setFailedFor] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("mermaid").then(async (mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: resolvedTheme === "dark" ? "dark" : "default",
      });
      const baseId = `mmd-${Math.random().toString(36).slice(2)}`;
      const variants = mermaidVariants(code);
      for (let i = 0; i < variants.length; i++) {
        try {
          const { svg } = await mermaid.render(`${baseId}-${i}`, variants[i]);
          if (!cancelled && ref.current) ref.current.innerHTML = svg;
          return;
        } catch {
          // пробуем следующий, более ремонтный вариант
        }
      }
      if (!cancelled) setFailedFor(code);
    });
    return () => {
      cancelled = true;
    };
  }, [code, resolvedTheme]);

  if (failedFor === code) {
    return (
      <div className="my-5 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
        <p className="mb-2 font-medium text-amber-600 dark:text-amber-400">схема не отрисовалась</p>
        <pre className="overflow-x-auto text-xs opacity-80">{code}</pre>
      </div>
    );
  }
  return (
    <div className="not-prose my-6 flex w-full justify-center overflow-x-auto rounded-xl border bg-card p-6">
      <div ref={ref} className="min-w-0 flex-1 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" />
    </div>
  );
}
