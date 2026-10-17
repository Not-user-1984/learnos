/** Общие подписи и эмодзи для UI: источники и режимы чата — единое место правды. */

export function kindEmoji(kind: string): string {
  return kind === "book" ? "📕" : kind === "video" ? "🎬" : "🌐";
}

export const MODE_LABEL: Record<string, string> = {
  free: "свободный",
  quick: "быстрый разбор",
  session: "сессия-урок",
  tuning: "настройка агентов",
};

export function modeEmoji(mode: string): string {
  return mode === "quick" ? "⚡" : mode === "session" ? "🎓" : mode === "tuning" ? "⚙️" : "💬";
}
