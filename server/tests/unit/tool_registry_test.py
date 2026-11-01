"""ToolRegistry: валидация аргументов, маппинг ошибок, обрезка с сохранением _card."""

import pytest
from pydantic import BaseModel

from app.kernel.errors import NotFound
from app.kernel.tools.registry import DuplicateTool, ToolRegistry, UnknownTool, _truncate
from app.kernel.tools.spec import ToolContext, ToolSpec


class NumArgs(BaseModel):
    """Аргументы тестового инструмента."""

    n: int


def make_registry(max_result_chars: int = 8000) -> ToolRegistry:
    """Реестр с инструментом calc: n=404 имитирует NotFound."""
    r = ToolRegistry(max_result_chars=max_result_chars)

    def calc(args: NumArgs, ctx: ToolContext) -> dict:
        del ctx
        if args.n == 404:
            raise NotFound("нет такого")
        return {"n": args.n}

    r.register(ToolSpec(name="calc", module="t", description="калькулятор", args_model=NumArgs, handler=calc))
    return r


def test_duplicate_name_rejected():
    r = make_registry()
    with pytest.raises(DuplicateTool):
        r.register(r.get("calc"))


def test_call_returns_result_for_valid_args():
    assert make_registry().call("calc", {"n": 2}, ToolContext()) == {"n": 2}


def test_call_invalid_args_reported_not_raised():
    out = make_registry().call("calc", {"n": "не число"}, ToolContext())
    assert out["error"] == "validation_failed"
    assert "message" in out


def test_call_maps_app_error_to_error_and_message():
    out = make_registry().call("calc", {"n": 404}, ToolContext())
    assert out == {"error": "not_found", "message": "нет такого"}


def test_unknown_tool_raises_for_caller():
    with pytest.raises(UnknownTool):
        make_registry().call("nope", {}, ToolContext())


def test_filter_by_names_and_channel():
    r = make_registry()
    found = r.filter(names={"calc"}, channel="mcp")
    assert [t.name for t in found] == ["calc"]
    assert r.filter(names={"calc"}, channel="нет такого") == []


def test_truncate_preserves_card_and_marks_truncated():
    payload = {"body": "x" * 5000, "_card": {"type": "note", "title": "т"}}
    out = _truncate(payload, 1000)
    assert out["truncated"] is True
    assert out["_card"] == {"type": "note", "title": "т"}
    assert len(out["body"]) <= 1000 // 2 + 1


def test_truncate_keeps_short_payload_intact():
    payload = {"body": "коротко", "_card": {"type": "note"}}
    assert _truncate(payload, 1000) == payload


def test_agent_channel_truncates_mcp_does_not():
    r = make_registry(max_result_chars=50)

    def big(args: NumArgs, ctx: ToolContext) -> dict:
        del ctx
        return {"text": "y" * 500, "_card": {"type": "card"}}

    r.register(ToolSpec(name="big", module="t", description="большой", args_model=NumArgs, handler=big))

    agent_out = r.call("big", {"n": 1}, ToolContext(channel="agent"))
    assert agent_out["truncated"] is True
    assert agent_out["_card"] == {"type": "card"}
    assert len(agent_out["text"]) <= 50 // 2 + 1

    mcp_out = r.call("big", {"n": 1}, ToolContext(channel="mcp"))
    assert len(mcp_out["text"]) == 500
    assert "truncated" not in mcp_out


def test_truncate_keeps_list_items_instead_of_dropping_whole_list():
    """Список длиннее бюджета не выбрасывается целиком: первые элементы + счётчик (R-01)."""
    items = [
        {"uid": f"blk_{i:03d}", "title": f"блок номер {i} о контейнерах", "kind": "lesson"}
        for i in range(100)
    ]
    out = _truncate({"blocks": items}, 2000)
    assert out["truncated"] is True
    assert isinstance(out["blocks"], list) and 1 <= len(out["blocks"]) < 100
    assert out["truncated_items"] == 100 - len(out["blocks"])
    assert "hint" in out
    # первые элементы — ровно начало списка, без переупорядочивания
    assert out["blocks"][0]["uid"] == "blk_000"


def test_truncate_nested_dicts_inside_lists():
    items = [{"meta": {"text": "z" * 3000}, "n": i} for i in range(50)]
    out = _truncate({"rows": items}, 2000)
    assert out["truncated"] is True
    assert isinstance(out["rows"], list) and out["rows"]
    for row in out["rows"]:
        assert len(row["meta"]["text"]) <= 1000 + 1


def test_non_truncatable_tool_keeps_window_result_intact():
    """Оконный инструмент (truncatable=False) не режется: offset/next_offset согласованы (R-01)."""
    r = make_registry(max_result_chars=200)

    def windowed(args: NumArgs, ctx: ToolContext) -> dict:
        del ctx
        text = "а" * 30_000
        offset, limit = args.n, 6000
        chunk = text[offset : offset + limit]
        return {
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(text) else None,
            "text": chunk,
        }

    r.register(
        ToolSpec(
            name="windowed",
            module="t",
            description="оконный",
            args_model=NumArgs,
            handler=windowed,
            truncatable=False,
        )
    )

    collected = ""
    offset = 0
    while True:
        out = r.call("windowed", {"n": offset}, ToolContext(channel="agent"))
        assert "truncated" not in out  # окно не порезано
        assert out["text"] == "а" * min(6000, 30_000 - offset)
        collected += out["text"]
        if out["next_offset"] is None:
            break
        offset = out["next_offset"]
    assert len(collected) == 30_000  # без дыр и дублей


def test_window_tools_are_not_truncatable(container):
    """read_chapter и web_read объявлены не режущимися — их окна согласованы с next_offset (R-01)."""
    from app.modules.library.tools import library_tools
    from app.modules.research.tools import research_tools

    lib = {t.name: t for t in library_tools(container)}
    res = {t.name: t for t in research_tools(container)}
    assert lib["read_chapter"].truncatable is False
    assert res["web_read"].truncatable is False
