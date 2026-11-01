"""R-03: сбой генерации блока не должен закрывать сессию и терять урок.

finish_session: блок пишется ДО закрытия; при сбое LLM сессия остаётся в debrief
и повторный finish создаёт блок. Частичный сбой (блок записан, закрытие упало)
не порождает дубль при повторе.
"""

import json

import pytest

from app.llm.providers.fake import FakeTurn
from app.modules.knowledge.domain import BlockDraft


def _to_debrief(client, ref: str) -> None:
    """Провести сессию по стейт-машине до debrief (theory→check→practice→debrief)."""
    for event in ("theory_done", "go_practice", "practice_done"):
        r = client.post(f"/api/sessions/{ref}/advance", json={"event": event, "payload": {}})
        assert r.status_code == 200, r.text


def _writer_turn() -> FakeTurn:
    return FakeTurn(
        text=json.dumps(
            {
                "title": "Урок по подам",
                "summary": "итог урока",
                "theses": ["тезис"],
                "concepts": [{"term": "под", "definition": "единица деплоя"}],
                "practice": [
                    {"machine": "pve", "command": "kubectl get pods", "explanation": "список подов"}
                ],
                "weak_spots": ["сетевые политики"],
                "category_suggestion": "infra/kubernetes",
            },
            ensure_ascii=False,
        )
    )


def test_finish_session_survives_llm_failure(container, client, fake_llm):
    """LLM упала на block_writer → сессия жива; повторный finish создаёт блок (R-03)."""
    course = client.post("/api/courses", json={"topic": "k8s"}).json()
    ses = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    ref = ses["session_uid"]
    _to_debrief(client, ref)

    fake_llm.queue(FakeTurn(error=RuntimeError("LLM недоступна")))
    with pytest.raises(Exception, match="LLM недоступна"):
        container.learning.finish_session(ref)

    state = client.get(f"/api/sessions/{ref}").json()
    assert state["status"] == "active"
    assert state["state"] == "debrief"

    # LLM починили — повторный finish проходит, блок создан, сессия закрыта
    fake_llm.queue(_writer_turn())
    fin = container.learning.finish_session(ref)
    assert fin["ok"] is True
    assert fin["block_uid"].startswith("blk_")
    closed = client.get(f"/api/sessions/{ref}").json()
    assert closed["status"] == "finished"
    assert closed["state"] == "done"


def test_finish_session_retry_after_partial_failure_does_not_duplicate(container, client):
    """Блок записан, сессия ещё открыта → повтор закрывает без дубля блока (R-03)."""
    course = client.post("/api/courses", json={"topic": "k8s2"}).json()
    ses = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    ref = ses["session_uid"]
    _to_debrief(client, ref)

    # имитируем «финиш упал после записи блока»: блок есть, сессия открыта
    draft = BlockDraft(title="Урок по подам", theses=("тезис",), category_suggestion="infra")
    saved = container.knowledge.save_block(draft, session_uid=ref)
    assert container.knowledge.count_for_session(ref) == 1

    fin = container.learning.finish_session(ref)  # без LLM: должен взять существующий блок
    assert fin["block_uid"] == saved.meta.uid
    assert container.knowledge.count_for_session(ref) == 1  # дубля нет
    closed = client.get(f"/api/sessions/{ref}").json()
    assert closed["status"] == "finished"
