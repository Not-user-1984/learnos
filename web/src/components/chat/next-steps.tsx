"use client";

/** Ряд «что дальше» над композером (B-003): один, контекстный, 0–3 действия.
 *  Скрыт во время стрима и пока у последнего сообщения есть неотвеченные решения —
 *  пользователь сначала отвечает на предложение агента, потом получает подсказки. */

import { Icon } from "@/components/ui/icon";
import { CHAT_SCENARIOS, type ChatScenario } from "@/lib/scenarios";
import type { ChatMessage } from "@/lib/types";

/** Действия фазы сессии: одно основное — «что от меня сейчас нужно». */
const SESSION_ACTIONS: Record<string, { icon: string; label: string; text: string }> = {
  theory: { icon: "help", label: "К вопросам", text: "Теория понятна — переходим к фейнман-вопросам." },
  check: {
    icon: "help",
    label: "Фейнман-вопросы",
    text: "Фейнман: запусти проверку — задай следующий вопрос по пройденному (карточкой ask).",
  },
  practice: { icon: "terminal", label: "Практика", text: "Начинаем практику — дай задание под моё железо." },
  debrief: { icon: "flag", label: "Завершить сессию", text: "Завершаем сессию: сделай разбор и сохрани блок-урок." },
};

const DECISION_TYPES = new Set(["action_offer", "quick_replies"]);

/** У последнего сообщения есть карточка-решение без ответа — подсказки не нужны. */
export function hasPendingDecision(messages: ChatMessage[]): boolean {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") return false;
  return (last.cards ?? []).some((c) => DECISION_TYPES.has(c.type) && !c.status);
}

type NextStepsProps = {
  streaming: boolean;
  messages: ChatMessage[];
  session: { state: string } | null;
  mode: string;
  onSend: (text: string) => void;
  onPrefill: (text: string) => void;
  onStartScenario: (scenario: ChatScenario) => void;
};

export function NextSteps({ streaming, messages, session, mode, onSend, onPrefill, onStartScenario }: NextStepsProps) {
  if (streaming || hasPendingDecision(messages)) return null;

  const items: { icon: string; label: string; run: () => void }[] = [];
  if (session && session.state !== "done" && SESSION_ACTIONS[session.state]) {
    // в сессии — одно основное действие текущей фазы
    const a = SESSION_ACTIONS[session.state];
    items.push({ icon: a.icon, label: a.label, run: () => onSend(a.text) });
  } else if (["root", "free", "quick"].includes(mode)) {
    // вне сессии — сценарии с тем же поведением, что на стартовом экране
    for (const s of CHAT_SCENARIOS) {
      items.push({
        icon: s.icon,
        label: s.label,
        run: () => (s.action.kind === "prefill" ? onPrefill(s.action.text) : onStartScenario(s)),
      });
    }
  }
  if (!items.length) return null;

  return (
    <div className="mx-auto mb-1 flex max-w-3xl flex-wrap gap-2 px-4">
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          onClick={it.run}
          className="inline-flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1.5 text-sm text-primary transition hover:bg-primary/20"
        >
          <Icon name={it.icon} size={16} /> {it.label}
        </button>
      ))}
    </div>
  );
}
