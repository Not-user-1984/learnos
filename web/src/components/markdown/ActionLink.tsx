"use client";

/** Ссылка с меню действий: у YouTube- и PDF-ссылок клик по тексту и кнопка-шеврон
 *  открывают попап («Открыть в новой вкладке», «Добавить в источники», «Быстрый
 *  разбор» / «Изучить книгу» — новый root-разговор со ссылкой первым сообщением).
 *  Обычные http(s)-ссылки рендерятся как раньше — навигация без меню. */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Icon } from "@/components/ui/icon";
import { apiPost } from "@/lib/api";

// YouTube-видео (youtu.be/<id>, watch?v=, shorts, live) — то же семейство ссылок,
// что распознаёт претрекер чата в server/app/modules/chat/domain.py
const YOUTUBE_RE =
  /^https?:\/\/(?:www\.|m\.)?(?:youtu\.be\/[\w-]{11,}|youtube\.com\/(?:watch\?\S*?v=[\w-]{11,}|shorts\/[\w-]{11,}|live\/[\w-]{11,}))/;

export type ActionLinkKind = "youtube" | "pdf" | null;

/** Тип ссылки для меню действий: YouTube-ролик, PDF или обычная страница. */
export function linkKind(href: string): ActionLinkKind {
  if (!/^https?:\/\//i.test(href)) return null;
  if (YOUTUBE_RE.test(href)) return "youtube";
  try {
    if (new URL(href).pathname.toLowerCase().endsWith(".pdf")) return "pdf";
  } catch {
    return null;
  }
  return null;
}

const KIND_TOAST: Record<string, string> = {
  book: " — в Библиотеке, нарезка глав пошла",
  video: " — видео в Библиотеке, транскрипт загружается",
  web: " — статья в Библиотеке, обрабатывается",
};

/** Действия над ссылкой в markdown-рендере. */
export function ActionLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const url = typeof href === "string" ? href : "";
  const kind = linkKind(url);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // клик мимо и Esc закрывают меню; фокус уходит обратно на кнопку
  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onDown = (e: PointerEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  if (!kind) {
    return <a href={url}>{children}</a>;
  }

  const close = () => setOpen(false);

  /** Добавить материал в Библиотеку одним действием (from-url); обработка — job. */
  const addToLibrary = async () => {
    setBusy(true);
    try {
      const out = await apiPost<{ title: string; kind: string }>("/sources/from-url", { url });
      toast.success(`«${out.title}»${KIND_TOAST[out.kind] ?? " — добавлено в Библиотеку"}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось добавить в Библиотеку");
    } finally {
      setBusy(false);
      close();
    }
  };

  /** Новый root-разговор со ссылкой первым сообщением: агент сразу начнёт разбор. */
  const startConversation = async () => {
    setBusy(true);
    try {
      const conv = await apiPost<{ uid: string }>("/conversations", {});
      const intent = kind === "pdf" ? "study" : "review";
      router.push(`/chat/${conv.uid}?initial=${encodeURIComponent(url)}&intent=${intent}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось создать разговор");
      setBusy(false);
    }
  };

  const items = [
    { icon: "open_in_new", label: "Открыть в новой вкладке", run: () => window.open(url, "_blank", "noopener") },
    { icon: "library_add", label: "Добавить в источники", run: () => void addToLibrary() },
    kind === "pdf"
      ? { icon: "auto_stories", label: "Изучить книгу", run: () => void startConversation() }
      : { icon: "bolt", label: "Быстрый разбор", run: () => void startConversation() },
  ];

  /** Клавиатура в меню: стрелки по пунктам, Esc закрывает и возвращает фокус. */
  const onMenuKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      triggerRef.current?.focus();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const nodes = [...(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
    if (!nodes.length) return;
    const idx = nodes.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? (idx + 1) % nodes.length : (idx - 1 + nodes.length) % nodes.length;
    nodes[next].focus();
  };

  return (
    <span ref={boxRef} className="relative inline-flex items-center gap-0.5 align-baseline">
      {/* клик по тексту ссылки открывает меню действий (BUG-002): «Открыть в новой
          вкладке» — первый пункт; модификаторные клики (Ctrl/Cmd/Shift) идут нативно */}
      <a
        href={url}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          setOpen(true);
        }}
      >
        {children}
      </a>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Действия со ссылкой"
        onClick={() => setOpen((v) => !v)}
        className="rounded p-0.5 text-muted-foreground transition hover:bg-accent hover:text-primary"
      >
        <Icon name="expand_more" size={14} />
      </button>
      {open && (
        <div
          ref={menuRef}
          role="menu"
          onKeyDown={onMenuKey}
          className="absolute left-0 top-full z-50 mt-1 w-56 max-w-[calc(100vw-2rem)] rounded-xl border bg-card p-1 shadow-lg"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={item.run}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-foreground transition hover:bg-accent disabled:opacity-60"
            >
              <Icon name={item.icon} size={16} className="shrink-0 text-primary" />
              {busy ? <span className="inline-flex items-center gap-2"><Icon name="progress_activity" size={13} className="animate-spin" />{item.label}</span> : item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
