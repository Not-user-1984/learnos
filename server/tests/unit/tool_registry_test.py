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
