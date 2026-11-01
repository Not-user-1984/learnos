"""R-24: трейсы запусков — usage у structured-вызовов и шаги доступны по /api/runs."""

import asyncio
import json

from app.agent.spec import AgentContext
from app.llm.providers.fake import FakeTurn
from app.modules.knowledge.agents import block_writer


def test_runs_api_exposes_structured_usage_and_steps(container, client, fake_llm):
    fake_llm.queue(FakeTurn(text=json.dumps({"title": "Урок", "theses": ["тезис"]}, ensure_ascii=False)))
    out = asyncio.run(
        container.agent_runtime.run_structured(block_writer, AgentContext(), "Транскрипт сессии")
    )
    assert out.title == "Урок"

    runs = client.get("/api/runs", params={"agent": "block_writer"}).json()
    assert runs, "запуск не попал в /api/runs"
    run = runs[0]
    assert run["status"] == "ok"
    assert run["input_tokens"] > 0 and run["output_tokens"] > 0  # R-24: раньше нули

    detail = client.get(f"/api/runs/{run['id']}").json()
    kinds = [st["kind"] for st in detail["steps"]]
    assert "structured" in kinds
    structured_step = next(st for st in detail["steps"] if st["kind"] == "structured")
    assert structured_step["tokens_in"] > 0
    assert structured_step["name"] == "BlockWriterDraft"


def test_run_detail_404_for_missing(container, client):
    assert client.get("/api/runs/999999").status_code == 404


def test_chat_run_records_llm_and_tool_steps(container, client, fake_llm):
    """Полный чат-прогон: в трейсе есть llm-шаги с токенами (R-24)."""
    conv = client.post("/api/conversations", json={}).json()
    fake_llm.queue(FakeTurn(text="Просто ответ без инструментов"))
    with client.stream(
        "POST", f"/api/conversations/{conv['uid']}/messages", json={"content": "привет"}
    ) as resp:
        "".join(resp.iter_text())

    runs = client.get("/api/runs", params={"limit": 5}).json()
    assert runs
    detail = client.get(f"/api/runs/{runs[0]['id']}").json()
    llm_steps = [st for st in detail["steps"] if st["kind"] == "llm"]
    assert llm_steps and llm_steps[0]["tokens_in"] > 0
