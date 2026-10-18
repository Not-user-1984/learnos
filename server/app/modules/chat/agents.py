"""Агенты-тьюторы чата: free_chat, quick_reviewer, session_tutor (заголовки делаются ролью fast)."""

from pathlib import Path

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"

free_chat = AgentSpec(
    name="free_chat",
    description=(
        "Свободный чат: отвечает, ищет по базе знаний, правит блоки, сохраняет конспекты, "
        "анализирует GitHub-репозитории на идеи."
    ),
    prompt_path=AGENTS_DIR / "free_chat" / "prompt.md",
    tools=frozenset(
        {
            "search",
            "get_block",
            "list_blocks",
            "update_block",
            "save_note",
            "list_sources",
            "get_source",
            "read_chapter",
            "get_profile",
            "research_sources",
            "web_search",
            "academic_search",
            "web_read",
            "list_chapters",
            "github_repo",
            "github_file",
            "save_idea_report",
            "send_telegram_text",
            "send_block_to_telegram",
            "send_chapter_to_telegram",
        }
    ),
    max_steps=30,
)

quick_reviewer = AgentSpec(
    name="quick_reviewer",
    description=(
        "Быстрый разбор источника: резюме главы, ключевые понятия, что применимо, вопросы; итог — конспект."
    ),
    prompt_path=AGENTS_DIR / "quick_reviewer" / "prompt.md",
    tools=frozenset(
        {
            "get_source",
            "list_chapters",
            "read_chapter",
            "search",
            "web_search",
            "academic_search",
            "web_read",
            "preview_note",
            "save_note",
            "update_block",
            "get_profile",
            "get_block",
            "send_telegram_text",
            "send_block_to_telegram",
            "send_chapter_to_telegram",
        }
    ),
    # длинные видео: транскрипт листается десятками порций read_chapter
    max_steps=40,
)

session_tutor = AgentSpec(
    name="session_tutor",
    description=(
        "Ведёт сессию-урок: теория → фейнман-вопросы → практика под железо → разбор; итог — блок-урок."
    ),
    prompt_path=AGENTS_DIR / "session_tutor" / "prompt.md",
    tools=frozenset(
        {
            "get_session_state",
            "advance",
            "read_chapter",
            "list_chapters",
            "web_search",
            "academic_search",
            "web_read",
            "practice_step",
            "finish_session",
            "search",
            "get_block",
            "get_profile",
            "start_session",
            "send_telegram_text",
            "send_block_to_telegram",
            "send_chapter_to_telegram",
        }
    ),
    max_steps=40,
)


repo_scout = AgentSpec(
    name="repo_scout",
    description=(
        "Idea-scout: реверс-инжиниринг GitHub-репозиториев — ищет приёмы, полезные LearnOS, "
        "без переписывания архитектуры; отчёт в чат + data/ideas + короткое резюме в Telegram."
    ),
    prompt_path=AGENTS_DIR / "repo_scout" / "prompt.md",
    tools=frozenset(
        {
            "github_repo",
            "github_file",
            "save_idea_report",
            "send_telegram_text",
            "web_search",
            "web_read",
        }
    ),
    max_steps=30,
)


def register_agents(c) -> None:
    """Зарегистрировать тьюторов чата."""
    registry: AgentRegistry = c.agent_registry
    registry.register(free_chat)
    registry.register(quick_reviewer)
    registry.register(session_tutor)
    registry.register(repo_scout)
