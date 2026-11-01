"""Линтер «промпт ↔ инструменты» (R-04): промпт не должен звать инструменты,

которых у агента нет — иначе модель зовёт unknown_tool и поток ломается.
Проверяются prompt.md всех зарегистрированных агентов и тексты директив/хинтов,
вставляемые в system_extra/user-сообщение (INTENT_DIRECTIVES, RESEARCH_DIRECTIVE,
хинты претрекера), против инструментов root/free_chat.
"""

import re

from app.modules.chat.service import INTENT_DIRECTIVES, RESEARCH_DIRECTIVE

# слова в бэктиках, которые заведомо не инструменты: поля карточек, параметры,
# mermaid, примеры имён агентов в промптах тюнеров
NOT_TOOLS = {
    "applicable",
    "chapter",
    "code_reviewer",
    "concepts",
    "description",
    "flowchart",
    "front_matter",
    "github",
    "homelab_helper",
    "instructions",
    "key_points",
    "media",
    "my_tools",
    "name",
    "next_offset",
    "notion",
    "number",
    "params",
    "print",
    "questions",
    "return",
    "title",
    "appendix",
    "command",
}
_BACKTICK = re.compile(r"`([a-z][a-z0-9_]{1,})`")


def _mentioned(text: str) -> set[str]:
    return set(_BACKTICK.findall(text))


def test_agent_prompts_mention_only_available_tools(container):
    """Каждый промпт зовёт только инструменты агента (или не-инструменты вовсе)."""
    registry = container.agent_registry
    all_tool_names = {t.name for t in container.tools.all()}
    agents = registry.all()
    agent_names = {a.name for a in agents}
    problems: list[str] = []

    for spec in agents:
        if spec.prompt_path is None:
            continue
        prompt = spec.prompt_path.read_text(encoding="utf-8")
        available = set(spec.tools)
        for ident in sorted(_mentioned(prompt)):
            if ident in available or ident in NOT_TOOLS or ident in agent_names:
                continue
            kind = "нет у агента" if ident in all_tool_names else "не существует"
            problems.append(f"{spec.name}: `{ident}` ({kind})")

    assert not problems, "промпты зовут недоступные инструменты:\n" + "\n".join(problems)


def test_directives_mention_only_root_tools(container):
    """Директивы интентов/ресёрча и хинты претрекера — против инструментов root/free_chat."""
    from app.modules.chat.domain import _HINTS  # noqa: SLF001 — тест линтера

    registry = container.agent_registry
    allowed = set(registry.get("root").tools) | set(registry.get("free_chat").tools)

    texts: dict[str, str] = {"RESEARCH_DIRECTIVE": RESEARCH_DIRECTIVE}
    texts.update({f"intent:{key}": value for key, value in INTENT_DIRECTIVES.items()})
    import inspect

    for key, hint in _HINTS.items():
        # у хинтов разные сигнатуры (url / arxiv / doi); вызываем по числу аргументов
        argc = len(inspect.signature(hint).parameters)
        args = ("https://example.com/x", "arXiv:2501.00001", "10.1000/x")[:argc]
        texts[f"hint:{key}"] = hint(*args)

    problems = [
        f"{src}: `{ident}`"
        for src, text in texts.items()
        for ident in sorted(_mentioned(text))
        if ident not in allowed and ident not in NOT_TOOLS
    ]
    assert not problems, "директивы/хинты зовут недоступные root/free_chat инструменты:\n" + "\n".join(
        problems
    )
