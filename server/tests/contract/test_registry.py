"""Контракты реестра инструментов: уникальность, имена v1, схемы, сигнатуры MCP."""

import inspect

from app.kernel.tools.mcp_adapter import _build_fn
from app.kernel.tools.spec import ToolContext

# обязательные имена инструментов v1 (паритет MCP, ТЗ 08)
REQUIRED_V1 = {
    "create_course",
    "list_courses",
    "add_source",
    "list_sources",
    "process_source",
    "list_chapters",
    "read_chapter",
    "search_chunks",
    "research_sources",
    "start_session",
    "get_session_state",
    "advance",
    "finish_session",
    "list_blocks",
    "get_block",
    "list_skills",
    "run_skill",
}

MCP_MODULES = {
    "knowledge",
    "library",
    "learning",
    "chat",
    "courses",
    "profile",
    "research",
    "search",
    "export",
    "skills",
    "review",
    "messenger",
    "tuning",
    "mcpext",
}


def test_tool_names_are_unique(container):
    names = [t.name for t in container.tools.all()]
    assert len(names) == len(set(names))


def test_required_v1_tools_present(container):
    names = {t.name for t in container.tools.all()}
    missing = REQUIRED_V1 - names
    assert not missing, f"потеряны инструменты v1: {missing}"


def test_every_tool_module_is_known(container):
    modules = {t.module for t in container.tools.all()}
    assert modules <= MCP_MODULES
    assert modules == MCP_MODULES  # каждый модуль заявляет хотя бы один инструмент


def test_every_tool_has_object_json_schema(container):
    for tool in container.tools.all():
        schema = tool.json_schema()
        assert isinstance(schema, dict), tool.name
        assert schema.get("type") == "object", tool.name
        assert isinstance(schema.get("properties"), dict), tool.name


def test_mcp_fn_signature_matches_args_model(container):
    """_build_fn генерирует функцию с параметрами ровно по полям args_model."""
    for spec in container.tools.all():
        fn = _build_fn(spec, container.tools)
        params = set(inspect.signature(fn).parameters)
        assert params == set(spec.args_model.model_fields), spec.name
        assert fn.__name__ == spec.name
        assert fn.__doc__ == spec.description


def test_knowledge_scope_excludes_library_tools(container):
    knowledge = {t.name for t in container.tools.by_module("knowledge")}
    library = {t.name for t in container.tools.by_module("library")}
    assert knowledge, "в knowledge нет инструментов"
    assert library, "в library нет инструментов"
    assert not (knowledge & library), "инструмент попал в два модуля"
    # каждый инструмент принадлежит ровно одному модулю
    per_module = {}
    for t in container.tools.all():
        per_module.setdefault(t.name, []).append(t.module)
    assert all(len(m) == 1 for m in per_module.values())


def test_call_list_skills_through_registry(container):
    """Инструмент вызывается через реестр как из MCP: список drop-in скиллов."""
    out = container.tools.call("list_skills", {}, ToolContext(channel="mcp"))
    names = {s["name"] for s in out}
    assert {"web-search", "book-splitter", "youtube-to-summary"} <= names


def test_call_unknown_tool_through_registry(container):
    from app.kernel.tools.registry import UnknownTool

    try:
        container.tools.call("no_such_tool", {}, ToolContext(channel="mcp"))
        raise AssertionError("ожидали UnknownTool")
    except UnknownTool:
        pass


def test_agents_registered_in_registry(container):
    """Все модули зарегистрировали своих агентов (включая library)."""
    names = {a.name for a in container.agent_registry.all()}
    assert {
        "free_chat",
        "quick_reviewer",
        "session_tutor",
        "block_writer",
        "categorizer",
        "chapter_summarizer",
        "course_planner",
    } <= names


def test_agent_duplicate_name_rejected():
    from app.agent.registry import AgentRegistry
    from app.agent.spec import AgentSpec

    registry = AgentRegistry()
    spec = AgentSpec(name="dup", description="d", prompt_path="/dev/null")
    registry.register(spec)
    try:
        registry.register(spec)
        raise AssertionError("ожидали ValueError")
    except ValueError:
        pass
