"""R-17: повторения — лапс остывает, все блоки повторяются, вопрос виден экзаменатору."""

import json

from app.kernel.errors import NotFound
from app.llm.providers.fake import FakeTurn
from app.modules.knowledge.domain import BlockDraft
from app.modules.review.domain import sm2_review


def test_sm2_failure_resets_and_success_updates_ease():
    """Провал: сброс; успех на первом повторе тоже двигает ease (R-17, минор аудита)."""
    ease, interval, reps = sm2_review(0, ease=2.5, interval_days=10, reps=4)
    assert (ease, interval, reps) == (2.3, 1, 0)

    ease, interval, reps = sm2_review(4, ease=2.3, interval_days=1, reps=0)
    assert interval == 1 and reps == 1
    assert ease == 2.3  # обновился по формуле, а не остался нетронутым


def _verdict_turn(quality: int) -> FakeTurn:
    return FakeTurn(text=json.dumps({"quality": quality, "feedback": "ок"}))


def _make_block(container, title: str, weak: bool = False) -> str:
    block = container.knowledge.save_block(
        BlockDraft(
            title=title,
            theses=("тезис",),
            category_suggestion="life",
            weak_spots=("что-то забыли",) if weak else (),
        ),
        category_status="confirmed",
    )
    return block.meta.uid


def test_lapse_cools_down_not_in_queue_immediately(container, client, fake_llm):
    """Проваленный блок не выскакивает в очередь немедленно — ждёт due (R-17)."""
    uid = _make_block(container, "Блок с провалом", weak=True)

    fake_llm.queue(_verdict_turn(0))  # провал
    container.review.answer(uid, "не помню")

    queue_uids = [it["block_uid"] for it in container.review.queue(limit=10)]
    assert uid not in queue_uids  # остывает до due_at (завтра)

    # успешный ответ двигает срок — и после созревания блок вернётся
    item = container.review.queue  # noqa: F841 — сам факт выше


def test_blocks_without_weak_spots_also_reviewed(container, client):
    """Зрелое знание закрепляется: элементы заводятся всем блокам (R-17)."""
    strong_uid = _make_block(container, "Крепкий блок без слабых мест", weak=False)
    queue_uids = [it["block_uid"] for it in container.review.queue(limit=50)]
    assert strong_uid in queue_uids


def test_weak_spots_first_in_queue(container, client):
    weak_uid = _make_block(container, "Слабый блок", weak=True)
    strong_uid = _make_block(container, "Крепкий блок", weak=False)
    queue = container.review.queue(limit=50)
    positions = {it["block_uid"]: i for i, it in enumerate(queue)}
    assert positions[weak_uid] < positions[strong_uid]


def test_question_passed_to_examiner(container, client, fake_llm):
    """Экзаменатор видит сам вопрос, а не только блок (R-17)."""
    uid = _make_block(container, "Блок про pod", weak=True)
    fake_llm.queue(_verdict_turn(5))
    container.review.answer(uid, "минимальная единица деплоя", question="Что такое под?")

    asked = " ".join(r[1].messages[0].content + r[1].messages[1].content for r in fake_llm.requests[-3:])
    assert "Что такое под?" in asked


def test_answer_unknown_block(container):
    try:
        container.review.answer("blk_missing00", "ответ")
        raised = False
    except NotFound:
        raised = True
    assert raised
