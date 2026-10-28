/** Общие подписи и эмодзи для UI: источники и режимы чата — единое место правды. */

export function kindIcon(kind: string): string {
  return kind === "book" ? "menu_book" : kind === "video" ? "movie" : "public";
}

export const MODE_LABEL: Record<string, string> = {
  root: "разговор",
  free: "свободный",
  quick: "быстрый разбор",
  session: "сессия-урок",
  tuning: "настройка агентов",
};

export function modeLabel(mode: string): string {
  if (mode.startsWith("agent:")) return `агент ${mode.slice(6)}`;
  return MODE_LABEL[mode] ?? mode;
}

export function modeIcon(mode: string): string {
  if (mode.startsWith("agent:")) return "smart_toy";
  if (mode === "root") return "hub";
  return mode === "quick" ? "bolt" : mode === "session" ? "school" : mode === "tuning" ? "tune" : "chat";
}
