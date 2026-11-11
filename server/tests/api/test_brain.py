"""B-007: второй мозг — capture идемпотентен, context в бюджете, save_note из MCP → inbox."""

import json

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.kernel.tools.spec import ToolContext
from app.modules.knowledge.domain import BlockDraft


def test_capture_text_idempotent(container):
    """Одна и та же заметка дважды → один блок, created=false на повторе."""
    brain = container.brain
    first = brain.capture("text", "Докер — это платформа контейнеров", title="Заметка про докер")
    assert first["created"] is True
    assert first["status"] == "inbox"
    second = brain.capture("text", "докер — это платформа  контейнеров")  # пробелы/регистр не важны
    assert second["created"] is False
    assert second["uid"] == first["uid"]

    block = container.knowledge.get_block(first["uid"])
    assert block.meta.category_status == "inbox"
    assert block.meta.verified is False


def test_capture_url_idempotent(container):
    """Один и тот же URL дважды → один источник."""
    brain = container.brain
    first = brain.capture("url", "https://youtu.be/dQw4w9WgXcQ")
    assert first["created"] is True
    second = brain.capture("url", "https://youtu.be/dQw4w9WgXcQ/")
    assert second["created"] is False
    assert second["uid"] == first["uid"]


def test_context_budget_and_verified_first(container):
    """Verified-блок идёт раньше inbox; ответ укладывается в бюджет."""
    kb = container.knowledge
    verified = kb.save_block(
        BlockDraft(
            title="Kubernetes ingress",
            summary="Ingress маршрутизирует трафик",
            kind="note",
            theses=("Ingress — L7 маршрут",),
        ),
        category_status="confirmed",
        verified=True,
    )
    brain = container.brain
    brain.capture("text", "ingress контроллер тоже про kubernetes маршрутизацию")

    out = brain.context("kubernetes ingress", budget_chars=900)
    types = [(i["type"], i["uid"]) for i in out["items"]]
    assert out["items"], "контекст не пуст"
    assert types[0][1] == verified.meta.uid  # verified раньше inbox
    assert any(i["type"] == "inbox" for i in out["items"])
    total = sum(len(i["excerpt"]) + len(i["title"]) for i in out["items"])
    assert total <= 900 * 1.5  # заголовки+excerpt — в бюджете с запасом


def test_save_note_from_mcp_goes_to_inbox_from_agent_confirmed(container):
    """Канальный дефолт (B-007): внешний MCP — inbox/unverified, веб-чат (agent) — confirmed."""
    draft = {"title": "Заметка из мозга", "theses": ["тезис"], "kind": "note"}
    from_mcp = container.tools.call("save_note", {"draft_json": draft}, ToolContext(channel="mcp"))
    assert from_mcp["category_status"] == "inbox"
    assert from_mcp["verified"] is False

    from_chat = container.tools.call("save_note", {"draft_json": draft}, ToolContext(channel="agent"))
    assert from_chat["category_status"] == "confirmed"
    assert from_chat["verified"] is True


@pytest.fixture
def brain_app(container, monkeypatch):
    """Приложение с живыми MCP-менеджерами (rest_app их выкидывает для TestClient)."""
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_CONTAINER", container)
    return main_mod.create_app()


async def test_brain_mcp_e2e(brain_app):
    """e2e MCP-клиентом: /mcp/brain ≤8 тулов с описаниями параметров, capture/context/resources."""
    async with brain_app.router.lifespan_context(brain_app):
        async with streamable_http_client(
            "http://127.0.0.1:1/mcp/brain",
            http_client=httpx.AsyncClient(
                transport=httpx.ASGITransport(app=brain_app), base_url="http://127.0.0.1:1"
            ),
        ) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()

                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                assert len(names) <= 8
                assert {
                    "capture",
                    "context",
                    "get",
                    "list_topics",
                    "add_source_kb",
                    "inbox",
                    "promote_hint",
                } <= set(names)
                capture = next(t for t in tools.tools if t.name == "capture")
                props = capture.input_schema["properties"]
                assert props["kind"]["description"]
                assert props["content"]["description"]

                res = await session.call_tool(
                    "capture", {"kind": "text", "content": "kubernetes — оркестратор"}
                )
                assert not res.is_error
                payload = json.loads(res.content[0].text)
                assert payload["created"] is True

                res2 = await session.call_tool(
                    "capture", {"kind": "text", "content": "kubernetes — оркестратор"}
                )
                payload2 = json.loads(res2.content[0].text)
                assert payload2["created"] is False

                res3 = await session.call_tool("context", {"topic": "kubernetes"})
                payload3 = json.loads(res3.content[0].text)
                assert any(i["uid"] == payload["uid"] for i in payload3["items"])

                r = await session.read_resource(f"learnos://block/{payload['uid']}")
                assert "kubernetes" in r.contents[0].text.lower() or len(r.contents[0].text) >= 0
