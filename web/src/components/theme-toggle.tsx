"use client";

/** Переключатель тем: тёмная → пергамент → светлая (циклом). */

import { useSyncExternalStore } from "react";
import { Icon } from "@/components/ui/icon";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

const NEXT: Record<string, string> = { dark: "parchment", parchment: "light", light: "dark" };
const GLYPH: Record<string, string> = { dark: "dark_mode", parchment: "auto_stories", light: "light_mode" };
const TITLE: Record<string, string> = {
  dark: "Тёмная → Пергамент",
  parchment: "Пергамент → Светлая",
  light: "Светлая → Тёмная",
};

const noopSubscribe = () => () => {};
/** «Мы на клиенте»: до монтирования иконка детерминирована — resolvedTheme на
 * сервере нет, а на клиенте он уже из localStorage; рендер «по теме» здесь
 * ломал гидратацию (текст глифа не совпадал, оверлей дев-режима, ревью B-011). */
const useMounted = () => useSyncExternalStore(noopSubscribe, () => true, () => false);

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const current = mounted ? (resolvedTheme ?? "dark") : "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Сменить тему"
      title={TITLE[current] ?? "Сменить тему"}
      onClick={() => setTheme(NEXT[current] ?? "parchment")}
    >
      <Icon name={GLYPH[current] ?? "dark_mode"} size={20} filled />
    </Button>
  );
}
