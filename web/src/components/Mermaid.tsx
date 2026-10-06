"use client";

import { useEffect, useId, useState } from "react";
import mermaid from "mermaid";

export function Mermaid({ code }: { code: string }) {
  const [svg, setSvg] = useState("");
  const [err, setErr] = useState("");
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");

  useEffect(() => {
    let alive = true;
    mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });
    mermaid
      .render(`mermaid-${id}`, code)
      .then(
        (r) => {
          if (alive) {
            setSvg(r.svg);
            setErr("");
          }
        },
        (e: unknown) => {
          if (alive) setErr(String(e));
        },
      );
    return () => {
      alive = false;
    };
  }, [code, id]);

  if (err) return <pre className="my-4 rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-xs text-red-300">{err}</pre>;
  if (!svg) return <div className="my-4 text-sm opacity-40">рендер схемы…</div>;
  return (
    <div
      className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/40 p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
