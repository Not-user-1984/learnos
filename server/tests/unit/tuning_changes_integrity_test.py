"""R-15: целостность правок промптов — apply сверяет базу, reject только pending, base_changed."""

import pytest

from app.kernel.errors import NotFound, ValidationFailed


def _stage(container, new_text: str, agent: str = "free_chat") -> int:
    out = container.tuning.stage_change(agent, new_text, "тест правки")
    return out["change_id"]


def test_apply_rejects_stale_draft(container):
    """База ушла вперёд — apply старого черновика отклоняется (R-15)."""
    stale_id = _stage(container, "Новый промпт номер один, достаточно длинный текст.")

    # между черновиком и apply база изменилась (другая правка применена)
    container.tuning.stage_change("free_chat", "Вторая правка промпта, тоже длинная.", "вторая")
    rows = container.tuning.changes(status="pending")
    fresh_id = None
    for c in rows:
        if c["status"] == "pending" and c["change_id"] != stale_id:
            fresh_id = c["change_id"]
    assert fresh_id, "второй черновик не нашёлся"
    container.tuning.apply_change(fresh_id)

    with pytest.raises(ValidationFailed, match="изменился"):
        container.tuning.apply_change(stale_id)


def test_reject_only_pending(container):
    """Applied-правку нельзя «отклонить» — статус больше не врёт (R-15)."""
    change_id = _stage(container, "Правка, которая будет применена. Текст достаточной длины.")
    container.tuning.apply_change(change_id)

    with pytest.raises(ValidationFailed, match="уже applied"):
        container.tuning.reject_change(change_id)


def test_override_records_base_sha_and_detects_base_change(container):
    """read_prompt видит, что базовый промпт из кода ушёл вперёд override (R-15)."""

    change_id = _stage(container, "Первая версия промпта override. Достаточно длинный текст.")
    container.tuning.apply_change(change_id)

    info = container.tuning.read_prompt("free_chat")
    assert info["has_override"] is True
    assert info["base_changed"] is False

    # базовый файл в коде изменился (новый релиз с правками промпта)
    spec_prompt = container.agent_registry.get("free_chat").prompt_path
    original = spec_prompt.read_text(encoding="utf-8")
    try:
        spec_prompt.write_text(original + "\n\nНовое правило из релиза.", encoding="utf-8")
        assert container.tuning.read_prompt("free_chat")["base_changed"] is True
    finally:
        spec_prompt.write_text(original, encoding="utf-8")
    assert container.tuning.read_prompt("free_chat")["base_changed"] is False


def test_unknown_change_rejected(container):
    with pytest.raises(NotFound):
        container.tuning.reject_change(999999)


def test_external_mcp_tools_reach_root(container):
    """R-29: обёртки внешнего MCP попадают в spec.tools root и убираются с сервером."""
    registry = container.agent_registry

    class _FakeExt:
        """Минимальный двойник McpExtService для проверки проброса."""

    from app.modules.mcpext.service import McpExtService

    ext = McpExtService(container.uow, container.tools, None, registry)
    ext._register_wrappers(  # noqa: SLF001
        "helper",
        "http://127.0.0.1:1/mcp",
        {},
        [{"name": f"tool_{i}", "description": f"инструмент {i}"} for i in range(3)],
    )
    root_tools = registry.get("root").tools
    got = {n for n in root_tools if n.startswith("mcp_helper_")}
    assert len(got) == 3

    ext._unregister_wrappers("helper")  # noqa: SLF001
    assert not {n for n in registry.get("root").tools if n.startswith("mcp_helper_")}
