from mcp.server.mcpserver import MCPServer

from . import core, skills_loader

mcp = MCPServer("learnos")


@mcp.tool()
def create_course(topic: str, plan_json: str = "{}") -> dict:
    """Создать курс по теме. plan_json — опциональный JSON-план сессий."""
    import json as _json

    return core.create_course(topic, _json.loads(plan_json))


@mcp.tool()
def list_courses() -> list[dict]:
    """Список курсов."""
    return core.list_courses()


@mcp.tool()
def add_source(course_id: int, kind: str, title: str, url: str | None = None, local_path: str | None = None) -> dict:
    """Добавить источник к курсу. kind: book | video | web | course."""
    return core.add_source(course_id, kind, title, url, local_path)


@mcp.tool()
def list_sources(course_id: int) -> list[dict]:
    """Источники курса."""
    return core.list_sources(course_id)


@mcp.tool()
def start_session(course_id: int) -> dict:
    """Начать сессию обучения по курсу. Возвращает состояние стейт-машины."""
    return core.start_session(course_id)


@mcp.tool()
def get_session_state(session_id: int) -> dict:
    """Текущее состояние сессии: state, transcript, allowed_events."""
    return core.get_session(session_id)


@mcp.tool()
def advance(session_id: int, event: str, payload_json: str = "{}") -> dict:
    """Продвинуть сессию. События переходов: theory_done, next_block, go_practice, practice_done.
    Лог-события (без смены состояния): ask, answer, note, practice_log. payload_json — JSON."""
    import json as _json

    return core.advance(session_id, event, _json.loads(payload_json))


@mcp.tool()
def finish_session(session_id: int, block_json: str) -> dict:
    """Завершить сессию (только из state=debrief) и закоммитить блок в KB.
    block_json: {title, tags, sources, theses, my_examples, mermaid, links}."""
    import json as _json

    return core.finish_session(session_id, _json.loads(block_json))


@mcp.tool()
def list_blocks(course_id: int | None = None) -> list[dict]:
    """Блоки базы знаний (создаются только через finish_session)."""
    return core.list_blocks(course_id)


@mcp.tool()
def get_block(block_uid: str) -> dict:
    """Блок KB целиком (frontmatter + markdown)."""
    return core.get_block(block_uid)


@mcp.tool()
def list_skills() -> list[dict]:
    """Доступные drop-in скиллы и их параметры."""
    return skills_loader.registry_info()


@mcp.tool()
def run_skill(name: str, kwargs_json: str = "{}") -> dict:
    """Выполнить скилл. kwargs_json — JSON с аргументами согласно list_skills."""
    import json as _json

    return skills_loader.run_skill(name, _json.loads(kwargs_json))


skills_loader.load_skills()
skills_loader.register_mcp_tools(mcp)
