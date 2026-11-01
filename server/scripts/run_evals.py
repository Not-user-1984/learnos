"""Раннер eval-сценариев на живой модели (T-050 Э6, раздел F аудита).

Запуск: cd server && sec exec ZAI_API_KEY -- uv run python scripts/run_evals.py [фильтр-имя]

Сценарии — tests/evals/*.yaml (формат — см. README там). Каждый прогон:
живой LLM, реальный реестр инструментов (без сетевых вызовов в expect —
контракты поведения, не факты интернета). Итог — таблица ✓/✗ и код выхода.
"""

import asyncio
import sys
from pathlib import Path

import yaml

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

EVALS_DIR = SERVER_DIR / "tests" / "evals"


def load_scenarios(filter_name: str | None = None) -> list[dict]:
    out = []
    for path in sorted(EVALS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if filter_name and filter_name not in data["name"]:
            continue
        out.append(data)
    return out


async def run_one(scenario: dict, container) -> dict:
    """Прогон одного сценария: события агента → проверка expect."""
    from app.agent.spec import AgentContext
    from app.llm.types import Message

    spec = container.agent_registry.get(scenario["agent"])
    ctx = AgentContext(system_extra=scenario.get("system_extra") or None)
    called: list[str] = []
    cards: list[str] = []
    text_parts: list[str] = []
    async for ev in container.agent_runtime.run(spec, ctx, [Message(role="user", content=scenario["user"])]):
        if ev.type == "tool_start":
            called.append(ev.name)
        elif ev.type == "card" and ev.card:
            cards.append(ev.card.get("type", "?"))
        elif ev.type == "text":
            text_parts.append(ev.text)
    text = "".join(text_parts)

    exp = scenario.get("expect") or {}
    problems: list[str] = []
    if exp.get("tools_any") and not set(exp["tools_any"]) & set(called):
        problems.append(f"не вызван ни один из {exp['tools_any']} (было: {called})")
    if set(exp.get("tools_none") or []) & set(called):
        problems.append(f"вызван запрещённый: {set(exp['tools_none']) & set(called)}")
    if exp.get("cards_any") and not set(exp["cards_any"]) & set(cards):
        problems.append(f"нет карточки из {exp['cards_any']} (были: {cards})")
    for frag in exp.get("text_contains") or []:
        if frag not in text:
            problems.append(f"в тексте нет {frag!r}")
    for frag in exp.get("text_not_contains") or []:
        if frag in text:
            problems.append(f"в тексте есть запрещённое {frag!r}")
    return {"name": scenario["name"], "ok": not problems, "problems": problems, "tools": called}


async def main() -> int:
    from app.bootstrap import build_container
    from app.kernel.config import get_settings

    filter_name = sys.argv[1] if len(sys.argv) > 1 else None
    scenarios = load_scenarios(filter_name)
    if not scenarios:
        print(f"сценариев не найдено ({EVALS_DIR}, фильтр: {filter_name!r})")
        return 2

    get_settings.cache_clear()
    container = build_container(get_settings())
    failed = 0
    for scenario in scenarios:
        result = await run_one(scenario, container)
        mark = "✓" if result["ok"] else "✗"
        print(f"{mark} {result['name']}  [{', '.join(result['tools']) or 'без инструментов'}]")
        for problem in result["problems"]:
            print(f"    — {problem}")
        failed += 0 if result["ok"] else 1
    print(f"\n{len(scenarios) - failed}/{len(scenarios)} прошло")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
