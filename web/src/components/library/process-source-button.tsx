"use client";

/** Кнопка (повторной) обработки источника: failed → «Запустить», processing → «Повторить» (R-10). */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { apiPost, ApiError } from "@/lib/api";

type Props = {
  sourceUid: string;
  status: string;
};

const LABELS: Record<string, { label: string; force: boolean }> = {
  failed: { label: "Запустить обработку", force: false },
  processing: { label: "Повторить обработку", force: true },
};

export function ProcessSourceButton({ sourceUid, status }: Props) {
  const conf = LABELS[status];
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  if (!conf) return null;

  const run = () => {
    setError(null);
    startTransition(async () => {
      try {
        await apiPost(`/sources/${sourceUid}/process?force=${conf.force}`, {});
        router.refresh();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "не удалось запустить обработку");
      }
    });
  };

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className="rounded-md border px-2.5 py-1.5 text-sm hover:bg-accent disabled:opacity-50"
      >
        {pending ? "Запускаю…" : conf.label}
      </button>
      {error && <span className="max-w-xs text-right text-xs text-destructive">{error}</span>}
    </span>
  );
}
