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


const AGENT_LABEL: Record<string, string> = {
  root: "root · оркестратор",
  quick_reviewer: "быстрый разбор",
  session_tutor: "тьютор урока",
  free_chat: "свободный чат",
  repo_scout: "idea-scout",
};

/** Короткая подпись агента, ведущего разговор (handoff, T-050). */
export function agentLabel(agent: string | null | undefined): string {
  if (!agent) return "";
  return AGENT_LABEL[agent] ?? `агент ${agent}`;
}
