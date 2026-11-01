"""T-051 Э5: модель знания — concepts в таблице, фейнман-пары в assessments."""

import json

from app.llm.providers.fake import FakeTurn
from app.modules.knowledge.domain import BlockDraft, Concept
from app.modules.review.domain import sm2_review  # noqa: F401 — смежный слой


def _concepts_rows(container, uid: str) -> list[dict]:
    from sqlalchemy import text as sql_text

    with container.uow() as uow:
        rows = (
            uow.session.execute(
                sql_text("SELECT uid, term, definition FROM concepts WHERE block_uid = :u ORDER BY term"),
                {"u": uid},
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


def test_save_block_writes_concepts_table(container):
    block = container.knowledge.save_block(
        BlockDraft(
            title="Урок с понятиями",
            theses=("тезис",),
            category_suggestion="infra",
            concepts=(
                Concept("под", "единица деплоя"),
                Concept("CNI", "плагин сети"),
            ),
        ),
        category_status="confirmed",
    )
    rows = _concepts_rows(container, block.meta.uid)
    assert [(r["term"], r["definition"]) for r in rows] == [("CNI", "плагин сети"), ("под", "единица деплоя")]
    assert all(r["uid"].startswith("cpt_") for r in rows)


def test_update_block_rewrites_concepts(container):
    block = container.knowledge.save_block(
        BlockDraft(
            title="Блок", theses=("т",), category_suggestion="life", concepts=(Concept("старое", "было"),)
        ),
        category_status="confirmed",
    )
    container.knowledge.update_block(
        block.meta.uid,
        {"concepts": [{"term": "новое", "definition": "стало"}]},
        "правка понятий",
    )
    rows = _concepts_rows(container, block.meta.uid)
    assert len(rows) == 1 and rows[0]["term"] == "новое"


def _to_debrief_with_feynman(client, ref: str) -> None:
    for event, payload in (
        ("ask", {"question": "Что такое под?"}),
        ("answer", {"text": "единица деплоя", "verdict": "ok"}),
        ("ask", {"question": "Зачем CNI?"}),
        ("answer", {"text": "не помню", "verdict": "missed"}),
        ("theory_done", {}),
        ("go_practice", {}),
        ("practice_done", {}),
    ):
        r = client.post(f"/api/sessions/{ref}/advance", json={"event": event, "payload": payload})
        assert r.status_code == 200, r.text


def test_finish_session_records_assessments(container, client, fake_llm):
    """Фейнман-пары уходят в assessments: вопрос, ответ, вердикт (T-051 Э5)."""
    course = client.post("/api/courses", json={"topic": "k8s"}).json()
    ses = client.post("/api/sessions", json={"course_id": course["id"]}).json()
    ref = ses["session_uid"]
    _to_debrief_with_feynman(client, ref)

    fake_llm.queue(FakeTurn(text=json.dumps({"title": "Урок", "theses": ["т"]}, ensure_ascii=False)))
    fin = container.learning.finish_session(ref)
    block_uid = fin["block_uid"]

    from sqlalchemy import text as sql_text

    with container.uow() as uow:
        rows = (
            uow.session.execute(
                sql_text(
                    "SELECT question, answer, verdict FROM assessments WHERE block_uid = :b ORDER BY id"
                ),
                {"b": block_uid},
            )
            .mappings()
            .all()
        )
    assert len(rows) == 2
    assert rows[0]["question"] == "Что такое под?" and rows[0]["verdict"] == "ok"
    assert rows[1]["verdict"] == "missed"
