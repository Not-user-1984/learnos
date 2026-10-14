"use client";

/** Рендер mermaid-схем с темой из next-themes; при ошибке — исходник с плашкой. */

import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";

export function Mermaid({ code }: { code: string }) {
  const { resolvedTheme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: resolvedTheme === "dark" ? "dark" : "default",
      });
      const id = `mmd-${Math.random().toString(36).slice(2)}`;
      mermaid
        .render(id, code)
        .then(({ svg }) => {
          if (!cancelled && ref.current) ref.current.innerHTML = svg;
        })
        .catch((e: unknown) => {
          if (!cancelled) setError(String(e));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [code, resolvedTheme]);

  if (error) {
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
