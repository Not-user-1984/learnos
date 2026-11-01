"""Агенты-тьюторы чата: free_chat, quick_reviewer, session_tutor (заголовки делаются ролью fast)."""

from dataclasses import replace
from pathlib import Path

from ...agent.registry import AgentRegistry
from ...agent.spec import AgentSpec

AGENTS_DIR = Path(__file__).parent / "agents"

# инструменты ведения сессии-урока: root получает их, чтобы вести сессию,
# созданную по интенту «session» (сессия привязана к разговору)
SESSION_TOOLS = frozenset({"start_session", "advance", "practice_step", "finish_session"})

# библиотечный цикл «предложил → согласие → добавил → обработал»: без них промпты
# и хинты претрекера посылают агента вызывать несуществующие для него инструменты (R-04)
LIBRARY_TOOLS = frozenset({"add_source", "process_source", "get_job"})

# сценарии единого входа, которые root ведёт сам: превью конспекта (апрув перед
# записью), активность-разбор по источнику, сборка курса из найденного
ENTRY_TOOLS = frozenset(
    {"preview_note", "start_activity", "create_course", "add_course_item", "list_courses"}
)

# инструменты, двигающие курсор книги (активность разговора): после них статус-бар
# быстрого разбора обновляется событием review_progress
REVIEW_TOOLS = frozenset({"mark_chapter_done", "finish_session"})

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
            "youtube_search",
            "web_read",
            "list_chapters",
            "github_repo",
            "github_file",
            "save_idea_report",
            "send_telegram_text",
            "send_block_to_telegram",
            "send_chapter_to_telegram",
            "offer_action",
            "offer_replies",
            "save_skill",
        }
    )
    | LIBRARY_TOOLS
    | {"preview_note"},
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
            "youtube_search",
            "web_read",
            "preview_note",
            "save_note",
            "update_block",
            "get_profile",
            "get_block",
            "mark_chapter_done",
            "offer_replies",
            "show_chapter_review",
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
            "youtube_search",
            "web_read",
            "practice_step",
            "finish_session",
            "search",
            "get_block",
            "get_profile",
            "start_session",
            "offer_replies",
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

root = AgentSpec(
    name="root",
    description=(
        "Корневой агент-оркестратор: сам отвечает на простое и ведёт разговор, "
        "сложные задачи передаёт специалистам через run_agent (каталог — list_agents)."
    ),
    prompt_path=AGENTS_DIR / "root" / "prompt.md",
    tools=(
        free_chat.tools
        | {"run_agent", "list_agents", "propose_change"}
        | SESSION_TOOLS
        | ENTRY_TOOLS
        | {"get_session_state", "mark_chapter_done", "get_review_queue", "answer_review"}
        # разбор главы карточкой: root ведёт интент «review» (единый вход) сам
        | {"show_chapter_review"}
    ),
    max_steps=30,
)


def _skill_tool_names(skills, agent_name: str) -> frozenset[str]:
    """Инструменты скиллов агента: run_skill/list_skills + builtin + свои (root видит все).

    Скиллы живут на диске, поэтому имена берём из SkillLoader на регистрации агентов —
    реестр инструментов в этот момент ещё пуст.
    """
    names = {"run_skill", "list_skills"} | skills.builtin_names() | skills.names_owned_by(agent_name)
    if agent_name == "root":
        names |= skills.agent_skill_names()
    return frozenset(names)


def register_agents(c) -> None:
    """Зарегистрировать тьюторов чата; free_chat и root получают скиллы (T-036, T-037)."""
    registry: AgentRegistry = c.agent_registry
    if c.skills is not None:
        registry.register(
            replace(free_chat, tools=free_chat.tools | _skill_tool_names(c.skills, "free_chat"))
        )
        registry.register(replace(root, tools=root.tools | _skill_tool_names(c.skills, "root")))
    else:
        registry.register(free_chat)
        registry.register(root)
    registry.register(quick_reviewer)
    registry.register(session_tutor)
    registry.register(repo_scout)
