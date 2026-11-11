/** Сценарии быстрого входа (B-003): единый источник для стартового экрана чата
 *  и ряда «что дальше» (NextSteps) — одна надпись = одно поведение. */

export type ScenarioAction =
  | { kind: "prefill"; text: string }
  | { kind: "new-conversation"; initial: string; intent?: string };

export type ChatScenario = {
  id: string;
  icon: string;
  label: string;
  action: ScenarioAction;
};

export const CHAT_SCENARIOS: ChatScenario[] = [
  {
    id: "reinforce",
    icon: "track_changes",
    label: "Закрепить пройденное",
    action: { kind: "new-conversation", initial: "Закрепим пройденное", intent: "reinforce" },
  },
  { id: "note", icon: "edit_note", label: "Конспект", action: { kind: "prefill", text: "Конспект: " } },
  {
    id: "course",
    icon: "school",
    label: "Собрать курс",
    action: { kind: "prefill", text: "Собери курс по теме: " },
  },
];
